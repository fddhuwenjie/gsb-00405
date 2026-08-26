from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime, date
from enum import Enum


def _parse_datetime_or_date(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    if isinstance(v, str):
        s = v.strip()
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            try:
                d = date.fromisoformat(s)
                return datetime(d.year, d.month, d.day)
            except Exception:
                pass
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            pass
    return v


def _normalize_conclusion(v):
    """将监管抽检总体结论的中文/英文统一为英文枚举值"""
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        if s in ("合格", "通过", "pass", "PASS", "Pass"):
            return "pass"
        if s in ("不合格", "不通过", "fail", "FAIL", "Fail"):
            return "fail"
    return v


class BatchStatus(str, Enum):
    PENDING = "pending"
    SAMPLING = "sampling"
    TESTING = "testing"
    JUDGING = "judging"
    RETAINING = "retaining"
    COMPLETED = "completed"
    REJECTED = "rejected"
    REINSPECTING = "reinspecting"


class Judgment(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    PENDING = "pending"


class ReportType(str, Enum):
    ORIGINAL = "original"
    REINSPECTION = "reinspection"
    FINAL = "final"
    ARBITRATION = "arbitration"


class ArbitrationStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RetentionStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    DESTROYED = "destroyed"


class ReInspectionStatus(str, Enum):
    PENDING = "pending"
    TESTING = "testing"
    COMPLETED = "completed"
    CONFIRMED = "confirmed"


class BatchCreate(BaseModel):
    batch_no: str = Field(..., max_length=50, description="批次号")
    product_name: str = Field(..., max_length=200, description="产品名称")
    production_date: datetime = Field(..., description="生产日期")
    quantity: int = Field(..., gt=0, description="生产数量")
    production_line: Optional[str] = Field(None, max_length=100, description="生产线")
    remark: Optional[str] = Field(None, description="备注")

    @field_validator("production_date", mode="before")
    @classmethod
    def _pd(cls, v):
        return _parse_datetime_or_date(v)


class BatchUpdate(BaseModel):
    product_name: Optional[str] = Field(None, max_length=200)
    production_date: Optional[datetime] = None
    quantity: Optional[int] = Field(None, gt=0)
    production_line: Optional[str] = Field(None, max_length=100)
    remark: Optional[str] = None

    @field_validator("production_date", mode="before")
    @classmethod
    def _pd(cls, v):
        return _parse_datetime_or_date(v)


class BatchResponse(BaseModel):
    id: int
    batch_no: str
    product_name: str
    production_date: datetime
    quantity: int
    production_line: Optional[str]
    status: str
    final_result: Optional[str]
    risk_level: str
    risk_score: float
    released: bool
    released_at: Optional[datetime]
    released_by: Optional[str]
    frozen: bool
    frozen_at: Optional[datetime]
    frozen_by: Optional[str]
    frozen_reason: Optional[str]
    release_revoked: bool
    release_revoked_at: Optional[datetime]
    release_revoked_by: Optional[str]
    release_revoked_reason: Optional[str]
    created_at: datetime
    updated_at: datetime
    remark: Optional[str]

    class Config:
        from_attributes = True


class ArbitrationCreate(BaseModel):
    reinspection_id: int = Field(..., description="复检记录ID")
    dispute_source: str = Field(..., description="争议来源")
    dispute_items: List[int] = Field(..., description="争议检测项ID列表")
    arbitrator: str = Field(..., max_length=100, description="仲裁负责人")


class ArbitrationProcess(BaseModel):
    handling_opinion: str = Field(..., description="处理意见")
    final_judgment: str = Field(..., max_length=20, description="最终判定")


class ArbitrationResponse(BaseModel):
    id: int
    arbitration_code: str
    batch_id: int
    batch_no: str
    reinspection_id: int
    reinspection_code: str
    original_report_id: int
    original_report_no: str
    reinspection_report_id: int
    reinspection_report_no: str
    dispute_source: str
    dispute_items: List[int]
    arbitrator: str
    handling_opinion: Optional[str]
    final_judgment: Optional[str]
    status: str
    arbitration_report_id: Optional[int]
    arbitration_report_no: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class RiskLevelStats(BaseModel):
    total_batches: int
    low_risk: int
    medium_risk: int
    high_risk: int
    low_risk_rate: float
    medium_risk_rate: float
    high_risk_rate: float


class SampleCreate(BaseModel):
    batch_id: int = Field(..., description="批次ID")
    sampling_person: Optional[str] = Field(None, max_length=100, description="取样人")
    sample_type: Optional[str] = Field("production", max_length=50, description="样品类型")


class SampleResponse(BaseModel):
    id: int
    sample_code: str
    batch_id: int
    batch_no: str
    sampling_time: datetime
    sampling_person: Optional[str]
    sample_type: str
    status: str
    is_retained: bool
    is_destroyed: bool
    retention_location: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class TestItemCreate(BaseModel):
    item_code: str = Field(..., max_length=50, description="检测项编码")
    item_name: str = Field(..., max_length=200, description="检测项名称")
    category: Optional[str] = Field(None, max_length=100, description="分类")
    unit: Optional[str] = Field(None, max_length=20, description="单位")
    standard_value: Optional[str] = Field(None, max_length=200, description="标准值")
    lower_limit: Optional[float] = Field(None, description="下限")
    upper_limit: Optional[float] = Field(None, description="上限")
    test_method: Optional[str] = Field(None, max_length=500, description="检测方法")
    is_mandatory: bool = Field(True, description="是否必检")


class TestItemResponse(BaseModel):
    id: int
    item_code: str
    item_name: str
    category: Optional[str]
    unit: Optional[str]
    standard_value: Optional[str]
    lower_limit: Optional[float]
    upper_limit: Optional[float]
    test_method: Optional[str]
    is_mandatory: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TestResultCreate(BaseModel):
    sample_id: int = Field(..., description="样品ID")
    test_item_id: int = Field(..., description="检测项ID")
    test_value: str = Field(..., max_length=100, description="检测值")
    numeric_value: Optional[float] = Field(None, description="数值化结果")
    tester: str = Field(..., max_length=100, description="检测人")
    instrument: Optional[str] = Field(None, max_length=200, description="检测仪器")
    test_time: Optional[datetime] = Field(default_factory=datetime.now, description="检测时间")


class TestResultUpdate(BaseModel):
    test_value: Optional[str] = Field(None, max_length=100)
    numeric_value: Optional[float] = None
    tester: Optional[str] = Field(None, max_length=100)
    instrument: Optional[str] = Field(None, max_length=200)
    judgment: Optional[str] = Field(None, max_length=20)
    remark: Optional[str] = None


class TestResultResponse(BaseModel):
    id: int
    sample_id: int
    sample_code: str
    test_item_id: int
    test_item_code: str
    test_item_name: str
    is_reinspection: bool
    test_value: str
    numeric_value: Optional[float]
    tester: str
    test_time: datetime
    instrument: Optional[str]
    judgment: Optional[str]
    standard_value: Optional[str]
    lower_limit: Optional[float]
    upper_limit: Optional[float]
    unit: Optional[str]
    remark: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class RetentionCreate(BaseModel):
    sample_id: int = Field(..., description="样品ID")
    retention_period_days: Optional[int] = Field(None, description="留样天数，默认90天")


class RetentionResponse(BaseModel):
    id: int
    sample_id: int
    sample_code: str
    location_id: int
    location_code: str
    retention_start: datetime
    retention_end: datetime
    retention_period_days: int
    status: str
    is_expired: bool
    destroyed: bool
    destroyed_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class RetentionLocationResponse(BaseModel):
    id: int
    location_code: str
    zone: str
    shelf: int
    position: int
    is_occupied: bool
    sample_code: Optional[str]
    temperature: Optional[float]
    humidity: Optional[float]

    class Config:
        from_attributes = True


class ReInspectionCreate(BaseModel):
    original_sample_id: int = Field(..., description="原始样品ID")
    original_report_id: int = Field(..., description="原始报告ID")
    reason: str = Field(..., description="复检原因")
    applicant: str = Field(..., max_length=100, description="申请人")


class ReInspectionResponse(BaseModel):
    id: int
    reinspection_code: str
    original_sample_id: int
    original_sample_code: str
    original_report_id: int
    original_report_no: str
    re_sample_id: int
    re_sample_code: str
    reason: str
    applicant: str
    apply_time: datetime
    status: str
    difference_identified: Optional[bool]
    difference_confirmed_by: Optional[str]
    difference_confirmed_at: Optional[datetime]
    difference_remark: Optional[str]
    final_judgment: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class DifferenceConfirm(BaseModel):
    difference_identified: bool = Field(..., description="是否确认有差异")
    difference_remark: Optional[str] = Field(None, description="差异说明")
    confirmed_by: str = Field(..., max_length=100, description="确认人")
    final_judgment: str = Field(..., max_length=20, description="最终判定")

    @field_validator("final_judgment", mode="before")
    @classmethod
    def _fj(cls, v):
        v = _normalize_conclusion(v)
        if v not in (Judgment.PASS.value, Judgment.FAIL.value):
            raise ValueError("最终判定只能为 pass 或 fail")
        return v


class ReportResponse(BaseModel):
    id: int
    report_no: str
    batch_id: int
    batch_no: str
    sample_id: int
    sample_code: str
    report_type: str
    overall_judgment: str
    issued_by: Optional[str]
    issued_at: datetime
    auditor: Optional[str]
    audited_at: Optional[datetime]
    approver: Optional[str]
    approved_at: Optional[datetime]
    is_active: bool
    test_results: List[TestResultResponse] = []
    created_at: datetime

    class Config:
        from_attributes = True


class BatchRelease(BaseModel):
    released_by: str = Field(..., max_length=100, description="放行人")
    remark: Optional[str] = Field(None, description="放行备注")


class RetentionDestroy(BaseModel):
    destroyed_by: str = Field(..., max_length=100, description="销毁人")
    destroy_remark: Optional[str] = Field(None, description="销毁说明")


class BatchQualityArchive(BaseModel):
    batch: BatchResponse
    samples: List[SampleResponse]
    original_report: Optional[ReportResponse]
    reinspection_reports: List[ReportResponse]
    final_report: Optional[ReportResponse]
    arbitration_reports: List[ReportResponse]
    retention: Optional[RetentionResponse]
    reinspections: List[ReInspectionResponse]
    arbitrations: List[ArbitrationResponse]


class RetentionLocationQuery(BaseModel):
    zone: Optional[str] = Field(None, description="库区")
    shelf: Optional[int] = Field(None, description="货架")
    is_occupied: Optional[bool] = Field(None, description="是否占用")


class ReInspectionDiffStats(BaseModel):
    total_reinspections: int
    with_difference: int
    without_difference: int
    pass_after_reinspection: int
    fail_after_reinspection: int
    difference_rate: float


class ExportRequest(BaseModel):
    batch_id: Optional[int] = Field(None, description="批次ID")
    report_id: Optional[int] = Field(None, description="报告ID")
    file_format: str = Field("xlsx", description="导出格式：xlsx/pdf")
    include_original: bool = Field(True, description="包含原始结果")
    include_reinspection: bool = Field(True, description="包含复检结果")
    include_final: bool = Field(True, description="包含最终判定")
    include_arbitration: bool = Field(True, description="包含仲裁结果")
    include_regulatory: bool = Field(True, description="包含监管抽检和风险摘要")
    exported_by: Optional[str] = Field(None, max_length=100, description="导出人")


class ExportRecordResponse(BaseModel):
    id: int
    export_no: str
    export_type: str
    batch_id: Optional[int]
    batch_no: Optional[str]
    report_id: Optional[int]
    report_no: Optional[str]
    file_format: str
    file_name: str
    file_path: str
    file_size: Optional[int]
    exported_by: Optional[str]
    exported_at: datetime
    include_original: bool
    include_reinspection: bool
    include_final: bool
    include_arbitration: bool
    include_regulatory: bool
    download_url: str

    class Config:
        from_attributes = True


class RetentionExpireStats(BaseModel):
    total_active: int
    expired: int
    expiring_7_days: int
    expiring_30_days: int
    destroyed: int


class RegulatoryInspectionStatus(str, Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"


class RegulatoryDifferenceStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    CLOSED = "closed"


class RegulatoryRiskType(str, Enum):
    CONSECUTIVE_FAIL = "consecutive_fail"
    REPEATED_DISPUTE = "repeated_dispute"
    DESTROYED_NO_REVIEW = "destroyed_no_review"
    REGULATORY_DIFFERENCE = "regulatory_difference"


class RegulatoryInspectionItemCreate(BaseModel):
    test_item_id: int = Field(..., description="检测项ID")
    regulatory_value: str = Field(..., max_length=100, description="监管检测值")
    regulatory_numeric_value: Optional[float] = Field(None, description="监管数值化结果")
    regulatory_judgment: Optional[str] = Field(None, max_length=20, description="监管判定")
    difference_detail: Optional[str] = Field(None, description="差异详情")


class RegulatoryInspectionCreate(BaseModel):
    batch_id: int = Field(..., description="批次ID")
    sample_id: Optional[int] = Field(None, description="关联样品ID")
    original_report_id: Optional[int] = Field(None, description="关联原始报告ID")
    reinspection_report_id: Optional[int] = Field(None, description="关联复检报告ID")
    arbitration_report_id: Optional[int] = Field(None, description="关联仲裁报告ID")
    inspection_agency: str = Field(..., max_length=200, description="抽检机构")
    inspector: str = Field(..., max_length=100, description="抽检人员")
    inspection_date: datetime = Field(..., description="抽检日期")
    inspection_type: Optional[str] = Field("spot_check", max_length=50, description="抽检类型")
    inspection_basis: Optional[str] = Field(None, max_length=500, description="抽检依据")
    sampling_location: Optional[str] = Field(None, max_length=200, description="抽样地点")
    overall_conclusion: Optional[str] = Field(None, max_length=20, description="监管抽检总体结论")
    inspection_remark: Optional[str] = Field(None, description="抽检备注")
    item_results: List[RegulatoryInspectionItemCreate] = Field(default_factory=list, description="抽检项目结果列表")
    created_by: Optional[str] = Field(None, max_length=100, description="录入人")

    @field_validator("inspection_date", mode="before")
    @classmethod
    def _id(cls, v):
        return _parse_datetime_or_date(v)

    @field_validator("overall_conclusion", mode="before")
    @classmethod
    def _oc(cls, v):
        return _normalize_conclusion(v)


class RegulatoryInspectionUpdate(BaseModel):
    inspection_agency: Optional[str] = Field(None, max_length=200)
    inspector: Optional[str] = Field(None, max_length=100)
    inspection_date: Optional[datetime] = None
    inspection_type: Optional[str] = Field(None, max_length=50)
    inspection_basis: Optional[str] = Field(None, max_length=500)
    sampling_location: Optional[str] = Field(None, max_length=200)
    overall_conclusion: Optional[str] = Field(None, max_length=20)
    inspection_remark: Optional[str] = None
    item_results: Optional[List[RegulatoryInspectionItemCreate]] = None

    @field_validator("inspection_date", mode="before")
    @classmethod
    def _id(cls, v):
        return _parse_datetime_or_date(v)

    @field_validator("overall_conclusion", mode="before")
    @classmethod
    def _oc(cls, v):
        return _normalize_conclusion(v)


class RegulatoryInspectionItemResponse(BaseModel):
    id: int
    inspection_id: int
    test_item_id: int
    test_item_code: str
    test_item_name: str
    enterprise_value: Optional[str]
    enterprise_numeric_value: Optional[float]
    enterprise_judgment: Optional[str]
    regulatory_value: str
    regulatory_numeric_value: Optional[float]
    regulatory_judgment: Optional[str]
    is_consistent: Optional[bool]
    difference_detail: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class RegulatoryInspectionResponse(BaseModel):
    id: int
    inspection_code: str
    batch_id: int
    batch_no: str
    sample_id: Optional[int]
    sample_code: Optional[str]
    original_report_id: Optional[int]
    original_report_no: Optional[str]
    reinspection_report_id: Optional[int]
    reinspection_report_no: Optional[str]
    arbitration_report_id: Optional[int]
    arbitration_report_no: Optional[str]
    inspection_agency: str
    inspector: str
    inspection_date: datetime
    inspection_type: str
    inspection_basis: Optional[str]
    sampling_location: Optional[str]
    overall_conclusion: Optional[str]
    inspection_remark: Optional[str]
    created_by: Optional[str]
    status: str
    difference_generated: bool
    difference_id: Optional[int]
    item_results: List[RegulatoryInspectionItemResponse] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RegulatoryDifferenceProcess(BaseModel):
    handler: str = Field(..., max_length=100, description="处理人")
    difference_reason: str = Field(..., description="差异原因分析")
    handling_measures: str = Field(..., description="处置措施")


class RegulatoryDifferenceClose(BaseModel):
    closed_by: str = Field(..., max_length=100, description="关闭人")
    closing_remark: str = Field(..., description="关闭备注")


class RegulatoryDifferenceResponse(BaseModel):
    id: int
    difference_code: str
    batch_id: int
    batch_no: str
    source_inspection_id: int
    source_inspection_code: str
    difference_type: Optional[str]
    difference_items_summary: Optional[str]
    enterprise_judgment: Optional[str]
    regulatory_judgment: Optional[str]
    difference_reason: Optional[str]
    handler: Optional[str]
    handling_measures: Optional[str]
    handling_status: str
    batch_frozen: bool
    release_revoked: bool
    closed_at: Optional[datetime]
    closed_by: Optional[str]
    closing_remark: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BatchFreezeRequest(BaseModel):
    frozen_by: str = Field(..., max_length=100, description="冻结操作人")
    frozen_reason: str = Field(..., description="冻结原因")


class BatchUnfreezeRequest(BaseModel):
    unfrozen_by: str = Field(..., max_length=100, description="解冻操作人")
    unfreeze_remark: Optional[str] = Field(None, description="解冻备注")


class ReleaseRevokeRequest(BaseModel):
    revoked_by: str = Field(..., max_length=100, description="撤销操作人")
    revoked_reason: str = Field(..., description="撤销原因")


class CrossBatchRiskTrendQuery(BaseModel):
    risk_type: Optional[str] = Field(None, description="风险类型筛选")
    scope_dimension: Optional[str] = Field(None, description="维度筛选：product/line/test_item")
    scope_value: Optional[str] = Field(None, description="维度值筛选")
    start_date: Optional[datetime] = Field(None, description="开始日期")
    end_date: Optional[datetime] = Field(None, description="结束日期")

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def _sd(cls, v):
        return _parse_datetime_or_date(v)


class CrossBatchRiskSummary(BaseModel):
    risk_type: str
    risk_type_display: str
    affected_count: int
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int


class CrossBatchRiskDetail(BaseModel):
    id: int
    record_date: datetime
    risk_type: str
    risk_type_display: str
    risk_level: str
    scope_dimension: Optional[str]
    scope_value: Optional[str]
    affected_batch_count: int
    affected_batch_ids: Optional[List[int]]
    description: Optional[str]
    detail_data: Optional[dict]
    generated_at: datetime

    class Config:
        from_attributes = True


class CrossBatchRiskResponse(BaseModel):
    summary: List[CrossBatchRiskSummary]
    details: List[CrossBatchRiskDetail]
    generated_at: datetime


class BatchQualityArchive(BaseModel):
    batch: BatchResponse
    samples: List[SampleResponse]
    original_report: Optional[ReportResponse]
    reinspection_reports: List[ReportResponse]
    final_report: Optional[ReportResponse]
    arbitration_reports: List[ReportResponse]
    retention: Optional[RetentionResponse]
    reinspections: List[ReInspectionResponse]
    arbitrations: List[ArbitrationResponse]
    regulatory_inspections: List[RegulatoryInspectionResponse]
    regulatory_differences: List[RegulatoryDifferenceResponse]
    risk_summary: Optional[CrossBatchRiskResponse] = None
