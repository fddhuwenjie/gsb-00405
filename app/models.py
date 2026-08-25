from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime

from .database import Base


class Batch(Base):
    __tablename__ = "batches"

    id = Column(Integer, primary_key=True, index=True)
    batch_no = Column(String(50), unique=True, index=True, nullable=False)
    product_name = Column(String(200), nullable=False)
    production_date = Column(DateTime, nullable=False)
    quantity = Column(Integer, nullable=False)
    production_line = Column(String(100))
    status = Column(String(20), default="pending", nullable=False)
    final_result = Column(String(20))
    risk_level = Column(String(20), default="low")
    risk_score = Column(Float, default=0.0)
    released = Column(Boolean, default=False)
    released_at = Column(DateTime)
    released_by = Column(String(100))
    frozen = Column(Boolean, default=False)
    frozen_at = Column(DateTime)
    frozen_by = Column(String(100))
    frozen_reason = Column(Text)
    release_revoked = Column(Boolean, default=False)
    release_revoked_at = Column(DateTime)
    release_revoked_by = Column(String(100))
    release_revoked_reason = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    remark = Column(Text)

    samples = relationship("Sample", back_populates="batch", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="batch", cascade="all, delete-orphan")
    arbitrations = relationship("Arbitration", back_populates="batch", cascade="all, delete-orphan")
    regulatory_inspections = relationship("RegulatoryInspection", back_populates="batch", cascade="all, delete-orphan")
    regulatory_differences = relationship("RegulatoryDifference", back_populates="batch", cascade="all, delete-orphan")


class Sample(Base):
    __tablename__ = "samples"

    id = Column(Integer, primary_key=True, index=True)
    sample_code = Column(String(50), unique=True, index=True, nullable=False)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    sampling_time = Column(DateTime, default=datetime.now)
    sampling_person = Column(String(100))
    sample_type = Column(String(50), default="production")
    status = Column(String(20), default="collected", nullable=False)
    is_retained = Column(Boolean, default=False)
    is_destroyed = Column(Boolean, default=False)
    destroyed_at = Column(DateTime)
    destroyed_by = Column(String(100))
    retention_location_id = Column(Integer, ForeignKey("retention_locations.id"))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    batch = relationship("Batch", back_populates="samples")
    test_results = relationship("TestResult", back_populates="sample", cascade="all, delete-orphan")
    retention = relationship("Retention", uselist=False, back_populates="sample", cascade="all, delete-orphan")
    retention_location = relationship("RetentionLocation", back_populates="samples")
    original_for_reinspections = relationship(
        "ReInspection",
        foreign_keys="ReInspection.original_sample_id",
        back_populates="original_sample"
    )
    re_inspections = relationship(
        "ReInspection",
        foreign_keys="ReInspection.re_sample_id",
        back_populates="re_sample",
        cascade="all, delete-orphan"
    )


class TestItem(Base):
    __tablename__ = "test_items"

    id = Column(Integer, primary_key=True, index=True)
    item_code = Column(String(50), unique=True, index=True, nullable=False)
    item_name = Column(String(200), nullable=False)
    category = Column(String(100))
    unit = Column(String(20))
    standard_value = Column(String(200))
    lower_limit = Column(Float)
    upper_limit = Column(Float)
    test_method = Column(String(500))
    is_mandatory = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    results = relationship("TestResult", back_populates="test_item")


class TestResult(Base):
    __tablename__ = "test_results"

    id = Column(Integer, primary_key=True, index=True)
    sample_id = Column(Integer, ForeignKey("samples.id"), nullable=False)
    test_item_id = Column(Integer, ForeignKey("test_items.id"), nullable=False)
    is_reinspection = Column(Boolean, default=False)
    reinspection_id = Column(Integer, ForeignKey("re_inspections.id"))
    test_value = Column(String(100))
    numeric_value = Column(Float)
    tester = Column(String(100))
    test_time = Column(DateTime, default=datetime.now)
    instrument = Column(String(200))
    result_status = Column(String(20), default="pending")
    judgment = Column(String(20))
    remark = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    sample = relationship("Sample", back_populates="test_results")
    test_item = relationship("TestItem", back_populates="results")
    reinspection = relationship("ReInspection", back_populates="test_results")


class RetentionLocation(Base):
    __tablename__ = "retention_locations"

    id = Column(Integer, primary_key=True, index=True)
    location_code = Column(String(50), unique=True, index=True, nullable=False)
    zone = Column(String(10), nullable=False)
    shelf = Column(Integer, nullable=False)
    position = Column(Integer, nullable=False)
    is_occupied = Column(Boolean, default=False)
    temperature = Column(Float)
    humidity = Column(Float)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    samples = relationship("Sample", back_populates="retention_location")
    retentions = relationship("Retention", back_populates="location")


