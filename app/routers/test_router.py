from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from ..database import get_db
from ..services import TestService
from ..schemas import (
    TestItemCreate,
    TestItemResponse,
    TestResultCreate,
    TestResultUpdate,
    TestResultResponse,
)

router = APIRouter(prefix="/tests", tags=["检测管理"])


@router.post("/items", response_model=TestItemResponse, summary="创建检测项")
def create_test_item(data: TestItemCreate, db: Session = Depends(get_db)):
    service = TestService(db)
    item = service.create_test_item(data)
    return TestItemResponse.model_validate(item)


@router.get("/items", response_model=List[TestItemResponse], summary="获取检测项列表")
def list_test_items(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    category: Optional[str] = Query(None, description="分类筛选"),
    is_mandatory: Optional[bool] = Query(None, description="是否必检筛选"),
    db: Session = Depends(get_db),
):
    service = TestService(db)
    items = service.list_test_items(
        skip=skip,
        limit=limit,
        category=category,
        is_mandatory=is_mandatory,
    )
    return [TestItemResponse.model_validate(i) for i in items]


@router.get("/items/{item_id}", response_model=TestItemResponse, summary="获取检测项详情")
def get_test_item(item_id: int, db: Session = Depends(get_db)):
    service = TestService(db)
    item = service.get_test_item(item_id)
    return TestItemResponse.model_validate(item)


@router.get("/items/code/{item_code}", response_model=TestItemResponse, summary="根据编码获取检测项")
def get_test_item_by_code(item_code: str, db: Session = Depends(get_db)):
    service = TestService(db)
    item = service.get_test_item_by_code(item_code)
    return TestItemResponse.model_validate(item)


@router.post("/results", response_model=TestResultResponse, summary="录入检测结果")
def create_test_result(data: TestResultCreate, db: Session = Depends(get_db)):
    service = TestService(db)
    result = service.create_test_result(data)
    return service.to_response(result)


@router.put("/results/{result_id}", response_model=TestResultResponse, summary="更新检测结果")
def update_test_result(
    result_id: int,
    data: TestResultUpdate,
    db: Session = Depends(get_db),
):
    service = TestService(db)
    result = service.update_test_result(result_id, data)
    return service.to_response(result)


@router.get("/results", response_model=List[TestResultResponse], summary="获取检测结果列表")
def list_test_results(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    sample_id: Optional[int] = Query(None, description="样品ID筛选"),
    test_item_id: Optional[int] = Query(None, description="检测项ID筛选"),
    is_reinspection: Optional[bool] = Query(None, description="是否复检筛选"),
    db: Session = Depends(get_db),
):
    service = TestService(db)
    results = service.get_test_results(
        skip=skip,
        limit=limit,
        sample_id=sample_id,
        test_item_id=test_item_id,
        is_reinspection=is_reinspection,
    )
    return [service.to_response(r) for r in results]
