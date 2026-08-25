from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from ..database import get_db
from ..services import ArbitrationService
from ..schemas import (
    ArbitrationCreate,
    ArbitrationProcess,
    ArbitrationResponse,
)

router = APIRouter(prefix="/arbitrations", tags=["仲裁管理"])


@router.post("", response_model=ArbitrationResponse, summary="发起仲裁")
def create_arbitration(data: ArbitrationCreate, db: Session = Depends(get_db)):
    service = ArbitrationService(db)
    arbitration = service.create_arbitration(data)
    return service.to_response(arbitration)


@router.get("", response_model=List[ArbitrationResponse], summary="获取仲裁列表")
def list_arbitrations(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = Query(None, description="状态筛选"),
    batch_id: Optional[int] = Query(None, description="批次ID筛选"),
    db: Session = Depends(get_db),
):
    service = ArbitrationService(db)
    arbitrations = service.list_arbitrations(
        skip=skip,
        limit=limit,
        status=status,
        batch_id=batch_id,
    )
    return [service.to_response(a) for a in arbitrations]


@router.get("/{arbitration_id}", response_model=ArbitrationResponse, summary="获取仲裁详情")
def get_arbitration(arbitration_id: int, db: Session = Depends(get_db)):
    service = ArbitrationService(db)
    arbitration = service.get_arbitration(arbitration_id)
    return service.to_response(arbitration)


@router.get("/code/{arbitration_code}", response_model=ArbitrationResponse, summary="根据编号获取仲裁")
def get_arbitration_by_code(arbitration_code: str, db: Session = Depends(get_db)):
    service = ArbitrationService(db)
    arbitration = service.get_arbitration_by_code(arbitration_code)
    return service.to_response(arbitration)


@router.post("/{arbitration_id}/process", response_model=ArbitrationResponse, summary="处理仲裁")
def process_arbitration(
    arbitration_id: int,
    data: ArbitrationProcess,
    db: Session = Depends(get_db),
):
    service = ArbitrationService(db)
    arbitration = service.process_arbitration(arbitration_id, data)
    return service.to_response(arbitration)


@router.post("/{arbitration_id}/complete", response_model=ArbitrationResponse, summary="完成仲裁")
def complete_arbitration(
    arbitration_id: int,
    data: ArbitrationProcess,
    db: Session = Depends(get_db),
):
    service = ArbitrationService(db)
    arbitration = service.complete_arbitration(arbitration_id, data)
    return service.to_response(arbitration)
