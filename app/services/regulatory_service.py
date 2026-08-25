from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional

from .base_service import BaseService
from ..models import (
    RegulatoryInspection,
    RegulatoryInspectionItem,
    RegulatoryDifference,
    Batch,
    Sample,
    Report,
    TestResult,
    TestItem,
)
from ..schemas import (
    RegulatoryInspectionCreate,
    RegulatoryInspectionUpdate,
    RegulatoryInspectionResponse,
    RegulatoryInspectionItemResponse,
    RegulatoryDifferenceResponse,
    RegulatoryDifferenceProcess,
    RegulatoryDifferenceClose,
    BatchFreezeRequest,
    BatchUnfreezeRequest,
    ReleaseRevokeRequest,
    RegulatoryInspectionStatus,
    RegulatoryDifferenceStatus,
    Judgment,
    ReportType,
)
from ..exceptions import (
    BatchNotFoundError,
    RegulatoryInspectionNotFoundError,
    RegulatoryDifferenceNotFoundError,
    BatchFrozenError,
    BatchNotFrozenError,
    BatchNotReleasedError,
    InspectionAlreadyConfirmedError,
    ReleaseNotAllowedError,
)


class RegulatoryService(BaseService):
    def _generate_inspection_code(self) -> str:
        code = self.generate_code("RI")
        while self.db.query(RegulatoryInspection).filter(RegulatoryInspection.inspection_code == code).first():
            code = self.generate_code("RI")
        return code

    def _generate_difference_code(self) -> str:
        code = self.generate_code("RD")
        while self.db.query(RegulatoryDifference).filter(RegulatoryDifference.difference_code == code).first():
            code = self.generate_code("RD")
        return code

    def _get_enterprise_test_result(self, sample_id: int, test_item_id: int) -> Optional[TestResult]:
        return (
            self.db.query(TestResult)
            .filter(
                TestResult.sample_id == sample_id,
                TestResult.test_item_id == test_item_id,
            )
            .order_by(TestResult.created_at.desc())
            .first()
        )

    def _get_active_report_for_batch(self, batch_id: int) -> Optional[Report]:
        return (
            self.db.query(Report)
            .filter(
                Report.batch_id == batch_id,
                Report.is_active == True,
            )
            .order_by(Report.created_at.desc())
            .first()
        )

    def create_inspection(self, data: RegulatoryInspectionCreate) -> RegulatoryInspection:
        batch = self.db.query(Batch).filter(Batch.id == data.batch_id).first()
        if not batch:
            raise BatchNotFoundError(batch_id=data.batch_id)

        inspection_code = self._generate_inspection_code()
        inspection = RegulatoryInspection(
            inspection_code=inspection_code,
            batch_id=data.batch_id,
            sample_id=data.sample_id,
            original_report_id=data.original_report_id,
            reinspection_report_id=data.reinspection_report_id,
            arbitration_report_id=data.arbitration_report_id,
            inspection_agency=data.inspection_agency,
            inspector=data.inspector,
            inspection_date=self.parse_datetime(data.inspection_date),
            inspection_type=data.inspection_type or "spot_check",
            inspection_basis=data.inspection_basis,
            sampling_location=data.sampling_location,
            overall_conclusion=data.overall_conclusion,
            inspection_remark=data.inspection_remark,
            created_by=data.created_by,
            status=RegulatoryInspectionStatus.DRAFT.value,
        )
        self.db.add(inspection)
        self.db.flush()

        sample_id_for_ref = data.sample_id
        if not sample_id_for_ref:
            active_report = self._get_active_report_for_batch(data.batch_id)
            if active_report:
                sample_id_for_ref = active_report.sample_id

        for item_data in data.item_results:
            enterprise_result = None
            if sample_id_for_ref:
                enterprise_result = self._get_enterprise_test_result(sample_id_for_ref, item_data.test_item_id)

            enterprise_value = None
            enterprise_numeric = None
            enterprise_judgment = None
            is_consistent = None

            if enterprise_result:
                enterprise_value = enterprise_result.test_value
                enterprise_numeric = enterprise_result.numeric_value
                enterprise_judgment = enterprise_result.judgment

                if item_data.regulatory_judgment and enterprise_judgment:
                    is_consistent = (item_data.regulatory_judgment == enterprise_judgment)

            item = RegulatoryInspectionItem(
                inspection_id=inspection.id,
                test_item_id=item_data.test_item_id,
                enterprise_value=enterprise_value,
                enterprise_numeric_value=enterprise_numeric,
                enterprise_judgment=enterprise_judgment,
                regulatory_value=item_data.regulatory_value,
                regulatory_numeric_value=item_data.regulatory_numeric_value,
                regulatory_judgment=item_data.regulatory_judgment,
                is_consistent=is_consistent,
                difference_detail=item_data.difference_detail,
            )
            self.db.add(item)

        self.db.commit()
        self.db.refresh(inspection)
        return inspection

    def get_inspection(self, inspection_id: int) -> RegulatoryInspection:
        inspection = self.db.query(RegulatoryInspection).filter(RegulatoryInspection.id == inspection_id).first()
        if not inspection:
            raise RegulatoryInspectionNotFoundError(inspection_id=inspection_id)
        return inspection

    def get_inspection_by_code(self, inspection_code: str) -> RegulatoryInspection:
        inspection = self.db.query(RegulatoryInspection).filter(RegulatoryInspection.inspection_code == inspection_code).first()
        if not inspection:
            raise RegulatoryInspectionNotFoundError(inspection_code=inspection_code)
        return inspection

    def list_inspections(
        self,
        skip: int = 0,
        limit: int = 100,
        batch_id: Optional[int] = None,
        status: Optional[str] = None,
    ) -> List[RegulatoryInspection]:
        query = self.db.query(RegulatoryInspection)
        if batch_id:
            query = query.filter(RegulatoryInspection.batch_id == batch_id)
        if status:
            query = query.filter(RegulatoryInspection.status == status)
        return query.order_by(RegulatoryInspection.created_at.desc()).offset(skip).limit(limit).all()

    def update_inspection(self, inspection_id: int, data: RegulatoryInspectionUpdate) -> RegulatoryInspection:
        inspection = self.get_inspection(inspection_id)
        if inspection.status != RegulatoryInspectionStatus.DRAFT.value:
            raise InspectionAlreadyConfirmedError(inspection.inspection_code)

        update_data = data.model_dump(exclude_unset=True, exclude={"item_results"})
        for key, value in update_data.items():
            if key == "inspection_date" and value:
                value = self.parse_datetime(value)
            setattr(inspection, key, value)

        if data.item_results is not None:
            self.db.query(RegulatoryInspectionItem).filter(
                RegulatoryInspectionItem.inspection_id == inspection_id
            ).delete()

            sample_id_for_ref = inspection.sample_id
            if not sample_id_for_ref:
                active_report = self._get_active_report_for_batch(inspection.batch_id)
                if active_report:
                    sample_id_for_ref = active_report.sample_id

            for item_data in data.item_results:
                enterprise_result = None
                if sample_id_for_ref:
                    enterprise_result = self._get_enterprise_test_result(sample_id_for_ref, item_data.test_item_id)

                enterprise_value = None
                enterprise_numeric = None
                enterprise_judgment = None
                is_consistent = None

                if enterprise_result:
                    enterprise_value = enterprise_result.test_value
                    enterprise_numeric = enterprise_result.numeric_value
                    enterprise_judgment = enterprise_result.judgment
                    if item_data.regulatory_judgment and enterprise_judgment:
                        is_consistent = (item_data.regulatory_judgment == enterprise_judgment)

                item = RegulatoryInspectionItem(
                    inspection_id=inspection.id,
                    test_item_id=item_data.test_item_id,
                    enterprise_value=enterprise_value,
                    enterprise_numeric_value=enterprise_numeric,
                    enterprise_judgment=enterprise_judgment,
                    regulatory_value=item_data.regulatory_value,
                    regulatory_numeric_value=item_data.regulatory_numeric_value,
                    regulatory_judgment=item_data.regulatory_judgment,
                    is_consistent=is_consistent,
                    difference_detail=item_data.difference_detail,
                )
                self.db.add(item)

        inspection.updated_at = datetime.now()
        self.db.commit()
        self.db.refresh(inspection)
        return inspection

    def confirm_inspection(self, inspection_id: int) -> RegulatoryInspection:
        inspection = self.get_inspection(inspection_id)
        if inspection.status != RegulatoryInspectionStatus.DRAFT.value:
            raise InspectionAlreadyConfirmedError(inspection.inspection_code)

        inspection.status = RegulatoryInspectionStatus.CONFIRMED.value
        inspection.updated_at = datetime.now()

        self.db.commit()
        self.db.refresh(inspection)

        if self._has_difference(inspection):
            self._generate_difference_from_inspection(inspection)

        return inspection

    def _has_difference(self, inspection: RegulatoryInspection) -> bool:
        if inspection.overall_conclusion:
            batch = self.db.query(Batch).filter(Batch.id == inspection.batch_id).first()
            if batch and batch.final_result and inspection.overall_conclusion != batch.final_result:
                return True

        for item in inspection.item_results:
            if item.is_consistent == False:
                return True
        return False

    def _generate_difference_from_inspection(self, inspection: RegulatoryInspection) -> RegulatoryDifference:
        batch = self.db.query(Batch).filter(Batch.id == inspection.batch_id).first()

        inconsistent_items = []
        for item in inspection.item_results:
            if item.is_consistent == False:
                ti = self.db.query(TestItem).filter(TestItem.id == item.test_item_id).first()
                item_name = ti.item_name if ti else f"检测项{item.test_item_id}"
                inconsistent_items.append(
                    f"{item_name}: 企业判定={item.enterprise_judgment or '-'}, "
                    f"监管判定={item.regulatory_judgment or '-'}"
                )

        difference_code = self._generate_difference_code()
        difference = RegulatoryDifference(
            difference_code=difference_code,
            batch_id=inspection.batch_id,
            source_inspection_id=inspection.id,
            difference_type="judgment_inconsistency" if inconsistent_items else "overall_inconsistency",
            difference_items_summary="\n".join(inconsistent_items) if inconsistent_items else None,
            enterprise_judgment=batch.final_result if batch else None,
            regulatory_judgment=inspection.overall_conclusion,
            handling_status=RegulatoryDifferenceStatus.PENDING.value,
        )
        self.db.add(difference)
        self.db.flush()

        inspection.difference_generated = True
        inspection.difference_id = difference.id
        inspection.status = RegulatoryInspectionStatus.COMPLETED.value
        inspection.updated_at = datetime.now()

        self._freeze_batch_for_difference(batch, difference)

        self.db.commit()
        self.db.refresh(difference)
        return difference

    def _freeze_batch_for_difference(self, batch: Batch, difference: RegulatoryDifference) -> None:
        if not batch:
            return

        if batch.released:
            batch.released = False
            batch.release_revoked = True
            batch.release_revoked_at = datetime.now()
            batch.release_revoked_by = "system_regulatory"
            batch.release_revoked_reason = f"监管抽检差异，自动撤销放行: 差异单{difference.difference_code}"
            difference.release_revoked = True

        batch.frozen = True
        batch.frozen_at = datetime.now()
        batch.frozen_by = "system_regulatory"
        batch.frozen_reason = f"监管抽检存在差异，自动冻结: 差异单{difference.difference_code}"
        difference.batch_frozen = True
        batch.updated_at = datetime.now()

    def freeze_batch(self, batch_id: int, data: BatchFreezeRequest) -> Batch:
        batch = self.db.query(Batch).filter(Batch.id == batch_id).first()
        if not batch:
            raise BatchNotFoundError(batch_id=batch_id)

        if batch.frozen:
            raise BatchFrozenError(batch.batch_no, batch.frozen_reason)

        batch.frozen = True
        batch.frozen_at = datetime.now()
        batch.frozen_by = data.frozen_by
        batch.frozen_reason = data.frozen_reason
        batch.updated_at = datetime.now()

        self.db.commit()
        self.db.refresh(batch)
        return batch

    def unfreeze_batch(self, batch_id: int, data: BatchUnfreezeRequest) -> Batch:
        batch = self.db.query(Batch).filter(Batch.id == batch_id).first()
        if not batch:
            raise BatchNotFoundError(batch_id=batch_id)

        if not batch.frozen:
            raise BatchNotFrozenError(batch.batch_no)

        pending_diff = (
            self.db.query(RegulatoryDifference)
            .filter(
                RegulatoryDifference.batch_id == batch_id,
                RegulatoryDifference.handling_status != RegulatoryDifferenceStatus.CLOSED.value,
            )
            .first()
        )
        if pending_diff:
            raise ReleaseNotAllowedError(f"存在未关闭的监管差异单 {pending_diff.difference_code}，无法解冻")

        batch.frozen = False
        batch.frozen_at = None
        batch.frozen_by = None
        if data.unfreeze_remark:
            batch.remark = (batch.remark or "") + f"\n解冻备注: {data.unfreeze_remark} (操作人: {data.unfrozen_by})"
        batch.updated_at = datetime.now()

        self.db.commit()
        self.db.refresh(batch)
        return batch

    def revoke_release(self, batch_id: int, data: ReleaseRevokeRequest) -> Batch:
        batch = self.db.query(Batch).filter(Batch.id == batch_id).first()
        if not batch:
            raise BatchNotFoundError(batch_id=batch_id)

        if not batch.released:
            raise BatchNotReleasedError(batch.batch_no)

        batch.released = False
        batch.release_revoked = True
        batch.release_revoked_at = datetime.now()
        batch.release_revoked_by = data.revoked_by
        batch.release_revoked_reason = data.revoked_reason
        batch.updated_at = datetime.now()

        self.db.commit()
        self.db.refresh(batch)
        return batch

    def get_difference(self, difference_id: int) -> RegulatoryDifference:
        diff = self.db.query(RegulatoryDifference).filter(RegulatoryDifference.id == difference_id).first()
        if not diff:
            raise RegulatoryDifferenceNotFoundError(difference_id=difference_id)
        return diff

    def get_difference_by_code(self, difference_code: str) -> RegulatoryDifference:
        diff = self.db.query(RegulatoryDifference).filter(RegulatoryDifference.difference_code == difference_code).first()
        if not diff:
            raise RegulatoryDifferenceNotFoundError(difference_code=difference_code)
        return diff

    def list_differences(
        self,
        skip: int = 0,
        limit: int = 100,
        batch_id: Optional[int] = None,
        handling_status: Optional[str] = None,
    ) -> List[RegulatoryDifference]:
        query = self.db.query(RegulatoryDifference)
        if batch_id:
            query = query.filter(RegulatoryDifference.batch_id == batch_id)
        if handling_status:
            query = query.filter(RegulatoryDifference.handling_status == handling_status)
        return query.order_by(RegulatoryDifference.created_at.desc()).offset(skip).limit(limit).all()

    def process_difference(self, difference_id: int, data: RegulatoryDifferenceProcess) -> RegulatoryDifference:
        diff = self.get_difference(difference_id)
        diff.handler = data.handler
        diff.difference_reason = data.difference_reason
        diff.handling_measures = data.handling_measures
        diff.handling_status = RegulatoryDifferenceStatus.PROCESSING.value
        diff.updated_at = datetime.now()

        self.db.commit()
        self.db.refresh(diff)
        return diff

    def close_difference(self, difference_id: int, data: RegulatoryDifferenceClose) -> RegulatoryDifference:
        diff = self.get_difference(difference_id)
        diff.closed_at = datetime.now()
        diff.closed_by = data.closed_by
        diff.closing_remark = data.closing_remark
        diff.handling_status = RegulatoryDifferenceStatus.CLOSED.value
        diff.updated_at = datetime.now()

        self.db.commit()
        self.db.refresh(diff)
        return diff

    def to_inspection_response(self, inspection: RegulatoryInspection) -> RegulatoryInspectionResponse:
        batch = inspection.batch
        sample = inspection.sample
        original_report = inspection.original_report
        reinspection_report = inspection.reinspection_report
        arbitration_report = inspection.arbitration_report

        item_responses = []
        for item in inspection.item_results:
            ti = item.test_item
            item_responses.append(
                RegulatoryInspectionItemResponse(
                    id=item.id,
                    inspection_id=item.inspection_id,
                    test_item_id=item.test_item_id,
                    test_item_code=ti.item_code if ti else "",
                    test_item_name=ti.item_name if ti else "",
                    enterprise_value=item.enterprise_value,
                    enterprise_numeric_value=item.enterprise_numeric_value,
                    enterprise_judgment=item.enterprise_judgment,
                    regulatory_value=item.regulatory_value,
                    regulatory_numeric_value=item.regulatory_numeric_value,
                    regulatory_judgment=item.regulatory_judgment,
                    is_consistent=item.is_consistent,
                    difference_detail=item.difference_detail,
                    created_at=item.created_at,
                )
            )

        return RegulatoryInspectionResponse(
            id=inspection.id,
            inspection_code=inspection.inspection_code,
            batch_id=inspection.batch_id,
            batch_no=batch.batch_no if batch else "",
            sample_id=inspection.sample_id,
            sample_code=sample.sample_code if sample else None,
            original_report_id=inspection.original_report_id,
            original_report_no=original_report.report_no if original_report else None,
            reinspection_report_id=inspection.reinspection_report_id,
            reinspection_report_no=reinspection_report.report_no if reinspection_report else None,
            arbitration_report_id=inspection.arbitration_report_id,
            arbitration_report_no=arbitration_report.report_no if arbitration_report else None,
            inspection_agency=inspection.inspection_agency,
            inspector=inspection.inspector,
            inspection_date=inspection.inspection_date,
            inspection_type=inspection.inspection_type,
            inspection_basis=inspection.inspection_basis,
            sampling_location=inspection.sampling_location,
            overall_conclusion=inspection.overall_conclusion,
            inspection_remark=inspection.inspection_remark,
            created_by=inspection.created_by,
            status=inspection.status,
            difference_generated=inspection.difference_generated,
            difference_id=inspection.difference_id,
            item_results=item_responses,
            created_at=inspection.created_at,
            updated_at=inspection.updated_at,
        )

    def to_difference_response(self, diff: RegulatoryDifference) -> RegulatoryDifferenceResponse:
        batch = diff.batch
        src = diff.source_inspection

        return RegulatoryDifferenceResponse(
            id=diff.id,
            difference_code=diff.difference_code,
            batch_id=diff.batch_id,
            batch_no=batch.batch_no if batch else "",
            source_inspection_id=diff.source_inspection_id,
            source_inspection_code=src.inspection_code if src else "",
            difference_type=diff.difference_type,
            difference_items_summary=diff.difference_items_summary,
            enterprise_judgment=diff.enterprise_judgment,
            regulatory_judgment=diff.regulatory_judgment,
            difference_reason=diff.difference_reason,
            handler=diff.handler,
            handling_measures=diff.handling_measures,
            handling_status=diff.handling_status,
            batch_frozen=diff.batch_frozen,
            release_revoked=diff.release_revoked,
            closed_at=diff.closed_at,
            closed_by=diff.closed_by,
            closing_remark=diff.closing_remark,
            created_at=diff.created_at,
            updated_at=diff.updated_at,
        )
