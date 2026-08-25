from sqlalchemy.orm import Session
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from collections import defaultdict

from .base_service import BaseService
from ..models import (
    ReInspection,
    Batch,
    Sample,
    Retention,
    TestResult,
    TestItem,
    Arbitration,
    RegulatoryInspection,
    RegulatoryDifference,
    CrossBatchRiskRecord,
)
from ..schemas import (
    ReInspectionDiffStats,
    RetentionExpireStats,
    RiskLevelStats,
    CrossBatchRiskTrendQuery,
    CrossBatchRiskResponse,
    CrossBatchRiskSummary,
    CrossBatchRiskDetail,
    RegulatoryRiskType,
    RiskLevel,
    Judgment,
)
from ..exceptions import BatchNotFoundError


RISK_TYPE_DISPLAY = {
    "consecutive_fail": "连续不合格",
    "repeated_dispute": "同类争议反复",
    "destroyed_no_review": "留样销毁无法复核",
    "regulatory_difference": "监管抽检差异",
}


class StatsService(BaseService):
    def get_reinspection_diff_stats(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> ReInspectionDiffStats:
        query = self.db.query(ReInspection)

        if start_date:
            query = query.filter(ReInspection.created_at >= start_date)
        if end_date:
            query = query.filter(ReInspection.created_at <= end_date)

        total = query.count()

        with_diff = query.filter(ReInspection.difference_identified == True).count()
        without_diff = query.filter(ReInspection.difference_identified == False).count()

        pass_after = query.filter(ReInspection.final_judgment == "pass").count()
        fail_after = query.filter(ReInspection.final_judgment == "fail").count()

        difference_rate = (with_diff / total * 100) if total > 0 else 0.0

        return ReInspectionDiffStats(
            total_reinspections=total,
            with_difference=with_diff,
            without_difference=without_diff,
            pass_after_reinspection=pass_after,
            fail_after_reinspection=fail_after,
            difference_rate=round(difference_rate, 2),
        )

    def get_batch_quality_stats(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict:
        query = self.db.query(Batch)

        if start_date:
            query = query.filter(Batch.created_at >= start_date)
        if end_date:
            query = query.filter(Batch.created_at <= end_date)

        total = query.count()
        passed = query.filter(Batch.final_result == "pass").count()
        failed = query.filter(Batch.final_result == "fail").count()
        pending = query.filter(Batch.final_result == None).count()
        released = query.filter(Batch.released == True).count()
        reinspected = query.filter(Batch.status == "reinspecting").count()

        pass_rate = (passed / total * 100) if total > 0 else 0.0

        return {
            "total_batches": total,
            "passed": passed,
            "failed": failed,
            "pending": pending,
            "released": released,
            "reinspected": reinspected,
            "pass_rate": round(pass_rate, 2),
        }

    def get_reinspection_trend(
        self,
        days: int = 30,
    ) -> List[Dict]:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        trend = []
        for i in range(days + 1):
            day = start_date + timedelta(days=i)
            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)

            day_count = (
                self.db.query(ReInspection)
                .filter(
                    ReInspection.created_at >= day_start,
                    ReInspection.created_at <= day_end,
                )
                .count()
            )

            with_diff = (
                self.db.query(ReInspection)
                .filter(
                    ReInspection.created_at >= day_start,
                    ReInspection.created_at <= day_end,
                    ReInspection.difference_identified == True,
                )
                .count()
            )

            trend.append(
                {
                    "date": day.strftime("%Y-%m-%d"),
                    "total_reinspections": day_count,
                    "with_difference": with_diff,
                }
            )

        return trend

    def get_reinspection_by_reason(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Dict]:
        query = self.db.query(ReInspection)

        if start_date:
            query = query.filter(ReInspection.created_at >= start_date)
        if end_date:
            query = query.filter(ReInspection.created_at <= end_date)

        reinspections = query.all()

        reason_stats: Dict[str, int] = {}
        for ri in reinspections:
            reason = ri.reason or "未指定原因"
            if len(reason) > 30:
                reason = reason[:30] + "..."
            reason_stats[reason] = reason_stats.get(reason, 0) + 1

        return [
            {"reason": reason, "count": count}
            for reason, count in sorted(reason_stats.items(), key=lambda x: -x[1])
        ]

    def get_risk_level_stats(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> RiskLevelStats:
        query = self.db.query(Batch)

        if start_date:
            query = query.filter(Batch.created_at >= start_date)
        if end_date:
            query = query.filter(Batch.created_at <= end_date)

        total = query.count()
        low = query.filter(Batch.risk_level == "low").count()
        medium = query.filter(Batch.risk_level == "medium").count()
        high = query.filter(Batch.risk_level == "high").count()

        return RiskLevelStats(
            total_batches=total,
            low_risk=low,
            medium_risk=medium,
            high_risk=high,
            low_risk_rate=round((low / total * 100) if total > 0 else 0.0, 2),
            medium_risk_rate=round((medium / total * 100) if total > 0 else 0.0, 2),
            high_risk_rate=round((high / total * 100) if total > 0 else 0.0, 2),
        )

    def get_retention_expire_stats(self) -> RetentionExpireStats:
        now = datetime.now()
        seven_days_later = now + timedelta(days=7)
        thirty_days_later = now + timedelta(days=30)

        total_active = (
            self.db.query(Retention)
            .filter(Retention.destroyed == False)
            .count()
        )

        expired = (
            self.db.query(Retention)
            .filter(
                Retention.is_expired == True,
                Retention.destroyed == False,
            )
            .count()
        )

        expiring_7_days = (
            self.db.query(Retention)
            .filter(
                Retention.is_expired == False,
                Retention.destroyed == False,
                Retention.retention_end > now,
                Retention.retention_end <= seven_days_later,
            )
            .count()
        )

        expiring_30_days = (
            self.db.query(Retention)
            .filter(
                Retention.is_expired == False,
                Retention.destroyed == False,
                Retention.retention_end > now,
                Retention.retention_end <= thirty_days_later,
            )
            .count()
        )

        destroyed = self.db.query(Retention).filter(Retention.destroyed == True).count()

        return RetentionExpireStats(
            total_active=total_active,
            expired=expired,
            expiring_7_days=expiring_7_days,
            expiring_30_days=expiring_30_days,
            destroyed=destroyed,
        )

    def get_overall_stats(self) -> Dict:
        now = datetime.now()
        thirty_days_ago = now - timedelta(days=30)

        batch_stats = self.get_batch_quality_stats()
        reinspection_stats = self.get_reinspection_diff_stats()
        retention_stats = self.get_retention_expire_stats()
        risk_stats = self.get_risk_level_stats()
        trend = self.get_reinspection_trend(days=7)

        total_samples = self.db.query(Sample).count()
        retained_samples = self.db.query(Sample).filter(Sample.is_retained == True).count()
        destroyed_samples = self.db.query(Sample).filter(Sample.is_destroyed == True).count()

        return {
            "batch_stats": batch_stats,
            "reinspection_stats": reinspection_stats,
            "retention_stats": retention_stats,
            "risk_level_stats": risk_stats,
            "sample_stats": {
                "total": total_samples,
                "retained": retained_samples,
                "destroyed": destroyed_samples,
            },
            "weekly_trend": trend,
            "generated_at": now,
        }

    def _identify_consecutive_fail_risk(
        self, start_date: Optional[datetime], end_date: Optional[datetime]
    ) -> List[CrossBatchRiskRecord]:
        records: List[CrossBatchRiskRecord] = []

        batch_query = self.db.query(Batch)
        if start_date:
            batch_query = batch_query.filter(Batch.production_date >= start_date)
        if end_date:
            batch_query = batch_query.filter(Batch.production_date <= end_date)
        batches = batch_query.order_by(Batch.production_date).all()

        def check_consecutive(grouped_batches: List[Batch], scope_name: str, scope_value: str):
            if len(grouped_batches) < 2:
                return
            sorted_batches = sorted(grouped_batches, key=lambda b: b.production_date)
            max_consecutive = 0
            current_consecutive = 0
            consecutive_ids: List[int] = []
            current_ids: List[int] = []

            for b in sorted_batches:
                if b.final_result == Judgment.FAIL.value:
                    current_consecutive += 1
                    current_ids.append(b.id)
                    if current_consecutive > max_consecutive:
                        max_consecutive = current_consecutive
                        consecutive_ids = list(current_ids)
                else:
                    current_consecutive = 0
                    current_ids = []

            if max_consecutive >= 2:
                risk_level = RiskLevel.HIGH.value if max_consecutive >= 3 else RiskLevel.MEDIUM.value
                records.append(
                    CrossBatchRiskRecord(
                        record_date=datetime.now(),
                        risk_type=RegulatoryRiskType.CONSECUTIVE_FAIL.value,
                        risk_level=risk_level,
                        scope_dimension=scope_name,
                        scope_value=scope_value,
                        affected_batch_count=len(consecutive_ids),
                        affected_batch_ids=consecutive_ids,
                        description=f"连续 {max_consecutive} 个批次不合格",
                        detail_data={"consecutive_count": max_consecutive},
                    )
                )

        by_product: Dict[str, List[Batch]] = defaultdict(list)
        by_line: Dict[str, List[Batch]] = defaultdict(list)
        for b in batches:
            if b.product_name:
                by_product[b.product_name].append(b)
            if b.production_line:
                by_line[b.production_line].append(b)

        for product_name, b_list in by_product.items():
            check_consecutive(b_list, "product", product_name)
        for line_name, b_list in by_line.items():
            check_consecutive(b_list, "line", line_name)

        fail_item_batches: Dict[int, List[Batch]] = defaultdict(list)
        for b in batches:
            sample_ids = [s.id for s in b.samples]
            if not sample_ids:
                continue
            fail_results = (
                self.db.query(TestResult)
                .filter(
                    TestResult.sample_id.in_(sample_ids),
                    TestResult.judgment == Judgment.FAIL.value,
                )
                .all()
            )
            for tr in fail_results:
                fail_item_batches[tr.test_item_id].append(b)

        for item_id, b_list in fail_item_batches.items():
            unique_batches = list({b.id: b for b in b_list}.values())
            if len(unique_batches) >= 2:
                ti = self.db.query(TestItem).filter(TestItem.id == item_id).first()
                item_name = ti.item_name if ti else f"检测项{item_id}"
                records.append(
                    CrossBatchRiskRecord(
                        record_date=datetime.now(),
                        risk_type=RegulatoryRiskType.CONSECUTIVE_FAIL.value,
                        risk_level=RiskLevel.MEDIUM.value if len(unique_batches) >= 3 else RiskLevel.LOW.value,
                        scope_dimension="test_item",
                        scope_value=item_name,
                        affected_batch_count=len(unique_batches),
                        affected_batch_ids=[b.id for b in unique_batches],
                        description=f"检测项{item_name}在 {len(unique_batches)} 个批次中不合格",
                        detail_data={"item_id": item_id, "item_name": item_name},
                    )
                )

        return records

    def _identify_repeated_dispute_risk(
        self, start_date: Optional[datetime], end_date: Optional[datetime]
    ) -> List[CrossBatchRiskRecord]:
        records: List[CrossBatchRiskRecord] = []

        arb_query = self.db.query(Arbitration)
        if start_date:
            arb_query = arb_query.filter(Arbitration.created_at >= start_date)
        if end_date:
            arb_query = arb_query.filter(Arbitration.created_at <= end_date)
        arbitrations = arb_query.all()

        if len(arbitrations) < 2:
            return records

        by_product: Dict[str, List[Arbitration]] = defaultdict(list)
        by_line: Dict[str, List[Arbitration]] = defaultdict(list)
        for a in arbitrations:
            batch = a.batch
            if batch:
                if batch.product_name:
                    by_product[batch.product_name].append(a)
                if batch.production_line:
                    by_line[batch.production_line].append(a)

        for product_name, a_list in by_product.items():
            if len(a_list) >= 2:
                batch_ids = list({a.batch_id for a in a_list if a.batch_id})
                records.append(
                    CrossBatchRiskRecord(
                        record_date=datetime.now(),
                        risk_type=RegulatoryRiskType.REPEATED_DISPUTE.value,
                        risk_level=RiskLevel.HIGH.value if len(a_list) >= 3 else RiskLevel.MEDIUM.value,
                        scope_dimension="product",
                        scope_value=product_name,
                        affected_batch_count=len(batch_ids),
                        affected_batch_ids=batch_ids,
                        description=f"产品{product_name}出现 {len(a_list)} 次仲裁争议",
                        detail_data={"arbitration_count": len(a_list)},
                    )
                )

        for line_name, a_list in by_line.items():
            if len(a_list) >= 2:
                batch_ids = list({a.batch_id for a in a_list if a.batch_id})
                records.append(
                    CrossBatchRiskRecord(
                        record_date=datetime.now(),
                        risk_type=RegulatoryRiskType.REPEATED_DISPUTE.value,
                        risk_level=RiskLevel.HIGH.value if len(a_list) >= 3 else RiskLevel.MEDIUM.value,
                        scope_dimension="line",
                        scope_value=line_name,
                        affected_batch_count=len(batch_ids),
                        affected_batch_ids=batch_ids,
                        description=f"生产线{line_name}出现 {len(a_list)} 次仲裁争议",
                        detail_data={"arbitration_count": len(a_list)},
                    )
                )

        reinspection_query = self.db.query(ReInspection).filter(ReInspection.difference_identified == True)
        if start_date:
            reinspection_query = reinspection_query.filter(ReInspection.created_at >= start_date)
        if end_date:
            reinspection_query = reinspection_query.filter(ReInspection.created_at <= end_date)
        reinspections = reinspection_query.all()

        if len(reinspections) >= 2:
            diff_by_product: Dict[str, List[ReInspection]] = defaultdict(list)
            for ri in reinspections:
                sample = ri.original_sample
                if sample and sample.batch:
                    if sample.batch.product_name:
                        diff_by_product[sample.batch.product_name].append(ri)

            for product_name, ri_list in diff_by_product.items():
                if len(ri_list) >= 2:
                    batch_ids = list({ri.original_sample.batch_id for ri in ri_list if ri.original_sample and ri.original_sample.batch})
                    records.append(
                        CrossBatchRiskRecord(
                            record_date=datetime.now(),
                            risk_type=RegulatoryRiskType.REPEATED_DISPUTE.value,
                            risk_level=RiskLevel.MEDIUM.value if len(ri_list) >= 3 else RiskLevel.LOW.value,
                            scope_dimension="product",
                            scope_value=product_name,
                            affected_batch_count=len(batch_ids),
                            affected_batch_ids=batch_ids,
                            description=f"产品{product_name}出现 {len(ri_list)} 次复检差异",
                            detail_data={"reinspection_diff_count": len(ri_list)},
                        )
                    )

        return records

    def _identify_destroyed_no_review_risk(
        self, start_date: Optional[datetime], end_date: Optional[datetime]
    ) -> List[CrossBatchRiskRecord]:
        records: List[CrossBatchRiskRecord] = []

        retention_query = self.db.query(Retention).filter(Retention.destroyed == True)
        if start_date:
            retention_query = retention_query.filter(Retention.destroyed_at >= start_date)
        if end_date:
            retention_query = retention_query.filter(Retention.destroyed_at <= end_date)
        destroyed_retentions = retention_query.all()

        affected_batches: Dict[str, List[int]] = defaultdict(list)
        for ret in destroyed_retentions:
            sample = ret.sample
            if sample and sample.batch:
                batch = sample.batch
                if batch.final_result == Judgment.FAIL.value or batch.risk_level in [RiskLevel.MEDIUM.value, RiskLevel.HIGH.value]:
                    if batch.product_name:
                        affected_batches[batch.product_name].append(batch.id)

        for product_name, batch_ids in affected_batches.items():
            unique_ids = list(set(batch_ids))
            if len(unique_ids) >= 1:
                records.append(
                    CrossBatchRiskRecord(
                        record_date=datetime.now(),
                        risk_type=RegulatoryRiskType.DESTROYED_NO_REVIEW.value,
                        risk_level=RiskLevel.HIGH.value if len(unique_ids) >= 2 else RiskLevel.MEDIUM.value,
                        scope_dimension="product",
                        scope_value=product_name,
                        affected_batch_count=len(unique_ids),
                        affected_batch_ids=unique_ids,
                        description=f"产品{product_name}有 {len(unique_ids)} 个存在质量问题批次的留样已销毁，无法复核",
                        detail_data={"destroyed_count": len(unique_ids)},
                    )
                )

        pending_diffs = (
            self.db.query(RegulatoryDifference)
            .filter(RegulatoryDifference.handling_status != "closed")
            .all()
        )
        for diff in pending_diffs:
            batch = diff.batch
            if not batch:
                continue
            sample_ids = [s.id for s in batch.samples]
            if not sample_ids:
                continue
            destroyed = (
                self.db.query(Retention)
                .filter(
                    Retention.sample_id.in_(sample_ids),
                    Retention.destroyed == True,
                )
                .first()
            )
            if destroyed:
                records.append(
                    CrossBatchRiskRecord(
                        record_date=datetime.now(),
                        risk_type=RegulatoryRiskType.DESTROYED_NO_REVIEW.value,
                        risk_level=RiskLevel.HIGH.value,
                        scope_dimension="batch",
                        scope_value=batch.batch_no,
                        affected_batch_count=1,
                        affected_batch_ids=[batch.id],
                        description=f"批次{batch.batch_no}存在未关闭监管差异但留样已销毁，无法复核",
                        detail_data={"difference_id": diff.id, "difference_code": diff.difference_code},
                    )
                )

        return records

    def _identify_regulatory_difference_risk(
        self, start_date: Optional[datetime], end_date: Optional[datetime]
    ) -> List[CrossBatchRiskRecord]:
        records: List[CrossBatchRiskRecord] = []

        diff_query = self.db.query(RegulatoryDifference)
        if start_date:
            diff_query = diff_query.filter(RegulatoryDifference.created_at >= start_date)
        if end_date:
            diff_query = diff_query.filter(RegulatoryDifference.created_at <= end_date)
        differences = diff_query.all()

        if not differences:
            return records

        by_product: Dict[str, List[RegulatoryDifference]] = defaultdict(list)
        by_line: Dict[str, List[RegulatoryDifference]] = defaultdict(list)
        for d in differences:
            batch = d.batch
            if batch:
                if batch.product_name:
                    by_product[batch.product_name].append(d)
                if batch.production_line:
                    by_line[batch.production_line].append(d)

        for product_name, d_list in by_product.items():
            batch_ids = list({d.batch_id for d in d_list if d.batch_id})
            if len(d_list) >= 1:
                records.append(
                    CrossBatchRiskRecord(
                        record_date=datetime.now(),
                        risk_type=RegulatoryRiskType.REGULATORY_DIFFERENCE.value,
                        risk_level=RiskLevel.HIGH.value if len(d_list) >= 2 else RiskLevel.MEDIUM.value,
                        scope_dimension="product",
                        scope_value=product_name,
                        affected_batch_count=len(batch_ids),
                        affected_batch_ids=batch_ids,
                        description=f"产品{product_name}出现 {len(d_list)} 次监管抽检差异",
                        detail_data={"difference_count": len(d_list)},
                    )
                )

        for line_name, d_list in by_line.items():
            batch_ids = list({d.batch_id for d in d_list if d.batch_id})
            if len(d_list) >= 1:
                records.append(
                    CrossBatchRiskRecord(
                        record_date=datetime.now(),
                        risk_type=RegulatoryRiskType.REGULATORY_DIFFERENCE.value,
                        risk_level=RiskLevel.HIGH.value if len(d_list) >= 2 else RiskLevel.MEDIUM.value,
                        scope_dimension="line",
                        scope_value=line_name,
                        affected_batch_count=len(batch_ids),
                        affected_batch_ids=batch_ids,
                        description=f"生产线{line_name}出现 {len(d_list)} 次监管抽检差异",
                        detail_data={"difference_count": len(d_list)},
                    )
                )

        return records

    def analyze_cross_batch_risks(
        self, query_params: CrossBatchRiskTrendQuery
    ) -> CrossBatchRiskResponse:
        start_date = query_params.start_date
        end_date = query_params.end_date

        all_risks: List[CrossBatchRiskRecord] = []

        if not query_params.risk_type or query_params.risk_type == RegulatoryRiskType.CONSECUTIVE_FAIL.value:
            all_risks.extend(self._identify_consecutive_fail_risk(start_date, end_date))

        if not query_params.risk_type or query_params.risk_type == RegulatoryRiskType.REPEATED_DISPUTE.value:
            all_risks.extend(self._identify_repeated_dispute_risk(start_date, end_date))

        if not query_params.risk_type or query_params.risk_type == RegulatoryRiskType.DESTROYED_NO_REVIEW.value:
            all_risks.extend(self._identify_destroyed_no_review_risk(start_date, end_date))

        if not query_params.risk_type or query_params.risk_type == RegulatoryRiskType.REGULATORY_DIFFERENCE.value:
            all_risks.extend(self._identify_regulatory_difference_risk(start_date, end_date))

        if query_params.scope_dimension:
            all_risks = [r for r in all_risks if r.scope_dimension == query_params.scope_dimension]
        if query_params.scope_value:
            all_risks = [r for r in all_risks if r.scope_value and query_params.scope_value in r.scope_value]

        for r in all_risks:
            existing = (
                self.db.query(CrossBatchRiskRecord)
                .filter(
                    CrossBatchRiskRecord.risk_type == r.risk_type,
                    CrossBatchRiskRecord.scope_dimension == r.scope_dimension,
                    CrossBatchRiskRecord.scope_value == r.scope_value,
                    CrossBatchRiskRecord.affected_batch_count == r.affected_batch_count,
                )
                .first()
            )
            if not existing:
                self.db.add(r)
        self.db.commit()

        risk_type_summary: Dict[str, Dict] = {}
        for r in all_risks:
            rt = r.risk_type
            if rt not in risk_type_summary:
                risk_type_summary[rt] = {
                    "risk_type": rt,
                    "risk_type_display": RISK_TYPE_DISPLAY.get(rt, rt),
                    "affected_count": 0,
                    "high_risk_count": 0,
                    "medium_risk_count": 0,
                    "low_risk_count": 0,
                }
            risk_type_summary[rt]["affected_count"] += r.affected_batch_count
            if r.risk_level == RiskLevel.HIGH.value:
                risk_type_summary[rt]["high_risk_count"] += 1
            elif r.risk_level == RiskLevel.MEDIUM.value:
                risk_type_summary[rt]["medium_risk_count"] += 1
            elif r.risk_level == RiskLevel.LOW.value:
                risk_type_summary[rt]["low_risk_count"] += 1

        summaries = [CrossBatchRiskSummary(**v) for v in risk_type_summary.values()]

        details = [
            CrossBatchRiskDetail(
                id=r.id or 0,
                record_date=r.record_date or datetime.now(),
                risk_type=r.risk_type,
                risk_type_display=RISK_TYPE_DISPLAY.get(r.risk_type, r.risk_type),
                risk_level=r.risk_level,
                scope_dimension=r.scope_dimension,
                scope_value=r.scope_value,
                affected_batch_count=r.affected_batch_count or 0,
                affected_batch_ids=r.affected_batch_ids,
                description=r.description,
                detail_data=r.detail_data,
                generated_at=r.generated_at or datetime.now(),
            )
            for r in all_risks
        ]
        details.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.risk_level, 3))

        return CrossBatchRiskResponse(
            summary=summaries,
            details=details,
            generated_at=datetime.now(),
        )

    def get_risk_trend_by_product(
        self, days: int = 30
    ) -> List[Dict]:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        products = (
            self.db.query(Batch.product_name)
            .filter(Batch.product_name.isnot(None))
            .distinct()
            .all()
        )
        product_names = [p[0] for p in products if p[0]]

        trend = []
        for product_name in product_names:
            product_batches = (
                self.db.query(Batch)
                .filter(
                    Batch.product_name == product_name,
                    Batch.production_date >= start_date,
                    Batch.production_date <= end_date,
                )
                .order_by(Batch.production_date)
                .all()
            )

            total = len(product_batches)
            passed = sum(1 for b in product_batches if b.final_result == Judgment.PASS.value)
            failed = sum(1 for b in product_batches if b.final_result == Judgment.FAIL.value)
            high_risk = sum(1 for b in product_batches if b.risk_level == RiskLevel.HIGH.value)
            medium_risk = sum(1 for b in product_batches if b.risk_level == RiskLevel.MEDIUM.value)
            frozen = sum(1 for b in product_batches if b.frozen)
            regulatory_diffs = (
                self.db.query(RegulatoryDifference)
                .join(Batch, Batch.id == RegulatoryDifference.batch_id)
                .filter(Batch.product_name == product_name)
                .count()
            )

            trend.append({
                "product_name": product_name,
                "total_batches": total,
                "passed": passed,
                "failed": failed,
                "pass_rate": round(passed / total * 100, 2) if total > 0 else 0.0,
                "high_risk": high_risk,
                "medium_risk": medium_risk,
                "frozen": frozen,
                "regulatory_differences": regulatory_diffs,
            })

        trend.sort(key=lambda x: x["failed"], reverse=True)
        return trend

    def get_risk_trend_by_test_item(
        self, days: int = 30
    ) -> List[Dict]:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        batch_ids = [
            b.id for b in self.db.query(Batch).filter(
                Batch.production_date >= start_date,
                Batch.production_date <= end_date,
            ).all()
        ]
        if not batch_ids:
            return []

        sample_ids = [
            s.id for s in self.db.query(Sample).filter(Sample.batch_id.in_(batch_ids)).all()
        ]
        if not sample_ids:
            return []

        fail_results = (
            self.db.query(TestResult)
            .filter(
                TestResult.sample_id.in_(sample_ids),
                TestResult.judgment == Judgment.FAIL.value,
            )
            .all()
        )

        item_stats: Dict[int, Dict] = {}
        for tr in fail_results:
            if tr.test_item_id not in item_stats:
                ti = self.db.query(TestItem).filter(TestItem.id == tr.test_item_id).first()
                item_stats[tr.test_item_id] = {
                    "test_item_id": tr.test_item_id,
                    "test_item_code": ti.item_code if ti else "",
                    "test_item_name": ti.item_name if ti else "",
                    "fail_count": 0,
                    "affected_batches": set(),
                }
            item_stats[tr.test_item_id]["fail_count"] += 1
            sample = self.db.query(Sample).filter(Sample.id == tr.sample_id).first()
            if sample and sample.batch_id:
                item_stats[tr.test_item_id]["affected_batches"].add(sample.batch_id)

        result = []
        for stat in item_stats.values():
            affected_count = len(stat["affected_batches"])
            result.append({
                "test_item_id": stat["test_item_id"],
                "test_item_code": stat["test_item_code"],
                "test_item_name": stat["test_item_name"],
                "fail_count": stat["fail_count"],
                "affected_batch_count": affected_count,
                "risk_level": RiskLevel.HIGH.value if affected_count >= 3 else RiskLevel.MEDIUM.value if affected_count >= 2 else RiskLevel.LOW.value,
            })

        result.sort(key=lambda x: x["fail_count"], reverse=True)
        return result

    def get_regulatory_inspection_stats(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> Dict:
        query = self.db.query(RegulatoryInspection)
        if start_date:
            query = query.filter(RegulatoryInspection.inspection_date >= start_date)
        if end_date:
            query = query.filter(RegulatoryInspection.inspection_date <= end_date)

        total = query.count()
        with_diff = query.filter(RegulatoryInspection.difference_generated == True).count()
        consistent = total - with_diff

        diff_query = self.db.query(RegulatoryDifference)
        if start_date:
            diff_query = diff_query.filter(RegulatoryDifference.created_at >= start_date)
        if end_date:
            diff_query = diff_query.filter(RegulatoryDifference.created_at <= end_date)

        total_diffs = diff_query.count()
        pending = diff_query.filter(RegulatoryDifference.handling_status == "pending").count()
        processing = diff_query.filter(RegulatoryDifference.handling_status == "processing").count()
        closed = diff_query.filter(RegulatoryDifference.handling_status == "closed").count()

        frozen_batches = self.db.query(Batch).filter(Batch.frozen == True).count()
        revoked_releases = self.db.query(Batch).filter(Batch.release_revoked == True).count()

        return {
            "inspection_stats": {
                "total": total,
                "with_difference": with_diff,
                "consistent": consistent,
                "difference_rate": round(with_diff / total * 100, 2) if total > 0 else 0.0,
            },
            "difference_stats": {
                "total": total_diffs,
                "pending": pending,
                "processing": processing,
                "closed": closed,
            },
            "batch_status": {
                "frozen": frozen_batches,
                "release_revoked": revoked_releases,
            },
            "generated_at": datetime.now(),
        }
