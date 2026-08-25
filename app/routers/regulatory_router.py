from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from ..database import get_db
from ..services.regulatory_service import RegulatoryService
from ..services.batch_service import BatchService
from ..schemas import (
    RegulatoryInspectionCreate,
    RegulatoryInspectionUpdate,
    RegulatoryInspectionResponse,
    RegulatoryDifferenceResponse,
    RegulatoryDifferenceProcess,
    RegulatoryDifferenceClose,
    BatchFreezeRequest,
    BatchUnfreezeRequest,
    ReleaseRevokeRequest,
    BatchResponse,
)

router = APIRouter(prefix="/regulatory", tags=["监管抽检与差异管理"])


@router.post("/inspections", response_model=RegulatoryInspectionResponse, summary="创建监管抽检记录")
def create_inspection(data: RegulatoryInspectionCreate, db: Session = Depends(get_db)):
    service = RegulatoryService(db)
    inspection = service.create_inspection(data)
    return service.to_inspection_response(inspection)


@router.get("/inspections", response_model=List[RegulatoryInspectionResponse], summary="获取监管抽检列表")
def list_inspections(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    batch_id: Optional[int] = Query(None, description="批次ID筛选"),
    status: Optional[str] = Query(None, description="状态筛选"),
    db: Session = Depends(get_db),
):
    service = RegulatoryService(db)
    inspections = service.list_inspections(skip=skip, limit=limit, batch_id=batch_id, status=status)
    return [service.to_inspection_response(i) for i in inspections]


@router.get("/inspections/{inspection_id}", response_model=RegulatoryInspectionResponse, summary="获取抽检详情")
def get_inspection(inspection_id: int, db: Session = Depends(get_db)):
    service = RegulatoryService(db)
    inspection = service.get_inspection(inspection_id)
    return service.to_inspection_response(inspection)


@router.get("/inspections/code/{inspection_code}", response_model=RegulatoryInspectionResponse, summary="按编号获取抽检")
def get_inspection_by_code(inspection_code: str, db: Session = Depends(get_db)):
    service = RegulatoryService(db)
    inspection = service.get_inspection_by_code(inspection_code)
    return service.to_inspection_response(inspection)


@router.put("/inspections/{inspection_id}", response_model=RegulatoryInspectionResponse, summary="更新抽检记录")
def update_inspection(inspection_id: int, data: RegulatoryInspectionUpdate, db: Session = Depends(get_db)):
    service = RegulatoryService(db)
    inspection = service.update_inspection(inspection_id, data)
    return service.to_inspection_response(inspection)


@router.post("/inspections/{inspection_id}/confirm", response_model=RegulatoryInspectionResponse, summary="确认抽检并生成差异单")
def confirm_inspection(inspection_id: int, db: Session = Depends(get_db)):
    service = RegulatoryService(db)
    inspection = service.confirm_inspection(inspection_id)
    return service.to_inspection_response(inspection)


@router.get("/differences", response_model=List[RegulatoryDifferenceResponse], summary="获取差异单列表")
def list_differences(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    batch_id: Optional[int] = Query(None, description="批次ID筛选"),
    handling_status: Optional[str] = Query(None, description="处理状态筛选"),
    db: Session = Depends(get_db),
):
    service = RegulatoryService(db)
    diffs = service.list_differences(skip=skip, limit=limit, batch_id=batch_id, handling_status=handling_status)
    return [service.to_difference_response(d) for d in diffs]


@router.get("/differences/{difference_id}", response_model=RegulatoryDifferenceResponse, summary="获取差异单详情")
def get_difference(difference_id: int, db: Session = Depends(get_db)):
    service = RegulatoryService(db)
    diff = service.get_difference(difference_id)
    return service.to_difference_response(diff)


@router.get("/differences/code/{difference_code}", response_model=RegulatoryDifferenceResponse, summary="按编号获取差异单")
def get_difference_by_code(difference_code: str, db: Session = Depends(get_db)):
    service = RegulatoryService(db)
    diff = service.get_difference_by_code(difference_code)
    return service.to_difference_response(diff)


@router.post("/differences/{difference_id}/process", response_model=RegulatoryDifferenceResponse, summary="处理差异单")
def process_difference(difference_id: int, data: RegulatoryDifferenceProcess, db: Session = Depends(get_db)):
    service = RegulatoryService(db)
    diff = service.process_difference(difference_id, data)
    return service.to_difference_response(diff)


@router.post("/differences/{difference_id}/close", response_model=RegulatoryDifferenceResponse, summary="关闭差异单")
def close_difference(difference_id: int, data: RegulatoryDifferenceClose, db: Session = Depends(get_db)):
    service = RegulatoryService(db)
    diff = service.close_difference(difference_id, data)
    return service.to_difference_response(diff)


@router.post("/batches/{batch_id}/freeze", response_model=BatchResponse, summary="冻结批次")
def freeze_batch(batch_id: int, data: BatchFreezeRequest, db: Session = Depends(get_db)):
    service = RegulatoryService(db)
    batch = service.freeze_batch(batch_id, data)
    return BatchResponse.model_validate(batch)


@router.post("/batches/{batch_id}/unfreeze", response_model=BatchResponse, summary="解冻批次")
def unfreeze_batch(batch_id: int, data: BatchUnfreezeRequest, db: Session = Depends(get_db)):
    service = RegulatoryService(db)
    batch = service.unfreeze_batch(batch_id, data)
    return BatchResponse.model_validate(batch)


@router.post("/batches/{batch_id}/revoke-release", response_model=BatchResponse, summary="撤销批次放行")
def revoke_release(batch_id: int, data: ReleaseRevokeRequest, db: Session = Depends(get_db)):
    service = RegulatoryService(db)
    batch = service.revoke_release(batch_id, data)
    return BatchResponse.model_validate(batch)
