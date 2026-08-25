from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from ..database import get_db
from ..services import RetentionService
from ..schemas import (
    RetentionCreate,
    RetentionDestroy,
    RetentionResponse,
    RetentionLocationResponse,
    RetentionExpireStats,
)

router = APIRouter(prefix="/retentions", tags=["留样管理"])


@router.post("", response_model=RetentionResponse, summary="创建留样")
def create_retention(data: RetentionCreate, db: Session = Depends(get_db)):
    service = RetentionService(db)
    retention = service.create_retention(data)
    return service.to_response(retention)


@router.get("", response_model=List[RetentionResponse], summary="获取留样列表")
def list_retentions(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = Query(None, description="状态筛选"),
    is_expired: Optional[bool] = Query(None, description="是否过期筛选"),
    destroyed: Optional[bool] = Query(None, description="是否销毁筛选"),
    db: Session = Depends(get_db),
):
    service = RetentionService(db)
    retentions = service.list_retentions(
        skip=skip,
        limit=limit,
        status=status,
        is_expired=is_expired,
        destroyed=destroyed,
    )
    return [service.to_response(r) for r in retentions]


@router.get("/locations", response_model=List[RetentionLocationResponse], summary="获取留样位置列表")
def list_locations(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    zone: Optional[str] = Query(None, description="库区筛选"),
    shelf: Optional[int] = Query(None, description="货架筛选"),
    is_occupied: Optional[bool] = Query(None, description="是否占用筛选"),
    db: Session = Depends(get_db),
):
    service = RetentionService(db)
    locations = service.list_locations(
        skip=skip,
        limit=limit,
        zone=zone,
        shelf=shelf,
        is_occupied=is_occupied,
    )
    return [service.to_location_response(l) for l in locations]


@router.get("/sample/{sample_id}", response_model=Optional[RetentionResponse], summary="根据样品获取留样")
def get_retention_by_sample(sample_id: int, db: Session = Depends(get_db)):
    service = RetentionService(db)
    retention = service.get_retention_by_sample(sample_id)
    return service.to_response(retention) if retention else None


@router.post("/check-expired", summary="检查过期留样", description="自动标记过期留样")
def check_expired_retentions(db: Session = Depends(get_db)):
    service = RetentionService(db)
    count = service.check_expired_retentions()
    return {"expired_count": count, "message": f"已标记 {count} 个过期留样"}


@router.get("/expire-stats", response_model=RetentionExpireStats, summary="获取留样过期统计")
def get_expire_stats(db: Session = Depends(get_db)):
    service = RetentionService(db)
    return service.get_expire_stats()


@router.get("/{retention_id}", response_model=RetentionResponse, summary="获取留样详情")
def get_retention(retention_id: int, db: Session = Depends(get_db)):
    service = RetentionService(db)
    retention = service.get_retention(retention_id)
    return service.to_response(retention)


@router.post("/{retention_id}/destroy", response_model=RetentionResponse, summary="销毁留样")
def destroy_retention(
    retention_id: int,
    data: RetentionDestroy,
    db: Session = Depends(get_db),
):
    service = RetentionService(db)
    retention = service.destroy_retention(retention_id, data)
    return service.to_response(retention)
