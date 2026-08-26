from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from ..database import get_db
from ..services import ReInspectionService, TestService, ReportService
from ..schemas import (
    ReInspectionCreate,
    ReInspectionResponse,
    DifferenceConfirm,
    TestResultCreate,
    TestResultResponse,
    ReportResponse,
)

router = APIRouter(prefix="/reinspections", tags=["复检管理"])


@router.post("", response_model=ReInspectionResponse, summary="申请复检")
def create_reinspection(data: ReInspectionCreate, db: Session = Depends(get_db)):
    service = ReInspectionService(db)
    reinspection = service.create_reinspection(data)
    return service.to_response(reinspection)


@router.get("", response_model=List[ReInspectionResponse], summary="获取复检列表")
def list_reinspections(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = Query(None, description="状态筛选"),
    original_sample_id: Optional[int] = Query(None, description="原始样品ID筛选"),
    db: Session = Depends(get_db),
):
    service = ReInspectionService(db)
    reinspections = service.list_reinspections(
        skip=skip,
        limit=limit,
        status=status,
        original_sample_id=original_sample_id,
    )
    return [service.to_response(r) for r in reinspections]


@router.get("/{reinspection_id}", response_model=ReInspectionResponse, summary="获取复检详情")
def get_reinspection(reinspection_id: int, db: Session = Depends(get_db)):
    service = ReInspectionService(db)
    reinspection = service.get_reinspection(reinspection_id)
    return service.to_response(reinspection)


@router.get("/code/{reinspection_code}", response_model=ReInspectionResponse, summary="根据编号获取复检")
def get_reinspection_by_code(reinspection_code: str, db: Session = Depends(get_db)):
    service = ReInspectionService(db)
    reinspection = service.get_reinspection_by_code(reinspection_code)
    return service.to_response(reinspection)


@router.post("/{reinspection_id}/test-results", response_model=TestResultResponse, summary="录入复检结果")
def create_reinspection_result(
    reinspection_id: int,
    data: TestResultCreate,
    db: Session = Depends(get_db),
):
    reinspection_service = ReInspectionService(db)
    result = reinspection_service.add_reinspection_test_result(reinspection_id, data)
    test_service = TestService(db)
    return test_service.to_response(result)


@router.post("/{reinspection_id}/complete-testing", response_model=ReInspectionResponse, summary="完成复检检测")
def complete_reinspection_testing(reinspection_id: int, db: Session = Depends(get_db)):
    service = ReInspectionService(db)
    reinspection = service.complete_reinspection_testing(reinspection_id)
    return service.to_response(reinspection)


@router.post("/{reinspection_id}/confirm-difference", response_model=ReInspectionResponse, summary="确认复检差异")
def confirm_difference(
    reinspection_id: int,
    data: DifferenceConfirm,
    db: Session = Depends(get_db),
):
    service = ReInspectionService(db)
    reinspection = service.confirm_difference(reinspection_id, data)
    return service.to_response(reinspection)


@router.post("/{reinspection_id}/report", response_model=ReportResponse, summary="生成复检报告")
def create_reinspection_report(
    reinspection_id: int,
    issued_by: str,
    db: Session = Depends(get_db),
):
    reinspection_service = ReInspectionService(db)
    reinspection = reinspection_service.get_reinspection(reinspection_id)

    report_service = ReportService(db)
    report = report_service.create_reinspection_report(
        sample_id=reinspection.re_sample_id,
        reinspection_id=reinspection_id,
        issued_by=issued_by,
    )
    return report_service.to_response(report)
