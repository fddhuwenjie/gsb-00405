from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional
import json

from .base_service import BaseService
from .report_service import ReportService
from .batch_service import BatchService
from ..models import Arbitration, ReInspection, Report, Batch, TestResult, Sample
from ..schemas import (
    ArbitrationCreate,
    ArbitrationProcess,
    ArbitrationResponse,
    ArbitrationStatus,
    ReportType,
    Judgment,
    BatchStatus,
)
from ..exceptions import (
    ArbitrationNotFoundError,
    ArbitrationNotAllowedError,
    ReInspectionNotFoundError,
    ReportNotFoundError,
    InvalidStatusError,
)


class ArbitrationService(BaseService):
    def __init__(self, db: Session):
        super().__init__(db)
        self.report_service = ReportService(db)
        self.batch_service = BatchService(db)

    def _generate_arbitration_code(self) -> str:
        code = self.generate_code("ARB")
        while self.db.query(Arbitration).filter(Arbitration.arbitration_code == code).first():
            code = self.generate_code("ARB")
        return code

    def _get_reinspection_report(self, reinspection_id: int) -> Report:
        report = (
            self.db.query(Report)
            .filter(
                Report.reinspection_id == reinspection_id,
                Report.report_type == ReportType.REINSPECTION.value,
            )
            .first()
        )
        if not report:
            raise ReportNotFoundError(detail=f"复检ID {reinspection_id} 未找到对应复检报告")
        return report

    def validate_arbitration_request(self, data: ArbitrationCreate) -> ReInspection:
        reinspection = (
            self.db.query(ReInspection).filter(ReInspection.id == data.reinspection_id).first()
        )
        if not reinspection:
            raise ReInspectionNotFoundError(reinspection_id=data.reinspection_id)

        if reinspection.status != "confirmed":
            raise ArbitrationNotAllowedError("复检尚未完成差异确认，无法发起仲裁")

        existing_arbitration = (
            self.db.query(Arbitration)
            .filter(
                Arbitration.reinspection_id == data.reinspection_id,
                Arbitration.status != ArbitrationStatus.COMPLETED.value,
            )
            .first()
        )
        if existing_arbitration:
            raise ArbitrationNotAllowedError("该复检已存在未完成的仲裁")

        return reinspection

    def create_arbitration(self, data: ArbitrationCreate) -> Arbitration:
        reinspection = self.validate_arbitration_request(data)

        original_report = self.report_service.get_report(reinspection.original_report_id)
        reinspection_report = self._get_reinspection_report(reinspection.id)

        arbitration_code = self._generate_arbitration_code()

        batch = reinspection.original_sample.batch

        arbitration = Arbitration(
            arbitration_code=arbitration_code,
            batch_id=batch.id,
            reinspection_id=reinspection.id,
            original_report_id=original_report.id,
            reinspection_report_id=reinspection_report.id,
            dispute_source=data.dispute_source,
            dispute_items=json.dumps(data.dispute_items),
            arbitrator=data.arbitrator,
            status=ArbitrationStatus.PENDING.value,
        )

        self.db.add(arbitration)

        if reinspection_report.is_active:
            reinspection_report.is_active = False
            reinspection_report.updated_at = datetime.now()

        self.db.commit()
        self.db.refresh(arbitration)

        self.batch_service.calculate_risk_level(batch.id)

        return arbitration

    def get_arbitration(self, arbitration_id: int) -> Arbitration:
        arbitration = (
            self.db.query(Arbitration).filter(Arbitration.id == arbitration_id).first()
        )
        if not arbitration:
            raise ArbitrationNotFoundError(arbitration_id=arbitration_id)
        return arbitration

    def get_arbitration_by_code(self, arbitration_code: str) -> Arbitration:
        arbitration = (
            self.db.query(Arbitration).filter(Arbitration.arbitration_code == arbitration_code).first()
        )
        if not arbitration:
            raise ArbitrationNotFoundError(arbitration_code=arbitration_code)
        return arbitration

    def list_arbitrations(
        self,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
        batch_id: Optional[int] = None,
    ) -> List[Arbitration]:
        query = self.db.query(Arbitration)
        if status:
            query = query.filter(Arbitration.status == status)
        if batch_id:
            query = query.filter(Arbitration.batch_id == batch_id)
        return query.order_by(Arbitration.created_at.desc()).offset(skip).limit(limit).all()

    def process_arbitration(self, arbitration_id: int, data: ArbitrationProcess) -> Arbitration:
        arbitration = self.get_arbitration(arbitration_id)

        if arbitration.status == ArbitrationStatus.COMPLETED.value:
            raise InvalidStatusError(arbitration.status, "pending/processing")

        arbitration.status = ArbitrationStatus.PROCESSING.value
        arbitration.updated_at = datetime.now()
        self.db.commit()
        self.db.refresh(arbitration)

        return arbitration

    def complete_arbitration(self, arbitration_id: int, data: ArbitrationProcess) -> Arbitration:
        arbitration = self.get_arbitration(arbitration_id)

        if arbitration.status == ArbitrationStatus.COMPLETED.value:
            raise InvalidStatusError(arbitration.status, "pending/processing")

        batch = arbitration.batch
        reinspection = arbitration.reinspection

        arbitration.handling_opinion = data.handling_opinion
        arbitration.final_judgment = data.final_judgment
        arbitration.status = ArbitrationStatus.COMPLETED.value
        arbitration.completed_at = datetime.now()
        arbitration.updated_at = datetime.now()

        arbitration_report_no = self.report_service.generate_report_no()
        active_sample = next(
            (s for s in batch.samples if s.sample_type == "production" and not s.is_destroyed),
            batch.samples[0] if batch.samples else None,
        )
        if not active_sample:
            from ..exceptions import SampleNotFoundError
            raise SampleNotFoundError("批次没有可用样品")

        arbitration_report = Report(
            report_no=arbitration_report_no,
            batch_id=batch.id,
            sample_id=active_sample.id,
            report_type=ReportType.ARBITRATION.value,
            overall_judgment=data.final_judgment,
            issued_by=arbitration.arbitrator,
            issued_at=datetime.now(),
            is_active=True,
        )
        self.db.add(arbitration_report)
        self.db.flush()

        arbitration.arbitration_report_id = arbitration_report.id

        batch.final_result = data.final_judgment
        if data.final_judgment == Judgment.PASS.value:
            batch.status = BatchStatus.COMPLETED.value
        else:
            batch.status = BatchStatus.REJECTED.value
        batch.updated_at = datetime.now()

        reinspection.final_judgment = data.final_judgment
        reinspection.updated_at = datetime.now()

        self.db.commit()
        self.db.refresh(arbitration)

        self.batch_service.calculate_risk_level(batch.id)

        return arbitration

    def to_response(self, arbitration: Arbitration) -> ArbitrationResponse:
        dispute_items = []
        if arbitration.dispute_items:
            try:
                dispute_items = json.loads(arbitration.dispute_items)
            except (json.JSONDecodeError, TypeError):
                dispute_items = []

        return ArbitrationResponse(
            id=arbitration.id,
            arbitration_code=arbitration.arbitration_code,
            batch_id=arbitration.batch_id,
            batch_no=arbitration.batch.batch_no,
            reinspection_id=arbitration.reinspection_id,
            reinspection_code=arbitration.reinspection.reinspection_code,
            original_report_id=arbitration.original_report_id,
            original_report_no=arbitration.original_report.report_no,
            reinspection_report_id=arbitration.reinspection_report_id,
            reinspection_report_no=arbitration.reinspection_report.report_no,
            dispute_source=arbitration.dispute_source,
            dispute_items=dispute_items,
            arbitrator=arbitration.arbitrator,
            handling_opinion=arbitration.handling_opinion,
            final_judgment=arbitration.final_judgment,
            status=arbitration.status,
            arbitration_report_id=arbitration.arbitration_report_id,
            arbitration_report_no=arbitration.arbitration_report.report_no if arbitration.arbitration_report else None,
            created_at=arbitration.created_at,
            completed_at=arbitration.completed_at,
        )
