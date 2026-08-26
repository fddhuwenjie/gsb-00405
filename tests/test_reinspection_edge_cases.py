#!/usr/bin/env python3
"""
复检流程边界条件与状态关联测试

测试内容:
1. 错样品 - 录入复检结果时样品与复检单不匹配
2. 非原始报告 - 基于非原始类型报告申请复检
3. 报告与样品不匹配 - 报告不属于指定样品
4. 原始报告停用后重复申请
5. 未完成检测 - 必检项目缺失时不能完成复检
6. 重复确认 - 已确认的复检不能再次确认
7. 差异确认后批次状态与风险等级验证
8. 最终判定值校验
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from app.database import Base, get_db
from app.config import settings

TEST_DB_PATH = settings.BASE_DIR / "data" / "test_reinspection_edge.db"

if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()

TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH}"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


PASS_COUNT = 0
FAIL_COUNT = 0
FAIL_DETAILS = []
ctx = {}


def test_case(name, func):
    global PASS_COUNT, FAIL_COUNT
    try:
        result = func()
        if result is not False:
            PASS_COUNT += 1
            print(f"  ✓ PASS {name}")
            return True
        else:
            FAIL_COUNT += 1
            FAIL_DETAILS.append(name)
            print(f"  ✗ FAIL {name}")
            return False
    except Exception as e:
        FAIL_COUNT += 1
        FAIL_DETAILS.append(f"{name}: {str(e)}")
        print(f"  ✗ FAIL {name} - 异常: {str(e)[:200]}")
        import traceback
        traceback.print_exc()
        return False


def print_header(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60 + "\n")


print_header("复检流程边界条件与状态关联测试")


# ============================================================
# 基础数据准备
# ============================================================
print_header("[准备] 基础数据准备")


def setup_test_items():
    items = [
        {"item_code": "RI-PH-001", "item_name": "pH值", "lower_limit": 6.5, "upper_limit": 7.5, "unit": "pH", "is_mandatory": True},
        {"item_code": "RI-WT-001", "item_name": "水分", "lower_limit": 0, "upper_limit": 13.0, "unit": "%", "is_mandatory": True},
        {"item_code": "RI-AS-001", "item_name": "灰分", "lower_limit": 0, "upper_limit": 1.5, "unit": "%", "is_mandatory": True},
    ]
    ids = []
    for it in items:
        r = client.post("/api/v1/tests/items", json=it)
        assert r.status_code == 200, f"创建检测项失败: {r.text}"
        ids.append(r.json()["id"])
    ctx["item_ids"] = ids
    return True


def setup_batch_and_sample(batch_no, product_name="复检边界测试产品"):
    br = client.post("/api/v1/batches", json={
        "batch_no": batch_no,
        "product_name": product_name,
        "production_date": "2025-06-01T10:00:00",
        "quantity": 500,
        "production_line": "L1",
    })
    assert br.status_code == 200, f"创建批次失败: {br.text}"
    batch_id = br.json()["id"]

    sr = client.post("/api/v1/samples", json={
        "batch_id": batch_id,
        "sampling_person": "测试员",
    })
    assert sr.status_code == 200, f"创建样品失败: {sr.text}"
    sample_id = sr.json()["id"]

    return batch_id, sample_id


def submit_results(sample_id, values, tester="检测员"):
    for i, (item_id, val) in enumerate(zip(ctx["item_ids"], values)):
        r = client.post("/api/v1/tests/results", json={
            "sample_id": sample_id,
            "test_item_id": item_id,
            "test_value": str(val),
            "numeric_value": val,
            "tester": f"{tester}{i+1}",
        })
        assert r.status_code == 200, f"录入结果失败: {r.text}"


def submit_reinspection_results(ri_id, re_sample_id, values, tester="复检员"):
    for i, (item_id, val) in enumerate(zip(ctx["item_ids"], values)):
        r = client.post(f"/api/v1/reinspections/{ri_id}/test-results", json={
            "sample_id": re_sample_id,
            "test_item_id": item_id,
            "test_value": str(val),
            "numeric_value": val,
            "tester": f"{tester}{i+1}",
        })
        assert r.status_code == 200, f"录入复检结果失败: {r.text}"


def create_original_report(sample_id, issued_by="审核员"):
    r = client.post(f"/api/v1/reports/original/{sample_id}?issued_by={issued_by}")
    assert r.status_code == 200, f"创建原始报告失败: {r.text}"
    return r.json()["id"]


def apply_reinspection(sample_id, report_id, reason="测试复检", applicant="申请人"):
    return client.post("/api/v1/reinspections", json={
        "original_sample_id": sample_id,
        "original_report_id": report_id,
        "reason": reason,
        "applicant": applicant,
    })


test_case("创建必检项", setup_test_items)


# ============================================================
# 测试1: 非原始报告申请复检
# ============================================================
print_header("[测试1] 非原始报告类型不能申请复检")


def t1_non_original_report():
    batch_id, sample_id = setup_batch_and_sample("BATCH-RI-001")
    submit_results(sample_id, [6.0, 14.0, 2.0])
    report_id = create_original_report(sample_id)

    ri_resp = apply_reinspection(sample_id, report_id)
    assert ri_resp.status_code == 200, f"首次复检申请应成功: {ri_resp.text}"
    ri_data = ri_resp.json()
    re_sample_id = ri_data["re_sample_id"]
    ri_id = ri_data["id"]

    submit_reinspection_results(ri_id, re_sample_id, [7.0, 10.0, 0.8], "复检员")
    client.post(f"/api/v1/reinspections/{ri_id}/complete-testing")
    client.post(f"/api/v1/reinspections/{ri_id}/confirm-difference", json={
        "difference_identified": True,
        "difference_remark": "操作误差",
        "confirmed_by": "质量主管",
        "final_judgment": "pass",
    })

    final_resp = client.post(f"/api/v1/reports/final/{batch_id}?issued_by=质量总监")
    assert final_resp.status_code == 200, f"生成最终报告失败: {final_resp.text}"
    final_report_id = final_resp.json()["id"]

    resp = apply_reinspection(sample_id, final_report_id)
    assert resp.status_code == 400, f"基于最终报告申请应返回400，实际: {resp.status_code}"
    detail = resp.json()["detail"]
    assert "原始报告" in detail, f"错误信息应提示只能基于原始报告，实际: {detail}"

    return True


test_case("1.1 基于复检报告(reinspection类型)申请复检应被拒绝", t1_non_original_report)


# ============================================================
# 测试2: 报告与样品不匹配
# ============================================================
print_header("[测试2] 报告与样品不匹配时不能申请复检")


def t2_report_sample_mismatch():
    batch_id_1, sample_id_1 = setup_batch_and_sample("BATCH-RI-002A")
    submit_results(sample_id_1, [7.0, 10.0, 0.8])
    report_id_1 = create_original_report(sample_id_1)

    batch_id_2, sample_id_2 = setup_batch_and_sample("BATCH-RI-002B")
    submit_results(sample_id_2, [6.0, 14.0, 2.0])
    create_original_report(sample_id_2)

    resp = client.post("/api/v1/reinspections", json={
        "original_sample_id": sample_id_2,
        "original_report_id": report_id_1,
        "reason": "测试报告样品不匹配",
        "applicant": "测试员",
    })
    assert resp.status_code == 400, f"报告与样品不匹配应返回400，实际: {resp.status_code}"
    assert "不匹配" in resp.json()["detail"], f"错误信息应包含'不匹配'，实际: {resp.json()['detail']}"

    return True


test_case("2.1 报告不属于指定样品时应被拒绝", t2_report_sample_mismatch)


# ============================================================
# 测试3: 原始报告停用后不能再次申请
# ============================================================
print_header("[测试3] 原始报告停用后不能重复申请复检")


def t3_deactivated_report():
    batch_id, sample_id = setup_batch_and_sample("BATCH-RI-003")
    submit_results(sample_id, [6.0, 14.0, 2.0])
    report_id = create_original_report(sample_id)

    ri_resp = apply_reinspection(sample_id, report_id, reason="第一次复检")
    assert ri_resp.status_code == 200, f"首次复检应成功: {ri_resp.text}"

    report_resp = client.get(f"/api/v1/reports/{report_id}")
    assert report_resp.json()["is_active"] == False, "首次复检后原始报告应被停用"

    resp2 = apply_reinspection(sample_id, report_id, reason="重复申请复检")
    assert resp2.status_code == 400, f"停用报告再次申请应返回400，实际: {resp2.status_code}"
    detail = resp2.json()["detail"]
    assert "停用" in detail or "已存在复检" in detail, f"应提示停用或重复申请，实际: {detail}"

    return True


test_case("3.1 原始报告停用后再次申请复检应被拒绝", t3_deactivated_report)


# ============================================================
# 测试4: 错样品 - 录入复检结果时样品不匹配
# ============================================================
print_header("[测试4] 录入复检结果时样品与复检单不匹配")


def t4_wrong_sample():
    batch_id, sample_id = setup_batch_and_sample("BATCH-RI-004")
    submit_results(sample_id, [6.0, 14.0, 2.0])
    report_id = create_original_report(sample_id)

    ri_resp = apply_reinspection(sample_id, report_id)
    assert ri_resp.status_code == 200
    ri_id = ri_resp.json()["id"]
    correct_re_sample_id = ri_resp.json()["re_sample_id"]

    other_batch_id, other_sample_id = setup_batch_and_sample("BATCH-RI-004-OTHER")

    resp = client.post(f"/api/v1/reinspections/{ri_id}/test-results", json={
        "sample_id": other_sample_id,
        "test_item_id": ctx["item_ids"][0],
        "test_value": "7.0",
        "numeric_value": 7.0,
        "tester": "检测员",
    })
    assert resp.status_code == 400, f"错样品录入应返回400，实际: {resp.status_code}"
    assert "不匹配" in resp.json()["detail"], f"应提示样品不匹配，实际: {resp.json()['detail']}"

    resp_ok = client.post(f"/api/v1/reinspections/{ri_id}/test-results", json={
        "sample_id": correct_re_sample_id,
        "test_item_id": ctx["item_ids"][0],
        "test_value": "7.0",
        "numeric_value": 7.0,
        "tester": "检测员",
    })
    assert resp_ok.status_code == 200, f"正确样品录入应成功: {resp_ok.text}"

    return True


test_case("4.1 使用非复检样品录入结果应被拒绝", t4_wrong_sample)


# ============================================================
# 测试5: 未完成检测不能进入完成状态
# ============================================================
print_header("[测试5] 必检项目未全部完成时不能完成复检")


def t5_incomplete_testing():
    batch_id, sample_id = setup_batch_and_sample("BATCH-RI-005")
    submit_results(sample_id, [6.0, 14.0, 2.0])
    report_id = create_original_report(sample_id)

    ri_resp = apply_reinspection(sample_id, report_id)
    assert ri_resp.status_code == 200
    ri_id = ri_resp.json()["id"]
    re_sample_id = ri_resp.json()["re_sample_id"]

    client.post(f"/api/v1/reinspections/{ri_id}/test-results", json={
        "sample_id": re_sample_id,
        "test_item_id": ctx["item_ids"][0],
        "test_value": "7.0",
        "numeric_value": 7.0,
        "tester": "检测员",
    })

    resp = client.post(f"/api/v1/reinspections/{ri_id}/complete-testing")
    assert resp.status_code == 400, f"缺少必检项应返回400，实际: {resp.status_code}"
    assert "检测项目" in resp.json()["detail"] or "未完成" in resp.json()["detail"], \
        f"应提示检测项缺失，实际: {resp.json()['detail']}"

    ri_check = client.get(f"/api/v1/reinspections/{ri_id}")
    assert ri_check.json()["status"] == "testing", "复检状态应仍为testing"

    for item_id in ctx["item_ids"][1:]:
        client.post(f"/api/v1/reinspections/{ri_id}/test-results", json={
            "sample_id": re_sample_id,
            "test_item_id": item_id,
            "test_value": "10.0",
            "numeric_value": 10.0,
            "tester": "检测员",
        })

    resp_ok = client.post(f"/api/v1/reinspections/{ri_id}/complete-testing")
    assert resp_ok.status_code == 200, f"全部项目完成后应成功: {resp_ok.text}"
    assert resp_ok.json()["status"] == "completed"

    return True


test_case("5.1 缺少必检项时完成复检应被拒绝", t5_incomplete_testing)


# ============================================================
# 测试6: 重复确认
# ============================================================
print_header("[测试6] 已确认的复检不能重复确认")


def t6_duplicate_confirm():
    batch_id, sample_id = setup_batch_and_sample("BATCH-RI-006")
    submit_results(sample_id, [6.0, 14.0, 2.0])
    report_id = create_original_report(sample_id)

    ri_resp = apply_reinspection(sample_id, report_id)
    ri_id = ri_resp.json()["id"]
    re_sample_id = ri_resp.json()["re_sample_id"]

    for item_id in ctx["item_ids"]:
        client.post(f"/api/v1/reinspections/{ri_id}/test-results", json={
            "sample_id": re_sample_id,
            "test_item_id": item_id,
            "test_value": "7.0",
            "numeric_value": 7.0,
            "tester": "检测员",
        })
    client.post(f"/api/v1/reinspections/{ri_id}/complete-testing")

    confirm_data = {
        "difference_identified": True,
        "difference_remark": "操作误差",
        "confirmed_by": "质量主管",
        "final_judgment": "pass",
    }
    resp1 = client.post(f"/api/v1/reinspections/{ri_id}/confirm-difference", json=confirm_data)
    assert resp1.status_code == 200, f"首次确认应成功: {resp1.text}"
    assert resp1.json()["status"] == "confirmed"

    resp2 = client.post(f"/api/v1/reinspections/{ri_id}/confirm-difference", json=confirm_data)
    assert resp2.status_code == 400, f"重复确认应返回400，实际: {resp2.status_code}"
    assert "状态无效" in resp2.json()["detail"], f"应提示状态无效，实际: {resp2.json()['detail']}"

    return True


test_case("6.1 已确认复检再次确认应被拒绝", t6_duplicate_confirm)


# ============================================================
# 测试7: 差异确认后批次状态与风险等级
# ============================================================
print_header("[测试7] 差异确认后批次状态/最终判定/风险等级验证")


def t7_batch_status_after_confirm_pass():
    batch_id, sample_id = setup_batch_and_sample("BATCH-RI-007A")
    submit_results(sample_id, [6.0, 14.0, 2.0])
    report_id = create_original_report(sample_id)

    ri_resp = apply_reinspection(sample_id, report_id)
    ri_id = ri_resp.json()["id"]
    re_sample_id = ri_resp.json()["re_sample_id"]

    for item_id in ctx["item_ids"]:
        client.post(f"/api/v1/reinspections/{ri_id}/test-results", json={
            "sample_id": re_sample_id,
            "test_item_id": item_id,
            "test_value": "7.0",
            "numeric_value": 7.0,
            "tester": "复检员",
        })
    client.post(f"/api/v1/reinspections/{ri_id}/complete-testing")

    client.post(f"/api/v1/reinspections/{ri_id}/confirm-difference", json={
        "difference_identified": True,
        "difference_remark": "首次检测误差",
        "confirmed_by": "质量主管",
        "final_judgment": "pass",
    })

    batch = client.get(f"/api/v1/batches/{batch_id}").json()
    assert batch["final_result"] == "pass", f"最终判定应为pass，实际: {batch['final_result']}"
    assert batch["status"] == "completed", f"批次状态应为completed，实际: {batch['status']}"
    assert batch["risk_score"] is not None, "风险评分应已计算"
    assert batch["risk_level"] in ("low", "medium", "high"), "风险等级应有效"

    return True


def t7_batch_status_after_confirm_fail():
    batch_id, sample_id = setup_batch_and_sample("BATCH-RI-007B")
    submit_results(sample_id, [7.0, 10.0, 0.8])
    report_id = create_original_report(sample_id)

    ri_resp = apply_reinspection(sample_id, report_id)
    ri_id = ri_resp.json()["id"]
    re_sample_id = ri_resp.json()["re_sample_id"]

    for item_id in ctx["item_ids"]:
        client.post(f"/api/v1/reinspections/{ri_id}/test-results", json={
            "sample_id": re_sample_id,
            "test_item_id": item_id,
            "test_value": "5.0",
            "numeric_value": 5.0,
            "tester": "复检员",
        })
    client.post(f"/api/v1/reinspections/{ri_id}/complete-testing")

    client.post(f"/api/v1/reinspections/{ri_id}/confirm-difference", json={
        "difference_identified": True,
        "difference_remark": "复检仍不合格",
        "confirmed_by": "质量主管",
        "final_judgment": "fail",
    })

    batch = client.get(f"/api/v1/batches/{batch_id}").json()
    assert batch["final_result"] == "fail", f"最终判定应为fail，实际: {batch['final_result']}"
    assert batch["status"] == "rejected", f"批次状态应为rejected，实际: {batch['status']}"
    assert batch["risk_score"] > 0, "不合格批次风险评分应大于0"

    return True


test_case("7.1 复检合格确认后批次=completed,final_result=pass,风险已计算", t7_batch_status_after_confirm_pass)
test_case("7.2 复检不合格确认后批次=rejected,final_result=fail,风险已计算", t7_batch_status_after_confirm_fail)


# ============================================================
# 测试8: 最终判定值校验
# ============================================================
print_header("[测试8] 最终判定值必须为pass或fail")


def t8_invalid_judgment():
    batch_id, sample_id = setup_batch_and_sample("BATCH-RI-008")
    submit_results(sample_id, [6.0, 14.0, 2.0])
    report_id = create_original_report(sample_id)

    ri_resp = apply_reinspection(sample_id, report_id)
    ri_id = ri_resp.json()["id"]
    re_sample_id = ri_resp.json()["re_sample_id"]

    for item_id in ctx["item_ids"]:
        client.post(f"/api/v1/reinspections/{ri_id}/test-results", json={
            "sample_id": re_sample_id,
            "test_item_id": item_id,
            "test_value": "7.0",
            "numeric_value": 7.0,
            "tester": "检测员",
        })
    client.post(f"/api/v1/reinspections/{ri_id}/complete-testing")

    resp = client.post(f"/api/v1/reinspections/{ri_id}/confirm-difference", json={
        "difference_identified": False,
        "confirmed_by": "质量主管",
        "final_judgment": "pending",
    })
    assert resp.status_code == 400, f"无效判定值应返回400，实际: {resp.status_code}"

    return True


test_case("8.1 final_judgment=pending应被拒绝", t8_invalid_judgment)


# ============================================================
# 测试9: 未完成检测状态下不能直接确认
# ============================================================
print_header("[测试9] 非completed状态不能确认差异")


def t9_confirm_before_testing():
    batch_id, sample_id = setup_batch_and_sample("BATCH-RI-009")
    submit_results(sample_id, [6.0, 14.0, 2.0])
    report_id = create_original_report(sample_id)

    ri_resp = apply_reinspection(sample_id, report_id)
    ri_id = ri_resp.json()["id"]

    resp = client.post(f"/api/v1/reinspections/{ri_id}/confirm-difference", json={
        "difference_identified": False,
        "confirmed_by": "质量主管",
        "final_judgment": "pass",
    })
    assert resp.status_code == 400, f"pending状态确认应返回400，实际: {resp.status_code}"
    assert "状态无效" in resp.json()["detail"]

    return True


test_case("9.1 pending状态直接确认差异应被拒绝", t9_confirm_before_testing)


# ============================================================
# 汇总
# ============================================================
total = PASS_COUNT + FAIL_COUNT
rate = (PASS_COUNT / total * 100) if total > 0 else 0

print_header("测试结果汇总")
print(f"  总计: {total} 项测试")
print(f"  通过: {PASS_COUNT} 项")
print(f"  失败: {FAIL_COUNT} 项")
print(f"  通过率: {rate:.1f}%\n")

if FAIL_DETAILS:
    print("失败项详情:")
    for f in FAIL_DETAILS:
        print(f"  ✗ {f}")
    print()

if FAIL_COUNT == 0:
    print("✅ 所有复检边界测试全部通过！")
    sys.exit(0)
else:
    print(f"❌ 有 {FAIL_COUNT} 项测试未通过！")
    sys.exit(1)
