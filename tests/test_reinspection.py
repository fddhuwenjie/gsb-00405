#!/usr/bin/env python3
"""
复检流程状态与数据关联 - 验收测试

执行方式:
    python3 -m pytest tests/test_reinspection.py -v

覆盖内容:
1. 错样品：报告与样品不匹配时禁止申请复检
2. 非原始报告：基于复检报告申请复检被拒绝
3. 原始报告停用后不能再次申请复检
4. 复检检测项目未全部完成（缺项/未判定/未开始）不能进入完成状态
5. 差异确认不可重复
6. 差异确认后批次按最终判定进入完成/拒收，并重算风险等级
7. 最终判定非法（非 pass/fail）时拒绝确认
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from app.database import Base, get_db


@pytest.fixture()
def client(tmp_path):
    db_path = tmp_path / "test_reinspection.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def create_test_items(client):
    items = [
        {"item_code": "RI-PH-001", "item_name": "pH值", "lower_limit": 6.5, "upper_limit": 7.5, "unit": "pH"},
        {"item_code": "RI-WT-001", "item_name": "水分", "lower_limit": 0, "upper_limit": 13.0, "unit": "%"},
        {"item_code": "RI-AS-001", "item_name": "灰分", "lower_limit": 0, "upper_limit": 1.5, "unit": "%"},
    ]
    item_ids = []
    for item in items:
        resp = client.post("/api/v1/tests/items", json=item)
        assert resp.status_code == 200, resp.text
        item_ids.append(resp.json()["id"])
    return item_ids


def setup_batch_with_report(client, batch_no, product_name, values, item_ids):
    batch_resp = client.post(
        "/api/v1/batches",
        json={
            "batch_no": batch_no,
            "product_name": product_name,
            "production_date": "2024-02-01T10:00:00",
            "quantity": 500,
            "production_line": "L1",
        },
    )
    assert batch_resp.status_code == 200, batch_resp.text
    batch = batch_resp.json()

    sample_resp = client.post(
        "/api/v1/samples",
        json={"batch_id": batch["id"], "sampling_person": "质检员", "sample_type": "production"},
    )
    assert sample_resp.status_code == 200, sample_resp.text
    sample = sample_resp.json()

    for item_id, value in zip(item_ids, values):
        tr_resp = client.post(
            "/api/v1/tests/results",
            json={
                "sample_id": sample["id"],
                "test_item_id": item_id,
                "test_value": str(value),
                "numeric_value": value,
                "tester": "检测员",
            },
        )
        assert tr_resp.status_code == 200, tr_resp.text

    report_resp = client.post(f"/api/v1/reports/original/{sample['id']}?issued_by=审核员")
    assert report_resp.status_code == 200, report_resp.text
    return batch, sample, report_resp.json()


def apply_reinspection(client, sample_id, report_id):
    return client.post(
        "/api/v1/reinspections",
        json={
            "original_sample_id": sample_id,
            "original_report_id": report_id,
            "reason": "检测结果异常，申请复检",
            "applicant": "质量工程师",
        },
    )


def enter_reinspection_results(client, reinspection_id, re_sample_id, item_ids, values):
    for item_id, value in zip(item_ids, values):
        body = {
            "sample_id": re_sample_id,
            "test_item_id": item_id,
            "test_value": str(value),
            "numeric_value": value,
            "tester": "复检员",
        }
        resp = client.post(f"/api/v1/reinspections/{reinspection_id}/test-results", json=body)
        assert resp.status_code == 200, resp.text


def confirm_difference(client, reinspection_id, final_judgment, difference_identified=True):
    return client.post(
        f"/api/v1/reinspections/{reinspection_id}/confirm-difference",
        json={
            "difference_identified": difference_identified,
            "difference_remark": "复检差异说明",
            "confirmed_by": "质量主管",
            "final_judgment": final_judgment,
        },
    )


FAIL_VALUES = (6.0, 14.0, 2.0)
PASS_VALUES = (7.0, 10.5, 0.8)


def test_reinspection_wrong_sample_rejected(client):
    """错样品：报告不属于该样品时禁止申请复检"""
    item_ids = create_test_items(client)
    _, sample_a, report_a = setup_batch_with_report(client, "BATCH-RI-001", "错样品产品A", FAIL_VALUES, item_ids)
    _, sample_b, report_b = setup_batch_with_report(client, "BATCH-RI-002", "错样品产品B", FAIL_VALUES, item_ids)

    resp = apply_reinspection(client, sample_a["id"], report_b["id"])
    assert resp.status_code == 400, f"错样品应被拒绝: {resp.text}"
    detail = resp.json()["detail"]
    assert "复检关联错误" in detail
    assert "不匹配" in detail

    reinspections = client.get("/api/v1/reinspections").json()
    assert len(reinspections) == 0, "申请失败不应创建复检记录"


def test_reinspection_based_on_non_original_report_rejected(client):
    """非原始报告：只能基于原始报告申请复检"""
    item_ids = create_test_items(client)
    _, sample, report = setup_batch_with_report(client, "BATCH-RI-010", "非原始报告产品", FAIL_VALUES, item_ids)

    ri_resp = apply_reinspection(client, sample["id"], report["id"])
    assert ri_resp.status_code == 200, ri_resp.text
    ri = ri_resp.json()

    enter_reinspection_results(client, ri["id"], ri["re_sample_id"], item_ids, PASS_VALUES)
    assert client.post(f"/api/v1/reinspections/{ri['id']}/complete-testing").status_code == 200
    assert confirm_difference(client, ri["id"], "pass").status_code == 200

    re_report_resp = client.post(f"/api/v1/reinspections/{ri['id']}/report?issued_by=审核员")
    assert re_report_resp.status_code == 200, re_report_resp.text
    reinspection_report = re_report_resp.json()
    assert reinspection_report["report_type"] == "reinspection"

    resp = apply_reinspection(client, ri["re_sample_id"], reinspection_report["id"])
    assert resp.status_code == 400, f"非原始报告应被拒绝: {resp.text}"
    assert "只能基于原始报告" in resp.json()["detail"]


def test_reinspection_reapply_with_inactive_report_rejected(client):
    """原始报告被停用后不能再次申请复检"""
    item_ids = create_test_items(client)
    _, sample, report = setup_batch_with_report(client, "BATCH-RI-020", "重复申请产品", FAIL_VALUES, item_ids)

    first = apply_reinspection(client, sample["id"], report["id"])
    assert first.status_code == 200, first.text

    inactive_report = client.get(f"/api/v1/reports/{report['id']}").json()
    assert inactive_report["is_active"] is False, "申请复检后原始报告应被停用"

    second = apply_reinspection(client, sample["id"], report["id"])
    assert second.status_code == 400, f"停用报告应无法再次申请: {second.text}"
    assert "停用" in second.json()["detail"]

    reinspections = client.get(
        "/api/v1/reinspections", params={"original_sample_id": sample["id"]}
    ).json()
    assert len(reinspections) == 1, "重复申请不应创建第二条复检记录"


def test_complete_testing_with_missing_items_blocked(client):
    """未完成检测：必检项目缺项时不能进入完成状态"""
    item_ids = create_test_items(client)
    _, sample, report = setup_batch_with_report(client, "BATCH-RI-030", "缺项产品", FAIL_VALUES, item_ids)

    ri = apply_reinspection(client, sample["id"], report["id"]).json()

    resp = client.post(f"/api/v1/reinspections/{ri['id']}/complete-testing")
    assert resp.status_code == 400, f"未录入任何结果不应允许完成: {resp.text}"

    client.post(
        f"/api/v1/reinspections/{ri['id']}/test-results",
        json={
            "sample_id": ri["re_sample_id"],
            "test_item_id": item_ids[0],
            "test_value": "7.0",
            "numeric_value": 7.0,
            "tester": "复检员",
        },
    )

    resp = client.post(f"/api/v1/reinspections/{ri['id']}/complete-testing")
    assert resp.status_code == 400, f"检测项目未完成应被拒绝: {resp.text}"
    assert "检测项目缺失" in resp.json()["detail"]

    detail = client.get(f"/api/v1/reinspections/{ri['id']}").json()
    assert detail["status"] == "testing", "校验失败后复检状态不应变为 completed"


def test_complete_testing_with_pending_judgment_blocked(client):
    """未完成检测：结果未判定（无有效判定值）时不能进入完成状态"""
    item_ids = create_test_items(client)
    _, sample, report = setup_batch_with_report(client, "BATCH-RI-031", "未判定产品", FAIL_VALUES, item_ids)

    ri = apply_reinspection(client, sample["id"], report["id"]).json()

    enter_reinspection_results(client, ri["id"], ri["re_sample_id"], item_ids[:2], PASS_VALUES[:2])
    pending_resp = client.post(
        f"/api/v1/reinspections/{ri['id']}/test-results",
        json={
            "sample_id": ri["re_sample_id"],
            "test_item_id": item_ids[2],
            "test_value": "未检出",
            "numeric_value": None,
            "tester": "复检员",
        },
    )
    assert pending_resp.status_code == 200, pending_resp.text
    assert pending_resp.json()["judgment"] == "pending"

    resp = client.post(f"/api/v1/reinspections/{ri['id']}/complete-testing")
    assert resp.status_code == 400, f"存在未判定结果时应被拒绝: {resp.text}"
    assert "检测项目缺失" in resp.json()["detail"]


def test_duplicate_confirm_blocked(client):
    """重复确认：差异确认只能执行一次"""
    item_ids = create_test_items(client)
    _, sample, report = setup_batch_with_report(client, "BATCH-RI-040", "重复确认产品", FAIL_VALUES, item_ids)

    ri = apply_reinspection(client, sample["id"], report["id"]).json()
    enter_reinspection_results(client, ri["id"], ri["re_sample_id"], item_ids, PASS_VALUES)
    assert client.post(f"/api/v1/reinspections/{ri['id']}/complete-testing").status_code == 200

    first = confirm_difference(client, ri["id"], "pass")
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "confirmed"

    second = confirm_difference(client, ri["id"], "pass")
    assert second.status_code == 400, f"重复确认应被拒绝: {second.text}"
    assert "状态无效" in second.json()["detail"]


def test_confirm_pass_sets_batch_completed_and_recalculates_risk(client):
    """差异确认合格：批次进入完成状态并重算风险等级"""
    item_ids = create_test_items(client)
    batch, sample, report = setup_batch_with_report(client, "BATCH-RI-050", "确认合格产品", FAIL_VALUES, item_ids)

    ri = apply_reinspection(client, sample["id"], report["id"]).json()
    enter_reinspection_results(client, ri["id"], ri["re_sample_id"], item_ids, PASS_VALUES)
    assert client.post(f"/api/v1/reinspections/{ri['id']}/complete-testing").status_code == 200

    resp = confirm_difference(client, ri["id"], "pass")
    assert resp.status_code == 200, resp.text

    batch_after = client.get(f"/api/v1/batches/{batch['id']}").json()
    assert batch_after["status"] == "completed", "复检合格后批次应为 completed"
    assert batch_after["final_result"] == "pass"
    assert batch_after["risk_level"] in ("low", "medium", "high"), "风险等级应重新计算"
    assert batch_after["risk_score"] > 0, "原始不合格与复检差异应体现在风险评分中"

    ri_after = client.get(f"/api/v1/reinspections/{ri['id']}").json()
    assert ri_after["status"] == "confirmed"
    assert ri_after["final_judgment"] == "pass"


def test_confirm_fail_sets_batch_rejected(client):
    """差异确认不合格：批次进入拒收状态"""
    item_ids = create_test_items(client)
    batch, sample, report = setup_batch_with_report(client, "BATCH-RI-051", "确认拒收产品", FAIL_VALUES, item_ids)

    ri = apply_reinspection(client, sample["id"], report["id"]).json()
    enter_reinspection_results(client, ri["id"], ri["re_sample_id"], item_ids, FAIL_VALUES)
    assert client.post(f"/api/v1/reinspections/{ri['id']}/complete-testing").status_code == 200

    resp = confirm_difference(client, ri["id"], "fail")
    assert resp.status_code == 200, resp.text

    batch_after = client.get(f"/api/v1/batches/{batch['id']}").json()
    assert batch_after["status"] == "rejected", "复检不合格后批次应为 rejected"
    assert batch_after["final_result"] == "fail"
    assert batch_after["risk_level"] in ("low", "medium", "high")
    assert batch_after["risk_score"] > 0


def test_confirm_with_invalid_judgment_blocked(client):
    """非法最终判定：非 pass/fail 的判定不能确认差异"""
    item_ids = create_test_items(client)
    _, sample, report = setup_batch_with_report(client, "BATCH-RI-060", "非法判定产品", FAIL_VALUES, item_ids)

    ri = apply_reinspection(client, sample["id"], report["id"]).json()
    enter_reinspection_results(client, ri["id"], ri["re_sample_id"], item_ids, PASS_VALUES)
    assert client.post(f"/api/v1/reinspections/{ri['id']}/complete-testing").status_code == 200

    resp = confirm_difference(client, ri["id"], "pending")
    assert resp.status_code == 400, f"非法判定应被拒绝: {resp.text}"
    assert "最终判定无效" in resp.json()["detail"]

    ri_after = client.get(f"/api/v1/reinspections/{ri['id']}").json()
    assert ri_after["status"] == "completed", "非法确认不应改变复检状态"
    assert ri_after["final_judgment"] is None
