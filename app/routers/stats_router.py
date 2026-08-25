from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from ..database import get_db
from ..services import StatsService
from ..schemas import (
    ReInspectionDiffStats,
    RetentionExpireStats,
    RiskLevelStats,
    CrossBatchRiskTrendQuery,
    CrossBatchRiskResponse,
)

router = APIRouter(prefix="/stats", tags=["统计分析"])


@router.get("/overall", summary="获取整体统计数据")
def get_overall_stats(db: Session = Depends(get_db)):
    service = StatsService(db)
    return service.get_overall_stats()


@router.get("/reinspection-diff", response_model=ReInspectionDiffStats, summary="复检差异统计")
def get_reinspection_diff_stats(
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    service = StatsService(db)
    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None
    return service.get_reinspection_diff_stats(start_dt, end_dt)


@router.get("/batch-quality", summary="批次质量统计")
def get_batch_quality_stats(
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    service = StatsService(db)
    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None
    return service.get_batch_quality_stats(start_dt, end_dt)


@router.get("/reinspection-trend", summary="复检趋势统计")
def get_reinspection_trend(
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    db: Session = Depends(get_db),
):
    service = StatsService(db)
    return service.get_reinspection_trend(days)


@router.get("/reinspection-reasons", summary="复检原因统计")
def get_reinspection_by_reason(
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    service = StatsService(db)
    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None
    return service.get_reinspection_by_reason(start_dt, end_dt)


@router.get("/retention-expire", response_model=RetentionExpireStats, summary="留样过期统计")
def get_retention_expire_stats(db: Session = Depends(get_db)):
    service = StatsService(db)
    return service.get_retention_expire_stats()


@router.get("/risk-level", response_model=RiskLevelStats, summary="风险等级统计")
def get_risk_level_stats(
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    service = StatsService(db)
    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None
    return service.get_risk_level_stats(start_dt, end_dt)


@router.post("/cross-batch-risks", response_model=CrossBatchRiskResponse, summary="跨批次风险趋势分析")
def analyze_cross_batch_risks(
    query: CrossBatchRiskTrendQuery = Body(default_factory=CrossBatchRiskTrendQuery),
    db: Session = Depends(get_db),
):
    service = StatsService(db)
    if query.start_date and isinstance(query.start_date, str):
        query.start_date = datetime.fromisoformat(query.start_date)
    if query.end_date and isinstance(query.end_date, str):
        query.end_date = datetime.fromisoformat(query.end_date)
    return service.analyze_cross_batch_risks(query)


@router.get("/risk-trend-by-product", summary="按产品维度质量风险趋势")
def get_risk_trend_by_product(
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    db: Session = Depends(get_db),
):
    service = StatsService(db)
    return service.get_risk_trend_by_product(days)


@router.get("/risk-trend-by-test-item", summary="按检测项维度不合格趋势")
def get_risk_trend_by_test_item(
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    db: Session = Depends(get_db),
):
    service = StatsService(db)
    return service.get_risk_trend_by_test_item(days)


@router.get("/regulatory-inspection", summary="监管抽检统计")
def get_regulatory_inspection_stats(
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    service = StatsService(db)
    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None
    return service.get_regulatory_inspection_stats(start_dt, end_dt)
