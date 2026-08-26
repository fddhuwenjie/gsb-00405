from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional

from .base_service import BaseService
from ..models import TestItem, TestResult, Sample, Batch
from ..schemas import (
    TestItemCreate,
    TestResultCreate,
    TestResultUpdate,
    TestResultResponse,
    Judgment,
    BatchStatus,
)
from ..exceptions import (
    TestItemNotFoundError,
    SampleNotFoundError,
    TestItemMissingError,
)


class TestService(BaseService):
    def create_test_item(self, data: TestItemCreate) -> TestItem:
        test_item = TestItem(**data.model_dump())
        self.db.add(test_item)
        self.db.commit()
        self.db.refresh(test_item)
        return test_item

    def get_test_item(self, item_id: int) -> TestItem:
        item = self.db.query(TestItem).filter(TestItem.id == item_id).first()
        if not item:
            raise TestItemNotFoundError(item_id=item_id)
        return item

    def get_test_item_by_code(self, item_code: str) -> TestItem:
        item = self.db.query(TestItem).filter(TestItem.item_code == item_code).first()
        if not item:
            raise TestItemNotFoundError(item_code=item_code)
        return item

    def list_test_items(
        self,
        skip: int = 0,
        limit: int = 100,
        category: Optional[str] = None,
        is_mandatory: Optional[bool] = None,
    ) -> List[TestItem]:
        query = self.db.query(TestItem)
        if category:
            query = query.filter(TestItem.category == category)
        if is_mandatory is not None:
            query = query.filter(TestItem.is_mandatory == is_mandatory)
        return query.order_by(TestItem.created_at).offset(skip).limit(limit).all()

    def get_mandatory_test_items(self) -> List[TestItem]:
        return self.db.query(TestItem).filter(TestItem.is_mandatory == True).all()

    def validate_test_items_complete(self, sample_id: int) -> None:
        mandatory_items = self.get_mandatory_test_items()
        if not mandatory_items:
            return

        existing_results = (
            self.db.query(TestResult)
            .filter(
                TestResult.sample_id == sample_id,
                TestResult.is_reinspection == False,
            )
            .all()
        )
        tested_item_ids = [r.test_item_id for r in existing_results]

        missing_items = []
        for item in mandatory_items:
            if item.id not in tested_item_ids:
                missing_items.append(f"{item.item_code}({item.item_name})")

        if missing_items:
            raise TestItemMissingError(missing_items)

    def validate_reinspection_items_complete(self, sample_id: int, reinspection_id: int) -> None:
        mandatory_items = self.get_mandatory_test_items()
        if not mandatory_items:
            return

        existing_results = (
            self.db.query(TestResult)
            .filter(
                TestResult.sample_id == sample_id,
                TestResult.reinspection_id == reinspection_id,
                TestResult.result_status == "completed",
                TestResult.judgment.in_([Judgment.PASS.value, Judgment.FAIL.value]),
            )
            .all()
        )
        tested_item_ids = [r.test_item_id for r in existing_results]

        missing_items = []
        for item in mandatory_items:
            if item.id not in tested_item_ids:
                missing_items.append(f"{item.item_code}({item.item_name})")

        if missing_items:
            raise TestItemMissingError(missing_items)

    def create_test_result(self, data: TestResultCreate, is_reinspection: bool = False, reinspection_id: Optional[int] = None) -> TestResult:
        sample = self.db.query(Sample).filter(Sample.id == data.sample_id).first()
        if not sample:
            raise SampleNotFoundError(sample_id=data.sample_id)

        test_item = self.get_test_item(data.test_item_id)

        judgment = self._auto_judge(data.numeric_value, test_item)

        test_result = TestResult(
            sample_id=data.sample_id,
            test_item_id=data.test_item_id,
            is_reinspection=is_reinspection,
            reinspection_id=reinspection_id,
            test_value=data.test_value,
            numeric_value=data.numeric_value,
            tester=data.tester,
            test_time=self.parse_datetime(data.test_time),
            instrument=data.instrument,
            result_status="completed",
            judgment=judgment,
        )

        self.db.add(test_result)

        if not is_reinspection:
            batch = sample.batch
            if batch.status in [BatchStatus.SAMPLING.value, BatchStatus.PENDING.value]:
                batch.status = BatchStatus.TESTING.value
                batch.updated_at = datetime.now()

        self.db.commit()
        self.db.refresh(test_result)
        return test_result

    def _auto_judge(self, numeric_value: Optional[float], test_item: TestItem) -> str:
        if numeric_value is None:
            return Judgment.PENDING.value

        if test_item.lower_limit is not None and numeric_value < test_item.lower_limit:
            return Judgment.FAIL.value

        if test_item.upper_limit is not None and numeric_value > test_item.upper_limit:
            return Judgment.FAIL.value

        return Judgment.PASS.value

    def update_test_result(self, result_id: int, data: TestResultUpdate) -> TestResult:
        result = self.db.query(TestResult).filter(TestResult.id == result_id).first()
        if not result:
            raise TestItemNotFoundError(item_id=result_id)

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(result, key, value)

        if data.numeric_value is not None:
            test_item = self.get_test_item(result.test_item_id)
            result.judgment = self._auto_judge(data.numeric_value, test_item)

        result.updated_at = datetime.now()
        self.db.commit()
        self.db.refresh(result)
        return result

    def get_test_results(
        self,
        sample_id: Optional[int] = None,
        test_item_id: Optional[int] = None,
        is_reinspection: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[TestResult]:
        query = self.db.query(TestResult)
        if sample_id:
            query = query.filter(TestResult.sample_id == sample_id)
        if test_item_id:
            query = query.filter(TestResult.test_item_id == test_item_id)
        if is_reinspection is not None:
            query = query.filter(TestResult.is_reinspection == is_reinspection)
        return query.order_by(TestResult.created_at.desc()).offset(skip).limit(limit).all()

    def to_response(self, result: TestResult) -> TestResultResponse:
        return TestResultResponse(
            id=result.id,
            sample_id=result.sample_id,
            sample_code=result.sample.sample_code,
            test_item_id=result.test_item_id,
            test_item_code=result.test_item.item_code,
            test_item_name=result.test_item.item_name,
            is_reinspection=result.is_reinspection,
            test_value=result.test_value,
            numeric_value=result.numeric_value,
            tester=result.tester,
            test_time=result.test_time,
            instrument=result.instrument,
            judgment=result.judgment,
            standard_value=result.test_item.standard_value,
            lower_limit=result.test_item.lower_limit,
            upper_limit=result.test_item.upper_limit,
            unit=result.test_item.unit,
            remark=result.remark,
            created_at=result.created_at,
        )