class Retention(Base):
    __tablename__ = "retentions"

    id = Column(Integer, primary_key=True, index=True)
    sample_id = Column(Integer, ForeignKey("samples.id"), unique=True, nullable=False)
    location_id = Column(Integer, ForeignKey("retention_locations.id"), nullable=False)
    retention_start = Column(DateTime, default=datetime.now)
    retention_end = Column(DateTime, nullable=False)
    retention_period_days = Column(Integer, nullable=False)
    status = Column(String(20), default="active", nullable=False)
    is_expired = Column(Boolean, default=False)
    destroyed = Column(Boolean, default=False)
    destroyed_at = Column(DateTime)
    destroyed_by = Column(String(100))
    destroy_remark = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    sample = relationship("Sample", back_populates="retention")
    location = relationship("RetentionLocation", back_populates="retentions")


class ReInspection(Base):
    __tablename__ = "re_inspections"

    id = Column(Integer, primary_key=True, index=True)
    reinspection_code = Column(String(50), unique=True, index=True, nullable=False)
    original_sample_id = Column(Integer, ForeignKey("samples.id"), nullable=False)
    original_report_id = Column(Integer, ForeignKey("reports.id"), nullable=False)
    re_sample_id = Column(Integer, ForeignKey("samples.id"), nullable=False)
    reason = Column(Text, nullable=False)
    applicant = Column(String(100), nullable=False)
    apply_time = Column(DateTime, default=datetime.now)
    status = Column(String(20), default="pending", nullable=False)
    difference_identified = Column(Boolean)
    difference_confirmed_by = Column(String(100))
    difference_confirmed_at = Column(DateTime)
    difference_remark = Column(Text)
    final_judgment = Column(String(20))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    original_sample = relationship("Sample", foreign_keys=[original_sample_id], back_populates="original_for_reinspections")
    original_report = relationship("Report", foreign_keys=[original_report_id], back_populates="re_inspections")
    re_sample = relationship("Sample", foreign_keys=[re_sample_id], back_populates="re_inspections")
    test_results = relationship("TestResult", back_populates="reinspection")


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    report_no = Column(String(50), unique=True, index=True, nullable=False)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    sample_id = Column(Integer, ForeignKey("samples.id"), nullable=False)
    report_type = Column(String(20), default="original", nullable=False)
    reinspection_id = Column(Integer, ForeignKey("re_inspections.id"))
    overall_judgment = Column(String(20), nullable=False)
    issued_by = Column(String(100))
    issued_at = Column(DateTime, default=datetime.now)
    auditor = Column(String(100))
    audited_at = Column(DateTime)
    approver = Column(String(100))
    approved_at = Column(DateTime)
    is_active = Column(Boolean, default=True)
    remark = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    batch = relationship("Batch", back_populates="reports")
    sample = relationship("Sample")
    re_inspections = relationship("ReInspection", foreign_keys="ReInspection.original_report_id", back_populates="original_report")


class Arbitration(Base):
    __tablename__ = "arbitrations"

    id = Column(Integer, primary_key=True, index=True)
    arbitration_code = Column(String(50), unique=True, index=True, nullable=False)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    reinspection_id = Column(Integer, ForeignKey("re_inspections.id"), nullable=False)
    original_report_id = Column(Integer, ForeignKey("reports.id"), nullable=False)
    reinspection_report_id = Column(Integer, ForeignKey("reports.id"), nullable=False)
    dispute_source = Column(Text, nullable=False)
    dispute_items = Column(Text, nullable=False)
    arbitrator = Column(String(100), nullable=False)
    handling_opinion = Column(Text)
    final_judgment = Column(String(20))
    status = Column(String(20), default="pending", nullable=False)
    arbitration_report_id = Column(Integer, ForeignKey("reports.id"))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    completed_at = Column(DateTime)

    batch = relationship("Batch", back_populates="arbitrations")
    reinspection = relationship("ReInspection")
    original_report = relationship("Report", foreign_keys=[original_report_id])
    reinspection_report = relationship("Report", foreign_keys=[reinspection_report_id])
    arbitration_report = relationship("Report", foreign_keys=[arbitration_report_id])


class ExportRecord(Base):
    __tablename__ = "export_records"

    id = Column(Integer, primary_key=True, index=True)
    export_no = Column(String(50), unique=True, index=True, nullable=False)
    export_type = Column(String(20), nullable=False)
    batch_id = Column(Integer, ForeignKey("batches.id"))
    report_id = Column(Integer, ForeignKey("reports.id"))
    file_format = Column(String(10), default="xlsx", nullable=False)
    file_name = Column(String(200), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer)
    exported_by = Column(String(100))
    exported_at = Column(DateTime, default=datetime.now)
    include_original = Column(Boolean, default=True)
    include_reinspection = Column(Boolean, default=True)
    include_final = Column(Boolean, default=True)
    include_arbitration = Column(Boolean, default=True)
    include_regulatory = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)

    batch = relationship("Batch")
    report = relationship("Report")


