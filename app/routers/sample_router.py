from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from ..database import get_db
from ..services import SampleService
from ..schemas import SampleCreate, SampleResponse

router = APIRouter(prefix="/samples", tags=["样品管理"])


@router.post("", response_model=SampleResponse, summary="送样/创建样品")
def create_sample(data: SampleCreate, db: Session = Depends(get_db)):
    service = SampleService(db)
    sample = service.create_sample(data)
    return service.to_response(sample)


@router.get("", response_model=List[SampleResponse], summary="获取样品列表")
def list_samples(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    batch_id: Optional[int] = Query(None, description="批次ID筛选"),
    is_retained: Optional[bool] = Query(None, description="是否留样筛选"),
    is_destroyed: Optional[bool] = Query(None, description="是否销毁筛选"),
    db: Session = Depends(get_db),
):
    service = SampleService(db)
    samples = service.list_samples(
        skip=skip,
        limit=limit,
        batch_id=batch_id,
        is_retained=is_retained,
        is_destroyed=is_destroyed,
    )
    return [service.to_response(s) for s in samples]


@router.get("/{sample_id}", response_model=SampleResponse, summary="获取样品详情")
def get_sample(sample_id: int, db: Session = Depends(get_db)):
    service = SampleService(db)
    sample = service.get_sample(sample_id)
    return service.to_response(sample)


@router.get("/code/{sample_code}", response_model=SampleResponse, summary="根据样品编号获取")
def get_sample_by_code(sample_code: str, db: Session = Depends(get_db)):
    service = SampleService(db)
    sample = service.get_sample_by_code(sample_code)
    return service.to_response(sample)
