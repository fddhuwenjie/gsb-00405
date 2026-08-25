from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import random
import string

from ..config import settings


class BaseService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def generate_code(prefix: str, length: int = 8) -> str:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        random_str = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
        return f"{prefix}{timestamp}{random_str}"

    @staticmethod
    def parse_datetime(value) -> datetime:
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value

    @staticmethod
    def add_days(date: datetime, days: int) -> datetime:
        return date + timedelta(days=days)

    @staticmethod
    def days_between(start: datetime, end: datetime) -> int:
        return (end - start).days