class RegulatoryInspection(Base):
    __tablename__ = "regulatory_inspections"

    id = Column(Integer, primary_key=True, index=True)
    inspection_code = Column(String(50), unique=True, index=True, nullable=False)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    sample_id = Column(Integer, ForeignKey("samples.id"))
    original_report_id = Column(Integer, ForeignKey("reports.id"))
    reinspection_report_id = Column(Integer, ForeignKey("reports.id"))
    arbitration_report_id = Column(Integer, ForeignKey("reports.id"))
    inspection_agency = Column(String(200), nullable=False)
    inspector = Column(String(100), nullable=False)
    inspection_date = Column(DateTime, nullable=False)
    inspection_type = Column(String(50), default="spot_check")
    inspection_basis = Column(String(500))
    sampling_location = Column(String(200))
    overall_conclusion = Column(String(20))
    inspection_remark = Column(Text)
    created_by = Column(String(100))
    status = Column(String(20), default="draft", nullable=False)
    difference_generated = Column(Boolean, default=False)
    difference_id = Column(Integer, ForeignKey("regulatory_differences.id"))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    batch = relationship("Batch", back_populates="regulatory_inspections")
    sample = relationship("Sample", foreign_keys=[sample_id])
    original_report = relationship("Report", foreign_keys=[original_report_id])
    reinspection_report = relationship("Report", foreign_keys=[reinspection_report_id])
    arbitration_report = relationship("Report", foreign_keys=[arbitration_report_id])
    difference = relationship("RegulatoryDifference", foreign_keys=[difference_id], back_populates="inspections")
    item_results = relationship("RegulatoryInspectionItem", back_populates="inspection", cascade="all, delete-orphan")


class RegulatoryInspectionItem(Base):
    __tablename__ = "regulatory_inspection_items"

    id = Column(Integer, primary_key=True, index=True)
    inspection_id = Column(Integer, ForeignKey("regulatory_inspections.id"), nullable=False)
    test_item_id = Column(Integer, ForeignKey("test_items.id"), nullable=False)
    enterprise_value = Column(String(100))
    enterprise_numeric_value = Column(Float)
    enterprise_judgment = Column(String(20))
    regulatory_value = Column(String(100))
    regulatory_numeric_value = Column(Float)
    regulatory_judgment = Column(String(20))
    is_consistent = Column(Boolean)
    difference_detail = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    inspection = relationship("RegulatoryInspection", back_populates="item_results")
    test_item = relationship("TestItem")


class RegulatoryDifference(Base):
    __tablename__ = "regulatory_differences"

    id = Column(Integer, primary_key=True, index=True)
    difference_code = Column(String(50), unique=True, index=True, nullable=False)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    source_inspection_id = Column(Integer, ForeignKey("regulatory_inspections.id"), nullable=False)
    difference_type = Column(String(50))
    difference_items_summary = Column(Text)
    enterprise_judgment = Column(String(20))
    regulatory_judgment = Column(String(20))
    difference_reason = Column(Text)
    handler = Column(String(100))
    handling_measures = Column(Text)
    handling_status = Column(String(20), default="pending", nullable=False)
    batch_frozen = Column(Boolean, default=False)
    release_revoked = Column(Boolean, default=False)
    closed_at = Column(DateTime)
    closed_by = Column(String(100))
    closing_remark = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    batch = relationship("Batch", back_populates="regulatory_differences")
    source_inspection = relationship("RegulatoryInspection", foreign_keys=[source_inspection_id])
    inspections = relationship("RegulatoryInspection", foreign_keys="RegulatoryInspection.difference_id", back_populates="difference")


class CrossBatchRiskRecord(Base):
    __tablename__ = "cross_batch_risk_records"

    id = Column(Integer, primary_key=True, index=True)
    record_date = Column(DateTime, default=datetime.now, nullable=False)
    risk_type = Column(String(50), nullable=False)
    risk_level = Column(String(20), default="medium")
    scope_dimension = Column(String(50))
    scope_value = Column(String(200))
    affected_batch_count = Column(Integer, default=0)
    affected_batch_ids = Column(JSON)
    description = Column(Text)
    detail_data = Column(JSON)
    generated_at = Column(DateTime, default=datetime.now)

    __mapper_args__ = {
        "primary_key": [id],
    }
