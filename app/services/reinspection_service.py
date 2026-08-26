from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional

from .base_service import BaseService
from .sample_service import SampleService
from .test_service import TestService
from .report_service import ReportService
from ..models import ReInspection, Sample, Report, Retention, TestResult, Batch
from ..schemas import (
    ReInspectionCreate,
    DifferenceConfirm,
    ReInspectionResponse,
    Judgment,
    ReInspectionStatus,
    BatchStatus,
)
from ..exceptions import (
    QualityInspectionException,
    SampleNotFoundError,
    ReportNotFoundError,
    ReInspectionNotFoundError,
    ReInspectionLinkError,
    RetentionDestroyedError,
    InvalidStatusError,
)


class ReInspectionService(BaseService):
    def __init__(self, db: Session):
        super().__init__(db)
        self.sample_service = SampleService(db)
        self.test_service = TestService(db)
        self.report_service = ReportService(db)

    def validate_reinspection_request(self, data: ReInspectionCreate) -> None:
        original_sample = (
            self.db.query(Sample).filter(Sample.id == data.original_sample_id).first()
        )
        if not original_sample:
            raise SampleNotFoundError(sample_id=data.original_sample_id)

        original_report = (
            self.db.query(Report).filter(Report.id == data.original_report_id).first()
        )
        if not original_report:
            raise ReportNotFoundError(report_id=data.original_report_id)

        if original_report.sample_id != data.original_sample_id:
            raise ReInspectionLinkError("报告与样品不匹配")

        if original_report.report_type != "original":
            raise ReInspectionLinkError("只能基于原始报告申请复检")

        if not original_report.is_active:
            raise ReInspectionLinkError("原始报告已停用，不能再次申请复检")

        if original_sample.is_destroyed:
            raise RetentionDestroyedError(original_sample.sample_code)

        retention = (
            self.db.query(Retention)
            .filter(Retention.sample_id == data.original_sample_id)
            .first()
        )
        if retention and retention.destroyed:
            raise RetentionDestroyedError(original_sample.sample_code)

    def create_reinspection(self, data: ReInspectionCreate) -> ReInspection:
        self.validate_reinspection_request(data)

        original_sample = self.sample_service.get_sample(data.original_sample_id)
        original_report = self.report_service.get_report(data.original_report_id)

        reinspection_code = self.generate_code("RI")
        while (
            self.db.query(ReInspection)
            .filter(ReInspection.reinspection_code == reinspection_code)
            .first()
        ):
            reinspection_code = self.generate_code("RI")

        re_sample_data = type(
            "SampleCreate",
            (),
            {
                "batch_id": original_sample.batch_id,
                "sampling_person": data.applicant,
                "sample_type": "reinspection",
            },
        )()

        re_sample = self.sample_service.create_sample(re_sample_data)

        reinspection = ReInspection(
            reinspection_code=reinspection_code,
            original_sample_id=data.original_sample_id,
            original_report_id=data.original_report_id,
            re_sample_id=re_sample.id,
            reason=data.reason,
            applicant=data.applicant,
            status=ReInspectionStatus.PENDING.value,
        )

        self.db.add(reinspection)

        batch = original_sample.batch
        batch.status = BatchStatus.REINSPECTING.value
        batch.updated_at = datetime.now()

        original_report.is_active = False
        original_report.updated_at = datetime.now()

        self.db.commit()
        self.db.refresh(reinspection)
        return reinspection

    def get_reinspection(self, reinspection_id: int) -> ReInspection:
        reinspection = (
            self.db.query(ReInspection)
            .filter(ReInspection.id == reinspection_id)
            .first()
        )
        if not reinspection:
            raise ReInspectionNotFoundError(reinspection_id=reinspection_id)
        return reinspection

    def get_reinspection_by_code(self, reinspection_code: str) -> ReInspection:
        reinspection = (
            self.db.query(ReInspection)
            .filter(ReInspection.reinspection_code == reinspection_code)
            .first()
        )
        if not reinspection:
            raise ReInspectionNotFoundError(reinspection_code=reinspection_code)
        return reinspection

    def list_reinspections(
        self,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
        original_sample_id: Optional[int] = None,
    ) -> List[ReInspection]:
        query = self.db.query(ReInspection)
        if status:
            query = query.filter(ReInspection.status == status)
        if original_sample_id:
            query = query.filter(ReInspection.original_sample_id == original_sample_id)
        return query.order_by(ReInspection.created_at.desc()).offset(skip).limit(limit).all()

    def update_reinspection_status(
        self, reinspection_id: int, status: str
    ) -> ReInspection:
        reinspection = self.get_reinspection(reinspection_id)

        allowed_transitions = {
            ReInspectionStatus.PENDING.value: {ReInspectionStatus.TESTING.value},
        }
        if status not in allowed_transitions.get(reinspection.status, set()):
            raise InvalidStatusError(
                reinspection.status,
                f"{ReInspectionStatus.PENDING.value}->{ReInspectionStatus.TESTING.value}",
            )

        reinspection.status = status
        reinspection.updated_at = datetime.now()
        self.db.commit()
        self.db.refresh(reinspection)
        return reinspection

    def complete_reinspection_testing(self, reinspection_id: int) -> ReInspection:
        reinspection = self.get_reinspection(reinspection_id)

        if reinspection.status != ReInspectionStatus.TESTING.value:
            raise InvalidStatusError(reinspection.status, "testing")

        self.test_service.validate_reinspection_items_complete(
            reinspection.re_sample_id, reinspection_id
        )

        reinspection.status = ReInspectionStatus.COMPLETED.value
        reinspection.updated_at = datetime.now()

        self.db.commit()
        self.db.refresh(reinspection)
        return reinspection

    def confirm_difference(
        self, reinspection_id: int, data: DifferenceConfirm
    ) -> ReInspection:
        reinspection = self.get_reinspection(reinspection_id)

        if reinspection.status != ReInspectionStatus.COMPLETED.value:
            raise InvalidStatusError(reinspection.status, ReInspectionStatus.COMPLETED.value)

        if data.final_judgment not in (
            Judgment.PASS.value,
            Judgment.FAIL.value,
        ):
            raise QualityInspectionException(
                f"最终判定无效: {data.final_judgment}，必须为 {Judgment.PASS.value}(合格) 或 {Judgment.FAIL.value}(不合格)"
            )

        reinspection.difference_identified = data.difference_identified
        reinspection.difference_confirmed_by = data.confirmed_by
        reinspection.difference_confirmed_at = datetime.now()
        reinspection.difference_remark = data.difference_remark
        reinspection.final_judgment = data.final_judgment
        reinspection.status = ReInspectionStatus.CONFIRMED.value
        reinspection.updated_at = datetime.now()

        batch = reinspection.original_sample.batch
        batch.final_result = data.final_judgment
        if data.final_judgment == Judgment.PASS.value:
            batch.status = BatchStatus.COMPLETED.value
        else:
            batch.status = BatchStatus.REJECTED.value
        batch.updated_at = datetime.now()

        self.db.commit()
        self.db.refresh(reinspection)

        from .batch_service import BatchService
        batch_service = BatchService(self.db)
        batch_service.calculate_risk_level(batch.id)

        return reinspection

    def to_response(self, reinspection: ReInspection) -> ReInspectionResponse:
        return ReInspectionResponse(
            id=reinspection.id,
            reinspection_code=reinspection.reinspection_code,
            original_sample_id=reinspection.original_sample_id,
            original_sample_code=reinspection.original_sample.sample_code,
            original_report_id=reinspection.original_report_id,
            original_report_no=reinspection.original_report.report_no,
            re_sample_id=reinspection.re_sample_id,
            re_sample_code=reinspection.re_sample.sample_code,
            reason=reinspection.reason,
            applicant=reinspection.applicant,
            apply_time=reinspection.apply_time,
            status=reinspection.status,
            difference_identified=reinspection.difference_identified,
            difference_confirmed_by=reinspection.difference_confirmed_by,
            difference_confirmed_at=reinspection.difference_confirmed_at,
            difference_remark=reinspection.difference_remark,
            final_judgment=reinspection.final_judgment,
            created_at=reinspection.created_at,
        )
