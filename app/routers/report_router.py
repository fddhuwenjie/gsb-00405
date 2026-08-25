from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from ..database import get_db
from ..services import ReportService
from ..schemas import ReportResponse

router = APIRouter(prefix="/reports", tags=["报告管理"])


@router.get("", response_model=List[ReportResponse], summary="获取报告列表")
def list_reports(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    batch_id: Optional[int] = Query(None, description="批次ID筛选"),
    report_type: Optional[str] = Query(None, description="报告类型筛选"),
    is_active: Optional[bool] = Query(None, description="是否有效筛选"),
    db: Session = Depends(get_db),
):
    service = ReportService(db)
    reports = service.list_reports(
        skip=skip,
        limit=limit,
        batch_id=batch_id,
        report_type=report_type,
        is_active=is_active,
    )
    return [service.to_response(r) for r in reports]


@router.get("/{report_id}", response_model=ReportResponse, summary="获取报告详情")
def get_report(report_id: int, db: Session = Depends(get_db)):
    service = ReportService(db)
    report = service.get_report(report_id)
    return service.to_response(report)


@router.get("/no/{report_no}", response_model=ReportResponse, summary="根据报告号获取")
def get_report_by_no(report_no: str, db: Session = Depends(get_db)):
    service = ReportService(db)
    report = service.get_report_by_no(report_no)
    return service.to_response(report)


@router.post("/original/{sample_id}", response_model=ReportResponse, summary="生成原始检测报告")
def create_original_report(sample_id: int, issued_by: str, db: Session = Depends(get_db)):
    service = ReportService(db)
    report = service.create_original_report(sample_id, issued_by)
    return service.to_response(report)


@router.post("/final/{batch_id}", response_model=ReportResponse, summary="生成最终报告")
def create_final_report(batch_id: int, issued_by: str, db: Session = Depends(get_db)):
    service = ReportService(db)
    report = service.create_final_report(batch_id, issued_by)
    return service.to_response(report)
