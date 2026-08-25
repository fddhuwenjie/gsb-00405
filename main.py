from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.database import init_db
from app.routers import (
    batch_router,
    sample_router,
    test_router,
    retention_router,
    reinspection_router,
    report_router,
    export_router,
    stats_router,
    arbitration_router,
    regulatory_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="质检样品留样与复检流程服务 - 支持送样、检测、判定、留样、复检、差异确认和放行全流程",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(batch_router, prefix="/api/v1")
app.include_router(sample_router, prefix="/api/v1")
app.include_router(test_router, prefix="/api/v1")
app.include_router(retention_router, prefix="/api/v1")
app.include_router(reinspection_router, prefix="/api/v1")
app.include_router(report_router, prefix="/api/v1")
app.include_router(export_router, prefix="/api/v1")
app.include_router(stats_router, prefix="/api/v1")
app.include_router(arbitration_router, prefix="/api/v1")
app.include_router(regulatory_router, prefix="/api/v1")


@app.get("/", summary="健康检查")
async def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", summary="健康检查")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )
