from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional

from .base_service import BaseService
from .regulatory_service import RegulatoryService
from .stats_service import StatsService
from ..models import (
    Batch,
    Sample,
    Report,
    Retention,
    ReInspection,
    TestResult,
    Arbitration,
    RegulatoryInspection,
    RegulatoryDifference,
)
from ..schemas import (
    BatchCreate,
    BatchUpdate,
    BatchRelease,
    BatchQualityArchive,
    BatchResponse,
    SampleResponse,
    ReportResponse,
    RetentionResponse,
    ReInspectionResponse,
    ArbitrationResponse,
    RegulatoryInspectionResponse,
    RegulatoryDifferenceResponse,
    TestResultResponse,
    Judgment,
    BatchStatus,
    RiskLevel,
    ReportType,
    CrossBatchRiskTrendQuery,
)
from ..exceptions import (
    BatchNotFoundError,
    ReleaseNotAllowedError,
    InvalidStatusError,
    ArbitrationPendingError,
    BatchFrozenError,
)


class BatchService(BaseService):
    def create_batch(self, data: BatchCreate) -> Batch:
        batch = Batch(
            batch_no=data.batch_no,
            product_name=data.product_name,
            production_date=self.parse_datetime(data.production_date),
            quantity=data.quantity,
            production_line=data.production_line,
            remark=data.remark,
            status=BatchStatus.PENDING.value,
        )
        self.db.add(batch)
        self.db.commit()
        self.db.refresh(batch)
        return batch

    def get_batch(self, batch_id: int) -> Batch:
        batch = self.db.query(Batch).filter(Batch.id == batch_id).first()
        if not batch:
            raise BatchNotFoundError(batch_id=batch_id)
        return batch

    def get_batch_by_no(self, batch_no: str) -> Batch:
        batch = self.db.query(Batch).filter(Batch.batch_no == batch_no).first()
        if not batch:
            raise BatchNotFoundError(batch_no=batch_no)
        return batch

    def list_batches(self, skip: int = 0, limit: int = 100, status: Optional[str] = None) -> List[Batch]:
        query = self.db.query(Batch)
        if status:
            query = query.filter(Batch.status == status)
        return query.order_by(Batch.created_at.desc()).offset(skip).limit(limit).all()

    def update_batch(self, batch_id: int, data: BatchUpdate) -> Batch:
        batch = self.get_batch(batch_id)
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key == "production_date" and value:
                value = self.parse_datetime(value)
            setattr(batch, key, value)
        batch.updated_at = datetime.now()
        self.db.commit()
        self.db.refresh(batch)
        return batch

    def update_batch_status(self, batch_id: int, status: str) -> Batch:
        batch = self.get_batch(batch_id)
        batch.status = status
        batch.updated_at = datetime.now()
        self.db.commit()
        self.db.refresh(batch)
        return batch

    def calculate_risk_level(self, batch_id: int) -> Batch:
        batch = self.get_batch(batch_id)
        sample_ids = [s.id for s in batch.samples]

        risk_score = 0.0

        fail_count = (
            self.db.query(TestResult)
            .filter(
                TestResult.sample_id.in_(sample_ids),
                TestResult.judgment == Judgment.FAIL.value,
            )
            .count()
        )
        risk_score += fail_count * 20.0

        reinspections = (
            self.db.query(ReInspection)
            .filter(ReInspection.original_sample_id.in_(sample_ids))
            .all()
        )
        for ri in reinspections:
            original_results = (
                self.db.query(TestResult)
                .filter(
                    TestResult.sample_id == ri.original_sample_id,
                    TestResult.is_reinspection == False,
                )
                .all()
            )
            re_results = (
                self.db.query(TestResult)
                .filter(
                    TestResult.sample_id == ri.re_sample_id,
                    TestResult.reinspection_id == ri.id,
                )
                .all()
            )

            orig_map = {tr.test_item_id: tr for tr in original_results}
            for re_tr in re_results:
                orig_tr = orig_map.get(re_tr.test_item_id)
                if orig_tr and orig_tr.numeric_value is not None and re_tr.numeric_value is not None:
                    if orig_tr.numeric_value != 0:
                        diff_pct = abs(re_tr.numeric_value - orig_tr.numeric_value) / abs(orig_tr.numeric_value) * 100
                        if diff_pct > 20:
                            risk_score += 25.0
                        elif diff_pct > 10:
                            risk_score += 15.0
                        elif diff_pct > 5:
                            risk_score += 5.0

        retention = (
            self.db.query(Retention)
            .filter(Retention.sample_id.in_(sample_ids))
            .first()
        )
        if retention and retention.destroyed:
            risk_score += 15.0

        historical_fail_count = (
            self.db.query(Batch)
            .filter(
                Batch.product_name == batch.product_name,
                Batch.id != batch.id,
                Batch.final_result == Judgment.FAIL.value,
            )
            .count()
        )
        risk_score += historical_fail_count * 10.0

        if risk_score <= 30:
            risk_level = RiskLevel.LOW.value
        elif risk_score <= 70:
            risk_level = RiskLevel.MEDIUM.value
        else:
            risk_level = RiskLevel.HIGH.value

        batch.risk_score = round(risk_score, 2)
        batch.risk_level = risk_level
        batch.updated_at = datetime.now()

        self.db.commit()
        self.db.refresh(batch)
        return batch

    def validate_release(self, batch: Batch) -> None:
        if batch.frozen:
            raise BatchFrozenError(batch.batch_no, batch.frozen_reason)

        if batch.status not in [BatchStatus.COMPLETED.value, BatchStatus.REJECTED.value, BatchStatus.JUDGING.value]:
            raise InvalidStatusError(batch.status, "completed/rejected/judging")

        pending_arbitration = (
            self.db.query(Arbitration)
            .filter(
                Arbitration.batch_id == batch.id,
                Arbitration.status != "completed",
            )
            .first()
        )
        if pending_arbitration:
            raise ArbitrationPendingError(batch.batch_no)

        pending_reg_diff = (
            self.db.query(RegulatoryDifference)
            .filter(
                RegulatoryDifference.batch_id == batch.id,
                RegulatoryDifference.handling_status != "closed",
            )
            .first()
        )
        if pending_reg_diff:
            raise ReleaseNotAllowedError(
                f"批次存在未关闭的监管差异单 {pending_reg_diff.difference_code}，无法放行"
            )

        active_report = (
            self.db.query(Report)
            .filter(
                Report.batch_id == batch.id,
                Report.is_active == True,
            )
            .order_by(Report.created_at.desc())
            .first()
        )

        if not active_report:
            raise ReleaseNotAllowedError("批次没有有效的检测报告")

        if active_report.overall_judgment == Judgment.FAIL.value:
            pending_reinspection = (
                self.db.query(ReInspection)
                .filter(
                    ReInspection.original_sample_id.in_(
                        self.db.query(Sample.id).filter(Sample.batch_id == batch.id)
                    ),
                    ReInspection.status != "confirmed",
                )
                .first()
            )
            if pending_reinspection:
                raise ReleaseNotAllowedError("存在未确认的复检，无法放行")

            if batch.final_result != Judgment.PASS.value:
                raise ReleaseNotAllowedError("批次判定不合格，无法直接放行")

    def release_batch(self, batch_id: int, data: BatchRelease) -> Batch:
        batch = self.get_batch(batch_id)

        self.validate_release(batch)

        batch.released = True
        batch.released_at = datetime.now()
        batch.released_by = data.released_by
        if data.remark:
            batch.remark = (batch.remark or "") + f"\n放行备注: {data.remark}"
        batch.updated_at = datetime.now()

        self.db.commit()
        self.db.refresh(batch)
        return batch

    def get_quality_archive(self, batch_id: int) -> BatchQualityArchive:
        from .arbitration_service import ArbitrationService

        batch = self.get_batch(batch_id)

        samples = self.db.query(Sample).filter(Sample.batch_id == batch_id).all()
        sample_ids = [s.id for s in samples]

        original_report = (
            self.db.query(Report)
            .filter(
                Report.batch_id == batch_id,
                Report.report_type == "original",
            )
            .first()
        )

        reinspection_reports = (
            self.db.query(Report)
            .filter(
                Report.batch_id == batch_id,
                Report.report_type == "reinspection",
            )
            .order_by(Report.created_at)
            .all()
        )

        final_report = (
            self.db.query(Report)
            .filter(
                Report.batch_id == batch_id,
                Report.report_type == "final",
            )
            .first()
        )

        arbitration_reports = (
            self.db.query(Report)
            .filter(
                Report.batch_id == batch_id,
                Report.report_type == "arbitration",
            )
            .order_by(Report.created_at)
            .all()
        )

        retention = None
        if sample_ids:
            retention = (
                self.db.query(Retention)
                .filter(Retention.sample_id.in_(sample_ids))
                .first()
            )

        reinspections = (
            self.db.query(ReInspection)
            .filter(ReInspection.original_sample_id.in_(sample_ids))
            .order_by(ReInspection.created_at)
            .all()
        )

        arbitrations = (
            self.db.query(Arbitration)
            .filter(Arbitration.batch_id == batch_id)
            .order_by(Arbitration.created_at)
            .all()
        )

        regulatory_inspections = (
            self.db.query(RegulatoryInspection)
            .filter(RegulatoryInspection.batch_id == batch_id)
            .order_by(RegulatoryInspection.created_at)
            .all()
        )

        regulatory_differences = (
            self.db.query(RegulatoryDifference)
            .filter(RegulatoryDifference.batch_id == batch_id)
            .order_by(RegulatoryDifference.created_at)
            .all()
        )

        arbitration_service = ArbitrationService(self.db)
        regulatory_service = RegulatoryService(self.db)
        stats_service = StatsService(self.db)

        risk_summary = stats_service.analyze_cross_batch_risks(
            CrossBatchRiskTrendQuery(
                scope_dimension="product",
                scope_value=batch.product_name,
            )
        )

        return BatchQualityArchive(
            batch=BatchResponse.model_validate(batch),
            samples=[self._to_sample_response(s) for s in samples],
            original_report=self._to_report_response(original_report) if original_report else None,
            reinspection_reports=[self._to_report_response(r) for r in reinspection_reports],
            final_report=self._to_report_response(final_report) if final_report else None,
            arbitration_reports=[self._to_report_response(r) for r in arbitration_reports],
            retention=self._to_retention_response(retention) if retention else None,
            reinspections=[self._to_reinspection_response(r) for r in reinspections],
            arbitrations=[arbitration_service.to_response(a) for a in arbitrations],
            regulatory_inspections=[regulatory_service.to_inspection_response(ri) for ri in regulatory_inspections],
            regulatory_differences=[regulatory_service.to_difference_response(rd) for rd in regulatory_differences],
            risk_summary=risk_summary,
        )

    def _to_sample_response(self, sample: Sample) -> SampleResponse:
        location_code = sample.retention_location.location_code if sample.retention_location else None
        return SampleResponse(
            id=sample.id,
            sample_code=sample.sample_code,
            batch_id=sample.batch_id,
            batch_no=sample.batch.batch_no,
            sampling_time=sample.sampling_time,
            sampling_person=sample.sampling_person,
            sample_type=sample.sample_type,
            status=sample.status,
            is_retained=sample.is_retained,
            is_destroyed=sample.is_destroyed,
            retention_location=location_code,
            created_at=sample.created_at,
        )

    def _to_report_response(self, report: Report) -> ReportResponse:
        test_results = []
        for tr in report.sample.test_results:
            if tr.reinspection_id and report.report_type == "reinspection":
                pass
            elif not tr.reinspection_id and report.report_type == "original":
                pass
            elif report.report_type == "final":
                pass
            else:
                continue

            test_results.append(
                TestResultResponse(
                    id=tr.id,
                    sample_id=tr.sample_id,
                    sample_code=tr.sample.sample_code,
                    test_item_id=tr.test_item_id,
                    test_item_code=tr.test_item.item_code,
                    test_item_name=tr.test_item.item_name,
                    is_reinspection=tr.is_reinspection,
                    test_value=tr.test_value,
                    numeric_value=tr.numeric_value,
                    tester=tr.tester,
                    test_time=tr.test_time,
                    instrument=tr.instrument,
                    judgment=tr.judgment,
                    standard_value=tr.test_item.standard_value,
                    lower_limit=tr.test_item.lower_limit,
                    upper_limit=tr.test_item.upper_limit,
                    unit=tr.test_item.unit,
                    remark=tr.remark,
                    created_at=tr.created_at,
                )
            )

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

    def _to_retention_response(self, retention: Retention) -> RetentionResponse:
        return RetentionResponse(
            id=retention.id,
            sample_id=retention.sample_id,
            sample_code=retention.sample.sample_code,
            location_id=retention.location_id,
            location_code=retention.location.location_code,
            retention_start=retention.retention_start,
            retention_end=retention.retention_end,
            retention_period_days=retention.retention_period_days,
            status=retention.status,
            is_expired=retention.is_expired,
            destroyed=retention.destroyed,
            destroyed_at=retention.destroyed_at,
            created_at=retention.created_at,
        )

    def _to_reinspection_response(self, reinspection: ReInspection) -> ReInspectionResponse:
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
