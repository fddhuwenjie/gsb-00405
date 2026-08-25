from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List, Optional

from .base_service import BaseService
from ..models import Retention, RetentionLocation, Sample, Batch
from ..schemas import (
    RetentionCreate,
    RetentionDestroy,
    RetentionResponse,
    RetentionLocationResponse,
    RetentionStatus,
    BatchStatus,
    RetentionExpireStats,
)
from ..exceptions import (
    SampleNotFoundError,
    RetentionNotFoundError,
    NoAvailableLocationError,
    RetentionDestroyedError,
    RetentionNotExpiredError,
)
from ..config import settings


class RetentionService(BaseService):
    def __init__(self, db: Session):
        super().__init__(db)
        self._init_locations()

    def _init_locations(self):
        existing = self.db.query(RetentionLocation).first()
        if existing:
            return

        locations = []
        for zone in settings.WAREHOUSE_ZONES:
            for shelf in range(1, settings.SHELVES_PER_ZONE + 1):
                for position in range(1, settings.POSITIONS_PER_SHELF + 1):
                    location_code = f"{zone}-{shelf:02d}-{position:02d}"
                    locations.append(
                        RetentionLocation(
                            location_code=location_code,
                            zone=zone,
                            shelf=shelf,
                            position=position,
                            is_occupied=False,
                        )
                    )
        self.db.bulk_save_objects(locations)
        self.db.commit()

    def _get_available_location(self) -> RetentionLocation:
        location = (
            self.db.query(RetentionLocation)
            .filter(RetentionLocation.is_occupied == False)
            .order_by(RetentionLocation.location_code)
            .first()
        )
        if not location:
            raise NoAvailableLocationError()
        return location

    def create_retention(self, data: RetentionCreate) -> Retention:
        sample = self.db.query(Sample).filter(Sample.id == data.sample_id).first()
        if not sample:
            raise SampleNotFoundError(sample_id=data.sample_id)

        existing_retention = (
            self.db.query(Retention)
            .filter(Retention.sample_id == data.sample_id)
            .first()
        )
        if existing_retention:
            return existing_retention

        location = self._get_available_location()
        period_days = data.retention_period_days or settings.RETENTION_PERIOD_DAYS

        retention = Retention(
            sample_id=data.sample_id,
            location_id=location.id,
            retention_start=datetime.now(),
            retention_end=self.add_days(datetime.now(), period_days),
            retention_period_days=period_days,
            status=RetentionStatus.ACTIVE.value,
            is_expired=False,
            destroyed=False,
        )

        self.db.add(retention)

        location.is_occupied = True
        location.updated_at = datetime.now()

        sample.is_retained = True
        sample.retention_location_id = location.id
        sample.status = "retained"
        sample.updated_at = datetime.now()

        batch = sample.batch
        if batch.status in [BatchStatus.TESTING.value, BatchStatus.JUDGING.value]:
            batch.status = BatchStatus.RETAINING.value
            batch.updated_at = datetime.now()

        self.db.commit()
        self.db.refresh(retention)
        return retention

    def get_retention(self, retention_id: int) -> Retention:
        retention = self.db.query(Retention).filter(Retention.id == retention_id).first()
        if not retention:
            raise RetentionNotFoundError()
        return retention

    def get_retention_by_sample(self, sample_id: int) -> Optional[Retention]:
        return (
            self.db.query(Retention)
            .filter(Retention.sample_id == sample_id)
            .first()
        )

    def list_retentions(
        self,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
        is_expired: Optional[bool] = None,
        destroyed: Optional[bool] = None,
    ) -> List[Retention]:
        query = self.db.query(Retention)
        if status:
            query = query.filter(Retention.status == status)
        if is_expired is not None:
            query = query.filter(Retention.is_expired == is_expired)
        if destroyed is not None:
            query = query.filter(Retention.destroyed == destroyed)
        return query.order_by(Retention.created_at.desc()).offset(skip).limit(limit).all()

    def list_locations(
        self,
        zone: Optional[str] = None,
        shelf: Optional[int] = None,
        is_occupied: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[RetentionLocation]:
        query = self.db.query(RetentionLocation)
        if zone:
            query = query.filter(RetentionLocation.zone == zone)
        if shelf:
            query = query.filter(RetentionLocation.shelf == shelf)
        if is_occupied is not None:
            query = query.filter(RetentionLocation.is_occupied == is_occupied)
        return query.order_by(RetentionLocation.location_code).offset(skip).limit(limit).all()

    def check_expired_retentions(self) -> int:
        now = datetime.now()
        expired_count = 0

        retentions = (
            self.db.query(Retention)
            .filter(
                Retention.is_expired == False,
                Retention.destroyed == False,
                Retention.retention_end <= now,
            )
            .all()
        )

        for retention in retentions:
            retention.is_expired = True
            retention.status = RetentionStatus.EXPIRED.value
            retention.updated_at = now
            expired_count += 1

        self.db.commit()
        return expired_count

    def validate_destroy(self, retention: Retention) -> None:
        if retention.destroyed:
            raise RetentionDestroyedError(retention.sample.sample_code)

        now = datetime.now()
        if retention.retention_end > now:
            days_left = self.days_between(now, retention.retention_end)
            raise RetentionNotExpiredError(retention.sample.sample_code, days_left)

    def destroy_retention(self, retention_id: int, data: RetentionDestroy) -> Retention:
        retention = self.get_retention(retention_id)
        self.validate_destroy(retention)

        retention.destroyed = True
        retention.destroyed_at = datetime.now()
        retention.destroyed_by = data.destroyed_by
        retention.destroy_remark = data.destroy_remark
        retention.status = RetentionStatus.DESTROYED.value
        retention.updated_at = datetime.now()

        location = retention.location
        location.is_occupied = False
        location.updated_at = datetime.now()

        sample = retention.sample
        sample.is_destroyed = True
        sample.destroyed_at = datetime.now()
        sample.destroyed_by = data.destroyed_by
        sample.status = "destroyed"
        sample.updated_at = datetime.now()

        self.db.commit()
        self.db.refresh(retention)
        return retention

    def get_expire_stats(self) -> RetentionExpireStats:
        now = datetime.now()
        seven_days_later = now + timedelta(days=7)
        thirty_days_later = now + timedelta(days=30)

        total_active = (
            self.db.query(Retention)
            .filter(Retention.destroyed == False)
            .count()
        )

        expired = (
            self.db.query(Retention)
            .filter(
                Retention.is_expired == True,
                Retention.destroyed == False,
            )
            .count()
        )

        expiring_7_days = (
            self.db.query(Retention)
            .filter(
                Retention.is_expired == False,
                Retention.destroyed == False,
                Retention.retention_end > now,
                Retention.retention_end <= seven_days_later,
            )
            .count()
        )

        expiring_30_days = (
            self.db.query(Retention)
            .filter(
                Retention.is_expired == False,
                Retention.destroyed == False,
                Retention.retention_end > now,
                Retention.retention_end <= thirty_days_later,
            )
            .count()
        )

        destroyed = self.db.query(Retention).filter(Retention.destroyed == True).count()

        return RetentionExpireStats(
            total_active=total_active,
            expired=expired,
            expiring_7_days=expiring_7_days,
            expiring_30_days=expiring_30_days,
            destroyed=destroyed,
        )

    def to_response(self, retention: Retention) -> RetentionResponse:
        return RetentionResponse(
            id=retention.id,
            sample_id=retention.sample_id,
            sample_code=retention.sample.sample_code,
            location_id=retention.location_id,
            location_code=retention.location.location_code,
            retention_start=retention.retention_start,
            retention_end=retention.retention_end,
            retention_period_days=retention.retention_period_days,
            status=retention.status,
            is_expired=retention.is_expired,
            destroyed=retention.destroyed,
            destroyed_at=retention.destroyed_at,
            created_at=retention.created_at,
        )

    def to_location_response(self, location: RetentionLocation) -> RetentionLocationResponse:
        sample_code = None
        if location.is_occupied and location.samples:
            active_sample = next((s for s in location.samples if not s.is_destroyed), None)
            if active_sample:
                sample_code = active_sample.sample_code

        return RetentionLocationResponse(
            id=location.id,
            location_code=location.location_code,
            zone=location.zone,
            shelf=location.shelf,
            position=location.position,
            is_occupied=location.is_occupied,
            sample_code=sample_code,
            temperature=location.temperature,
            humidity=location.humidity,
        )
