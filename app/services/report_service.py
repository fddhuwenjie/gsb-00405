from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional

from .base_service import BaseService
from .test_service import TestService
from ..models import Report, Sample, TestResult, Batch
from ..schemas import (
    ReportResponse,
    TestResultResponse,
    Judgment,
    ReportType,
    BatchStatus,
)
from ..exceptions import (
    ReportNotFoundError,
    SampleNotFoundError,
    InvalidStatusError,
)


class ReportService(BaseService):
    def __init__(self, db: Session):
        super().__init__(db)
        self.test_service = TestService(db)

    def generate_report_no(self) -> str:
        report_no = self.generate_code("RPT")
        while self.db.query(Report).filter(Report.report_no == report_no).first():
            report_no = self.generate_code("RPT")
        return report_no

    def get_report(self, report_id: int) -> Report:
        report = self.db.query(Report).filter(Report.id == report_id).first()
        if not report:
            raise ReportNotFoundError(report_id=report_id)
        return report

    def get_report_by_no(self, report_no: str) -> Report:
        report = self.db.query(Report).filter(Report.report_no == report_no).first()
        if not report:
            raise ReportNotFoundError(report_no=report_no)
        return report

    def list_reports(
        self,
        skip: int = 0,
        limit: int = 100,
        batch_id: Optional[int] = None,
        report_type: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> List[Report]:
        query = self.db.query(Report)
        if batch_id:
            query = query.filter(Report.batch_id == batch_id)
        if report_type:
            query = query.filter(Report.report_type == report_type)
        if is_active is not None:
            query = query.filter(Report.is_active == is_active)
        return query.order_by(Report.created_at.desc()).offset(skip).limit(limit).all()

    def _calculate_overall_judgment(
        self, sample_id: int, is_reinspection: bool = False, reinspection_id: Optional[int] = None
    ) -> str:
        if is_reinspection and reinspection_id:
            results = (
                self.db.query(TestResult)
                .filter(
                    TestResult.sample_id == sample_id,
                    TestResult.reinspection_id == reinspection_id,
                )
                .all()
            )
        else:
            results = (
                self.db.query(TestResult)
                .filter(
                    TestResult.sample_id == sample_id,
                    TestResult.is_reinspection == False,
                )
                .all()
            )

        if not results:
            return Judgment.PENDING.value

        has_fail = any(r.judgment == Judgment.FAIL.value for r in results)
        has_pending = any(r.judgment == Judgment.PENDING.value for r in results)

        if has_fail:
            return Judgment.FAIL.value
        if has_pending:
            return Judgment.PENDING.value
        return Judgment.PASS.value

    def create_original_report(self, sample_id: int, issued_by: str) -> Report:
        sample = self.db.query(Sample).filter(Sample.id == sample_id).first()
        if not sample:
            raise SampleNotFoundError(sample_id=sample_id)

        self.test_service.validate_test_items_complete(sample_id)

        overall_judgment = self._calculate_overall_judgment(sample_id, is_reinspection=False)

        report_no = self.generate_report_no()
        report = Report(
            report_no=report_no,
            batch_id=sample.batch_id,
            sample_id=sample_id,
            report_type=ReportType.ORIGINAL.value,
            overall_judgment=overall_judgment,
            issued_by=issued_by,
            issued_at=datetime.now(),
            is_active=True,
        )

        self.db.add(report)

        batch = sample.batch
        batch.status = (
            BatchStatus.COMPLETED.value
            if overall_judgment == Judgment.PASS.value
            else BatchStatus.JUDGING.value
        )
        batch.final_result = overall_judgment
        batch.updated_at = datetime.now()

        sample.status = "tested"
        sample.updated_at = datetime.now()

        self.db.commit()
        self.db.refresh(report)

        from .batch_service import BatchService
        batch_service = BatchService(self.db)
        batch_service.calculate_risk_level(sample.batch_id)

        return report

    def create_reinspection_report(
        self, sample_id: int, reinspection_id: int, issued_by: str
    ) -> Report:
        sample = self.db.query(Sample).filter(Sample.id == sample_id).first()
        if not sample:
            raise SampleNotFoundError(sample_id=sample_id)

        self.test_service.validate_reinspection_items_complete(sample_id, reinspection_id)

        overall_judgment = self._calculate_overall_judgment(
            sample_id, is_reinspection=True, reinspection_id=reinspection_id
        )

        report_no = self.generate_report_no()
        report = Report(
            report_no=report_no,
            batch_id=sample.batch_id,
            sample_id=sample_id,
            report_type=ReportType.REINSPECTION.value,
            reinspection_id=reinspection_id,
            overall_judgment=overall_judgment,
            issued_by=issued_by,
            issued_at=datetime.now(),
            is_active=True,
        )

        self.db.add(report)

        sample.status = "tested"
        sample.updated_at = datetime.now()

        self.db.commit()
        self.db.refresh(report)
        return report

    def create_final_report(self, batch_id: int, issued_by: str) -> Report:
        batch = self.db.query(Batch).filter(Batch.id == batch_id).first()
        if not batch:
            from ..exceptions import BatchNotFoundError
            raise BatchNotFoundError(batch_id=batch_id)

        if not batch.final_result:
            raise InvalidStatusError(batch.status, "final_result set")

        active_sample = next(
            (s for s in batch.samples if s.sample_type == "production" and not s.is_destroyed),
            batch.samples[0] if batch.samples else None,
        )

        if not active_sample:
            raise SampleNotFoundError("批次没有可用样品")

        report_no = self.generate_report_no()
        report = Report(
            report_no=report_no,
            batch_id=batch_id,
            sample_id=active_sample.id,
            report_type=ReportType.FINAL.value,
            overall_judgment=batch.final_result,
            issued_by=issued_by,
            issued_at=datetime.now(),
            is_active=True,
        )

        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)
        return report

    def to_response(self, report: Report) -> ReportResponse:
        test_results = []

        if report.report_type == ReportType.ORIGINAL.value:
            results = (
                self.db.query(TestResult)
                .filter(
                    TestResult.sample_id == report.sample_id,
                    TestResult.is_reinspection == False,
                )
                .all()
            )
        elif report.report_type == ReportType.REINSPECTION.value:
            results = (
                self.db.query(TestResult)
                .filter(
                    TestResult.sample_id == report.sample_id,
                    TestResult.reinspection_id == report.reinspection_id,
                )
                .all()
            )
        elif report.report_type == ReportType.ARBITRATION.value:
            batch_reports = (
                self.db.query(Report)
                .filter(
                    Report.batch_id == report.batch_id,
                    Report.report_type.in_([ReportType.ORIGINAL.value, ReportType.REINSPECTION.value, ReportType.ARBITRATION.value]),
                )
                .order_by(Report.created_at)
                .all()
            )
            results = []
            seen_items = set()
            for r in reversed(batch_reports):
                for tr in r.sample.test_results:
                    if tr.test_item_id not in seen_items:
                        if (r.report_type == ReportType.ORIGINAL.value and not tr.is_reinspection) or \
                           (r.report_type == ReportType.REINSPECTION.value and tr.reinspection_id) or \
                           (r.report_type == ReportType.ARBITRATION.value):
                            results.append(tr)
                            seen_items.add(tr.test_item_id)
        else:
            batch_reports = (
                self.db.query(Report)
                .filter(
                    Report.batch_id == report.batch_id,
                    Report.report_type.in_([ReportType.ORIGINAL.value, ReportType.REINSPECTION.value]),
                )
                .order_by(Report.created_at)
                .all()
            )
            results = []
            seen_items = set()
            for r in reversed(batch_reports):
                for tr in r.sample.test_results:
                    if tr.test_item_id not in seen_items:
                        if (r.report_type == ReportType.ORIGINAL.value and not tr.is_reinspection) or \
                           (r.report_type == ReportType.REINSPECTION.value and tr.reinspection_id):
                            results.append(tr)
                            seen_items.add(tr.test_item_id)

        for tr in results:
            test_results.append(self.test_service.to_response(tr))

        return ReportResponse(
            id=report.id,
            report_no=report.report_no,
            batch_id=report.batch_id,
            batch_no=report.batch.batch_no,
            sample_id=report.sample_id,
            sample_code=report.sample.sample_code,
            report_type=report.report_type,
            overall_judgment=report.overall_judgment,
            issued_by=report.issued_by,
            issued_at=report.issued_at,
            auditor=report.auditor,
            audited_at=report.audited_at,
            approver=report.approver,
            approved_at=report.approved_at,
            is_active=report.is_active,
            test_results=test_results,
            created_at=report.created_at,
        )
