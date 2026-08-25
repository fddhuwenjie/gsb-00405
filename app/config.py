from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    APP_NAME: str = "质检样品留样与复检流程服务"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    EXPORT_DIR: Path = BASE_DIR / "exports"
    DB_PATH: Path = DATA_DIR / "quality_inspection.db"

    SAMPLE_CODE_PREFIX: str = "SP"
    RETENTION_PERIOD_DAYS: int = 90
    WAREHOUSE_ZONES: list = ["A", "B", "C"]
    SHELVES_PER_ZONE: int = 10
    POSITIONS_PER_SHELF: int = 20

    def ensure_dirs(self):
        self.DATA_DIR.mkdir(exist_ok=True)
        self.EXPORT_DIR.mkdir(exist_ok=True)


settings = Settings()
settings.ensure_dirs()

DATABASE_URL = f"sqlite:///{settings.DB_PATH}"
