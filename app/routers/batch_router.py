from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from ..database import get_db
from ..services import BatchService
from ..schemas import (
    BatchCreate,
    BatchUpdate,
    BatchResponse,
    BatchRelease,
    BatchQualityArchive,
)

router = APIRouter(prefix="/batches", tags=["批次管理"])


@router.post("", response_model=BatchResponse, summary="创建批次")
def create_batch(data: BatchCreate, db: Session = Depends(get_db)):
    service = BatchService(db)
    batch = service.create_batch(data)
    return BatchResponse.model_validate(batch)


@router.get("", response_model=List[BatchResponse], summary="获取批次列表")
def list_batches(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = Query(None, description="批次状态筛选"),
    db: Session = Depends(get_db),
):
    service = BatchService(db)
    batches = service.list_batches(skip=skip, limit=limit, status=status)
    return [BatchResponse.model_validate(b) for b in batches]


@router.get("/{batch_id}", response_model=BatchResponse, summary="获取批次详情")
def get_batch(batch_id: int, db: Session = Depends(get_db)):
    service = BatchService(db)
    batch = service.get_batch(batch_id)
    return BatchResponse.model_validate(batch)


@router.get("/no/{batch_no}", response_model=BatchResponse, summary="根据批次号获取")
def get_batch_by_no(batch_no: str, db: Session = Depends(get_db)):
    service = BatchService(db)
    batch = service.get_batch_by_no(batch_no)
    return BatchResponse.model_validate(batch)


@router.put("/{batch_id}", response_model=BatchResponse, summary="更新批次")
def update_batch(batch_id: int, data: BatchUpdate, db: Session = Depends(get_db)):
    service = BatchService(db)
    batch = service.update_batch(batch_id, data)
    return BatchResponse.model_validate(batch)


@router.post("/{batch_id}/release", response_model=BatchResponse, summary="放行批次")
def release_batch(batch_id: int, data: BatchRelease, db: Session = Depends(get_db)):
    service = BatchService(db)
    batch = service.release_batch(batch_id, data)
    return BatchResponse.model_validate(batch)


@router.get("/{batch_id}/archive", response_model=BatchQualityArchive, summary="获取批次质量档案")
def get_batch_archive(batch_id: int, db: Session = Depends(get_db)):
    service = BatchService(db)
    return service.get_quality_archive(batch_id)
