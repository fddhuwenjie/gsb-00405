from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional

from .base_service import BaseService
from ..models import Sample, Batch, RetentionLocation
from ..schemas import SampleCreate, SampleResponse, BatchStatus
from ..exceptions import (
    SampleNotFoundError,
    SampleCodeDuplicateError,
    BatchNotFoundError,
)
from ..config import settings


class SampleService(BaseService):
    def create_sample(self, data: SampleCreate) -> Sample:
        batch = self.db.query(Batch).filter(Batch.id == data.batch_id).first()
        if not batch:
            raise BatchNotFoundError(batch_id=data.batch_id)

        sample_code = self.generate_code(settings.SAMPLE_CODE_PREFIX)
        while self.db.query(Sample).filter(Sample.sample_code == sample_code).first():
            sample_code = self.generate_code(settings.SAMPLE_CODE_PREFIX)

        sample = Sample(
            sample_code=sample_code,
            batch_id=data.batch_id,
            sampling_person=data.sampling_person,
            sample_type=data.sample_type,
            status="collected",
        )

        self.db.add(sample)

        batch.status = BatchStatus.SAMPLING.value
        batch.updated_at = datetime.now()

        self.db.commit()
        self.db.refresh(sample)
        return sample

    def get_sample(self, sample_id: int) -> Sample:
        sample = self.db.query(Sample).filter(Sample.id == sample_id).first()
        if not sample:
            raise SampleNotFoundError(sample_id=sample_id)
        return sample

    def get_sample_by_code(self, sample_code: str) -> Sample:
        sample = self.db.query(Sample).filter(Sample.sample_code == sample_code).first()
        if not sample:
            raise SampleNotFoundError(sample_code=sample_code)
        return sample

    def list_samples(
        self,
        skip: int = 0,
        limit: int = 100,
        batch_id: Optional[int] = None,
        is_retained: Optional[bool] = None,
        is_destroyed: Optional[bool] = None,
    ) -> List[Sample]:
        query = self.db.query(Sample)
        if batch_id:
            query = query.filter(Sample.batch_id == batch_id)
        if is_retained is not None:
            query = query.filter(Sample.is_retained == is_retained)
        if is_destroyed is not None:
            query = query.filter(Sample.is_destroyed == is_destroyed)
        return query.order_by(Sample.created_at.desc()).offset(skip).limit(limit).all()

    def validate_sample_code_unique(self, sample_code: str) -> None:
        existing = self.db.query(Sample).filter(Sample.sample_code == sample_code).first()
        if existing:
            raise SampleCodeDuplicateError(sample_code)

    def update_sample_status(self, sample_id: int, status: str) -> Sample:
        sample = self.get_sample(sample_id)
        sample.status = status
        sample.updated_at = datetime.now()
        self.db.commit()
        self.db.refresh(sample)
        return sample

    def to_response(self, sample: Sample) -> SampleResponse:
        location_code = sample.retention_location.location_code if sample.retention_location else None
        return SampleResponse(
            id=sample.id,
            sample_code=sample.sample_code,
            batch_id=sample.batch_id,
            batch_no=sample.batch.batch_no,
            sampling_time=sample.sampling_time,
            sampling_person=sample.sampling_person,
            sample_type=sample.sample_type,
            status=sample.status,
            is_retained=sample.is_retained,
            is_destroyed=sample.is_destroyed,
            retention_location=location_code,
            created_at=sample.created_at,
        )
