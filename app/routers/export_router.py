from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import os

from ..database import get_db
from ..services import ExportService
from ..schemas import ExportRequest, ExportRecordResponse

router = APIRouter(prefix="/exports", tags=["导出管理"])


@router.post("", response_model=ExportRecordResponse, summary="导出报告")
def export_report(data: ExportRequest, db: Session = Depends(get_db)):
    service = ExportService(db)
    record = service.export_report(data)
    return service.to_response(record)


@router.get("", response_model=List[ExportRecordResponse], summary="获取导出记录列表")
def list_export_records(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    batch_id: Optional[int] = Query(None, description="批次ID筛选"),
    db: Session = Depends(get_db),
):
    service = ExportService(db)
    records = service.list_export_records(skip=skip, limit=limit, batch_id=batch_id)
    return [service.to_response(r) for r in records]


@router.get("/download/{export_no}", summary="下载导出文件")
def download_export(export_no: str, db: Session = Depends(get_db)):
    from ..models import ExportRecord

    record = db.query(ExportRecord).filter(ExportRecord.export_no == export_no).first()
    if not record:
        raise HTTPException(status_code=404, detail="导出记录不存在")

    if not os.path.exists(record.file_path):
        raise HTTPException(status_code=404, detail="文件不存在")

    return FileResponse(
        path=record.file_path,
        filename=record.file_name,
        media_type="application/octet-stream",
    )
