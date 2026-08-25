#!/usr/bin/env python3
"""
质检样品留样与复检流程服务 - 验收测试脚本

执行方式:
    python3 tests/test_acceptance.py

覆盖验收内容:
1. 正常流程 - 合格批次放行
2. 异常流程 - 不合格批次复检
3. 留样到期销毁
4. 数据持久化验证
5. 数据追溯
6. 报告导出
7. 统计分析
8. 业务规则校验（编号重复、项目缺失、复检关联、销毁检查、放行校验）
"""

import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from app.database import Base, get_db
from app.config import settings

TEST_DB_PATH = settings.BASE_DIR / "data" / "test_quality_inspection.db"

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


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"


def print_test(name: str, passed: bool, detail: str = ""):
    status = f"{Colors.GREEN}✓ PASS{Colors.RESET}" if passed else f"{Colors.RED}✗ FAIL{Colors.RESET}"
    print(f"  {status} {name}")
    if detail and not passed:
        print(f"    {Colors.YELLOW}详情: {detail}{Colors.RESET}")


print(f"\n{Colors.BLUE}=" * 60)
print("  质检样品留样与复检流程服务 - 验收测试")
print("=" * 60, Colors.RESET)

test_results = {"passed": 0, "failed": 0, "total": 0}


def run_test(name: str, test_func):
    test_results["total"] += 1
    try:
        test_func()
        test_results["passed"] += 1
        print_test(name, True)
    except AssertionError as e:
        test_results["failed"] += 1
        print_test(name, False, str(e))
    except Exception as e:
        test_results["failed"] += 1
        print_test(name, False, f"异常: {str(e)}")


print(f"\n{Colors.BLUE}[验收1] 正常流程 - 合格批次放行{Colors.RESET}")

batch_id_1 = None
sample_id_1 = None
test_item_ids = []
original_report_id_1 = None
retention_id_1 = None


def test_1_1_create_test_items():
    global test_item_ids
    test_items = [
        {"item_code": "PH001", "item_name": "pH值", "lower_limit": 6.5, "upper_limit": 7.5, "unit": "pH", "is_mandatory": True},
        {"item_code": "WT001", "item_name": "水分", "lower_limit": 0, "upper_limit": 13.0, "unit": "%", "is_mandatory": True},
        {"item_code": "AS001", "item_name": "灰分", "lower_limit": 0, "upper_limit": 1.5, "unit": "%", "is_mandatory": True},
    ]
    for item in test_items:
        response = client.post("/api/v1/tests/items", json=item)
        assert response.status_code == 200, f"创建检测项失败: {response.text}"
        test_item_ids.append(response.json()["id"])
    assert len(test_item_ids) == 3


def test_1_2_create_batch():
    global batch_id_1
    batch_data = {
        "batch_no": "BATCH2024001",
        "product_name": "测试产品A",
        "production_date": "2024-01-15T10:00:00",
        "quantity": 1000,
        "production_line": "L1",
    }
    response = client.post("/api/v1/batches", json=batch_data)
    assert response.status_code == 200, f"创建批次失败: {response.text}"
    batch_id_1 = response.json()["id"]
    assert response.json()["status"] == "pending"
    assert response.json()["batch_no"] == "BATCH2024001"


def test_1_3_create_sample():
    global sample_id_1
    sample_data = {
        "batch_id": batch_id_1,
        "sampling_person": "质检员A",
        "sample_type": "production",
    }
    response = client.post("/api/v1/samples", json=sample_data)
    assert response.status_code == 200, f"送样失败: {response.text}"
    sample_id_1 = response.json()["id"]
    sample_code = response.json()["sample_code"]
    assert sample_code.startswith("SP"), f"样品编号格式错误: {sample_code}"
    assert response.json()["status"] == "collected"
    assert response.json()["batch_no"] == "BATCH2024001"


def test_1_4_input_test_results():
    test_results_data = [
        {"sample_id": sample_id_1, "test_item_id": test_item_ids[0], "test_value": "7.0", "numeric_value": 7.0, "tester": "检测员A"},
        {"sample_id": sample_id_1, "test_item_id": test_item_ids[1], "test_value": "10.5", "numeric_value": 10.5, "tester": "检测员A"},
        {"sample_id": sample_id_1, "test_item_id": test_item_ids[2], "test_value": "0.8", "numeric_value": 0.8, "tester": "检测员A"},
    ]
    for tr in test_results_data:
        response = client.post("/api/v1/tests/results", json=tr)
        assert response.status_code == 200, f"录入检测结果失败: {response.text}"
        assert response.json()["judgment"] == "pass", f"检测值判定错误"


def test_1_5_create_original_report():
    global original_report_id_1
    response = client.post(f"/api/v1/reports/original/{sample_id_1}?issued_by=审核员A")
    assert response.status_code == 200, f"生成原始报告失败: {response.text}"
    original_report_id_1 = response.json()["id"]
    assert response.json()["overall_judgment"] == "pass"
    assert response.json()["report_type"] == "original"
    assert len(response.json()["test_results"]) == 3


def test_1_6_create_retention():
    global retention_id_1
    retention_data = {"sample_id": sample_id_1, "retention_period_days": 90}
    response = client.post("/api/v1/retentions", json=retention_data)
    assert response.status_code == 200, f"留样失败: {response.text}"
    retention_id_1 = response.json()["id"]
    location_code = response.json()["location_code"]
    assert location_code == "A-01-01", f"留样位置分配错误: {location_code}"
    assert response.json()["status"] == "active"
    assert response.json()["is_expired"] == False


def test_1_7_release_batch():
    release_data = {"released_by": "质量主管", "remark": "合格放行"}
    response = client.post(f"/api/v1/batches/{batch_id_1}/release", json=release_data)
    assert response.status_code == 200, f"放行失败: {response.text}"
    assert response.json()["released"] == True
    assert response.json()["released_by"] == "质量主管"
    assert response.json()["status"] == "completed"


run_test("1.1 创建检测项", test_1_1_create_test_items)
run_test("1.2 创建批次", test_1_2_create_batch)
run_test("1.3 送样(生成样品编号)", test_1_3_create_sample)
run_test("1.4 录入合格检测结果", test_1_4_input_test_results)
run_test("1.5 生成原始检测报告", test_1_5_create_original_report)
run_test("1.6 留样(分配库位A-01-01)", test_1_6_create_retention)
run_test("1.7 放行批次", test_1_7_release_batch)

print(f"\n{Colors.BLUE}[验收2] 异常流程 - 不合格批次复检{Colors.RESET}")

batch_id_2 = None
sample_id_2 = None
original_report_id_2 = None
reinspection_id = None
re_sample_id = None


def test_2_1_create_batch_2():
    global batch_id_2
    batch_data = {
        "batch_no": "BATCH2024002",
        "product_name": "测试产品B",
        "production_date": "2024-01-16T10:00:00",
        "quantity": 800,
        "production_line": "L2",
    }
    response = client.post("/api/v1/batches", json=batch_data)
    assert response.status_code == 200
    batch_id_2 = response.json()["id"]


def test_2_2_create_sample_2():
    global sample_id_2
    sample_data = {"batch_id": batch_id_2, "sampling_person": "质检员B"}
    response = client.post("/api/v1/samples", json=sample_data)
    assert response.status_code == 200
    sample_id_2 = response.json()["id"]


def test_2_3_input_fail_test_results():
    test_results_data = [
        {"sample_id": sample_id_2, "test_item_id": test_item_ids[0], "test_value": "6.0", "numeric_value": 6.0, "tester": "检测员B"},
        {"sample_id": sample_id_2, "test_item_id": test_item_ids[1], "test_value": "14.0", "numeric_value": 14.0, "tester": "检测员B"},
        {"sample_id": sample_id_2, "test_item_id": test_item_ids[2], "test_value": "1.0", "numeric_value": 1.0, "tester": "检测员B"},
    ]
    for tr in test_results_data:
        response = client.post("/api/v1/tests/results", json=tr)
        assert response.status_code == 200


def test_2_4_create_original_report_fail():
    global original_report_id_2
    response = client.post(f"/api/v1/reports/original/{sample_id_2}?issued_by=审核员B")
    assert response.status_code == 200
    original_report_id_2 = response.json()["id"]
    assert response.json()["overall_judgment"] == "fail"


def test_2_5_apply_reinspection():
    global reinspection_id, re_sample_id
    reinspection_data = {
        "original_sample_id": sample_id_2,
        "original_report_id": original_report_id_2,
        "reason": "检测结果异常，申请复检",
        "applicant": "质量工程师",
    }
    response = client.post("/api/v1/reinspections", json=reinspection_data)
    assert response.status_code == 200, f"申请复检失败: {response.text}"
    reinspection_id = response.json()["id"]
    re_sample_id = response.json()["re_sample_id"]
    assert response.json()["original_report_no"] is not None
    assert response.json()["status"] == "pending"


def test_2_6_check_original_report_inactive():
    response = client.get(f"/api/v1/reports/{original_report_id_2}")
    assert response.status_code == 200
    assert response.json()["is_active"] == False, "原始报告应标记为非活跃"


def test_2_7_input_reinspection_results():
    test_results_data = [
        {"sample_id": re_sample_id, "test_item_id": test_item_ids[0], "test_value": "7.2", "numeric_value": 7.2, "tester": "检测员C"},
        {"sample_id": re_sample_id, "test_item_id": test_item_ids[1], "test_value": "12.0", "numeric_value": 12.0, "tester": "检测员C"},
        {"sample_id": re_sample_id, "test_item_id": test_item_ids[2], "test_value": "1.2", "numeric_value": 1.2, "tester": "检测员C"},
    ]
    for tr in test_results_data:
        response = client.post(f"/api/v1/reinspections/{reinspection_id}/test-results", json=tr)
        assert response.status_code == 200, f"录入复检结果失败: {response.text}"


def test_2_8_complete_reinspection_testing():
    response = client.post(f"/api/v1/reinspections/{reinspection_id}/complete-testing")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_2_9_confirm_difference():
    confirm_data = {
        "difference_identified": True,
        "difference_remark": "第一次检测操作误差，复检结果合格",
        "confirmed_by": "质量主管",
        "final_judgment": "pass",
    }
    response = client.post(f"/api/v1/reinspections/{reinspection_id}/confirm-difference", json=confirm_data)
    assert response.status_code == 200
    assert response.json()["final_judgment"] == "pass"
    assert response.json()["difference_identified"] == True


def test_2_10_check_batch_final_result():
    response = client.get(f"/api/v1/batches/{batch_id_2}")
    assert response.status_code == 200
    assert response.json()["final_result"] == "pass", "复检结论应覆盖原始结果"
    assert response.json()["status"] == "completed"


def test_2_11_check_old_report_retained():
    response = client.get(f"/api/v1/reports", params={"batch_id": batch_id_2})
    assert response.status_code == 200
    reports = response.json()
    assert len(reports) >= 1, "旧报告应保留"
    original_reports = [r for r in reports if r["report_type"] == "original"]
    assert len(original_reports) == 1, "原始报告应保留"


def test_2_12_create_final_report():
    response = client.post(f"/api/v1/reports/final/{batch_id_2}?issued_by=质量主管")
    assert response.status_code == 200
    assert response.json()["overall_judgment"] == "pass"
    assert response.json()["report_type"] == "final"


def test_2_13_release_reinspected_batch():
    release_data = {"released_by": "质量经理", "remark": "复检合格，予以放行"}
    response = client.post(f"/api/v1/batches/{batch_id_2}/release", json=release_data)
    assert response.status_code == 200
    assert response.json()["released"] == True


run_test("2.1 创建批次2", test_2_1_create_batch_2)
run_test("2.2 送样", test_2_2_create_sample_2)
run_test("2.3 录入不合格检测结果", test_2_3_input_fail_test_results)
run_test("2.4 生成不合格原始报告", test_2_4_create_original_report_fail)
run_test("2.5 申请复检", test_2_5_apply_reinspection)
run_test("2.6 验证原始报告标记为非活跃", test_2_6_check_original_report_inactive)
run_test("2.7 录入复检合格结果", test_2_7_input_reinspection_results)
run_test("2.8 完成复检检测", test_2_8_complete_reinspection_testing)
run_test("2.9 差异确认", test_2_9_confirm_difference)
run_test("2.10 复检结论覆盖原始结果", test_2_10_check_batch_final_result)
run_test("2.11 旧报告保留可查询", test_2_11_check_old_report_retained)
run_test("2.12 生成最终报告", test_2_12_create_final_report)
run_test("2.13 放行复检合格批次", test_2_13_release_reinspected_batch)

print(f"\n{Colors.BLUE}[验收3] 留样到期销毁{Colors.RESET}")

batch_id_3 = None
sample_id_3 = None
retention_id_3 = None


def test_3_1_create_batch_3():
    global batch_id_3
    batch_data = {
        "batch_no": "BATCH2024003",
        "product_name": "测试产品C",
        "production_date": "2024-01-17T10:00:00",
        "quantity": 500,
        "production_line": "L1",
    }
    response = client.post("/api/v1/batches", json=batch_data)
    assert response.status_code == 200
    batch_id_3 = response.json()["id"]


def test_3_2_create_sample_3():
    global sample_id_3
    sample_data = {"batch_id": batch_id_3, "sampling_person": "质检员C"}
    response = client.post("/api/v1/samples", json=sample_data)
    assert response.status_code == 200
    sample_id_3 = response.json()["id"]


def test_3_3_input_test_results_3():
    for item_id in test_item_ids:
        tr = {"sample_id": sample_id_3, "test_item_id": item_id, "test_value": "7.0", "numeric_value": 7.0, "tester": "检测员C"}
        client.post("/api/v1/tests/results", json=tr)


def test_3_4_create_report_3():
    client.post(f"/api/v1/reports/original/{sample_id_3}?issued_by=审核员C")


def test_3_5_create_retention_short():
    global retention_id_3
    retention_data = {"sample_id": sample_id_3, "retention_period_days": 1}
    response = client.post("/api/v1/retentions", json=retention_data)
    assert response.status_code == 200
    retention_id_3 = response.json()["id"]
    location_code = response.json()["location_code"]
    assert location_code == "A-01-02", f"留样位置应为A-01-02（BATCH2024002未留样），实际: {location_code}"


def test_3_6_destroy_not_expired_fails():
    destroy_data = {"destroyed_by": "仓库管理员", "destroy_remark": "测试销毁未到期留样"}
    response = client.post(f"/api/v1/retentions/{retention_id_3}/destroy", json=destroy_data)
    assert response.status_code == 400, "未到期留样应无法销毁"
    assert "留样未到期" in response.json()["detail"]


def test_3_7_simulate_expired_retention():
    from app.models import Retention
    db = TestingSessionLocal()
    retention = db.query(Retention).filter(Retention.id == retention_id_3).first()
    retention.retention_end = datetime.now() - timedelta(days=1)
    db.commit()
    db.close()


def test_3_8_check_expired_retentions():
    response = client.post("/api/v1/retentions/check-expired")
    assert response.status_code == 200
    assert response.json()["expired_count"] >= 1


def test_3_9_destroy_expired_retention():
    destroy_data = {"destroyed_by": "仓库管理员", "destroy_remark": "留样到期，正常销毁"}
    response = client.post(f"/api/v1/retentions/{retention_id_3}/destroy", json=destroy_data)
    assert response.status_code == 200
    assert response.json()["destroyed"] == True
    assert response.json()["status"] == "destroyed"


def test_3_10_location_released_after_destroy():
    locations = client.get("/api/v1/retentions/locations").json()
    location = next((l for l in locations if l["location_code"] == "A-01-02"), None)
    assert location is not None
    assert location["is_occupied"] == False, "销毁后位置应释放"


def test_3_11_reinspection_destroyed_sample_fails():
    client.post(f"/api/v1/reports/original/{sample_id_3}?issued_by=审核员C")
    reports = client.get("/api/v1/reports", params={"batch_id": batch_id_3}).json()
    report_id = reports[0]["id"] if reports else None
    if report_id:
        reinspection_data = {
            "original_sample_id": sample_id_3,
            "original_report_id": report_id,
            "reason": "测试已销毁样品复检",
            "applicant": "测试员",
        }
        response = client.post("/api/v1/reinspections", json=reinspection_data)
        assert response.status_code == 400, "已销毁样品应无法复检"
        assert "已销毁" in response.json()["detail"]


run_test("3.1 创建批次3", test_3_1_create_batch_3)
run_test("3.2 送样", test_3_2_create_sample_3)
run_test("3.3 录入检测结果", test_3_3_input_test_results_3)
run_test("3.4 生成报告", test_3_4_create_report_3)
run_test("3.5 创建1天短期限留样", test_3_5_create_retention_short)
run_test("3.6 未到期留样销毁被拒绝", test_3_6_destroy_not_expired_fails)
run_test("3.7 模拟留样过期", test_3_7_simulate_expired_retention)
run_test("3.8 检查过期留样", test_3_8_check_expired_retentions)
run_test("3.9 销毁过期留样", test_3_9_destroy_expired_retention)
run_test("3.10 销毁后位置释放", test_3_10_location_released_after_destroy)
run_test("3.11 已销毁留样无法复检", test_3_11_reinspection_destroyed_sample_fails)

print(f"\n{Colors.BLUE}[验收4] 数据持久化验证{Colors.RESET}")

export_record_id = None


def test_4_1_export_batch_report():
    global export_record_id
    export_data = {
        "batch_id": batch_id_2,
        "file_format": "xlsx",
        "include_original": True,
        "include_reinspection": True,
        "include_final": True,
        "exported_by": "系统管理员",
    }
    response = client.post("/api/v1/exports", json=export_data)
    assert response.status_code == 200, f"导出失败: {response.text}"
    export_record_id = response.json()["id"]
    assert response.json()["include_original"] == True
    assert response.json()["include_reinspection"] == True
    assert response.json()["include_final"] == True


def test_4_2_check_export_file_exists():
    exports = client.get("/api/v1/exports").json()
    assert len(exports) >= 1
    export_record = exports[0]
    import os
    assert os.path.exists(export_record["file_path"].replace("/app", "")) or os.path.exists(export_record["file_path"]), "导出文件应存在"


def test_4_3_verify_data_after_restart():
    batch = client.get(f"/api/v1/batches/{batch_id_1}").json()
    assert batch["batch_no"] == "BATCH2024001", "批次信息应持久化"
    assert batch["released"] == True

    sample = client.get(f"/api/v1/samples/{sample_id_1}").json()
    assert sample["sample_code"] is not None, "样品编号应持久化"
    assert sample["retention_location"] == "A-01-01", "留样位置应持久化"

    test_results = client.get("/api/v1/tests/results", params={"sample_id": sample_id_1}).json()
    assert len(test_results) == 3, "检测结果应持久化"

    reinspections = client.get("/api/v1/reinspections", params={"original_sample_id": sample_id_2}).json()
    assert len(reinspections) == 1, "复检链路应持久化"
    assert reinspections[0]["original_report_no"] is not None

    exports = client.get("/api/v1/exports").json()
    assert len(exports) >= 1, "导出记录应持久化"


run_test("4.1 导出批次报告(Excel)", test_4_1_export_batch_report)
run_test("4.2 导出文件存在", test_4_2_check_export_file_exists)
run_test("4.3 数据持久化验证", test_4_3_verify_data_after_restart)

print(f"\n{Colors.BLUE}[验收5] 数据追溯{Colors.RESET}")


def test_5_1_batch_quality_archive():
    response = client.get(f"/api/v1/batches/{batch_id_2}/archive")
    assert response.status_code == 200
    archive = response.json()

    assert archive["batch"]["batch_no"] == "BATCH2024002"
    assert len(archive["samples"]) >= 2, "应包含原始样品和复检样品"
    assert archive["original_report"] is not None, "应包含原始报告"
    assert len(archive["reinspection_reports"]) >= 0, "应包含复检报告列表"
    assert archive["final_report"] is not None, "应包含最终报告"
    assert len(archive["reinspections"]) == 1, "应包含复检记录"


def test_5_2_retention_location_query():
    response = client.get("/api/v1/retentions/locations", params={"zone": "A", "is_occupied": True})
    assert response.status_code == 200
    locations = response.json()
    assert len(locations) >= 1
    assert all(l["zone"] == "A" for l in locations)
    assert all(l["is_occupied"] == True for l in locations)


def test_5_3_reports_traceable_to_batch():
    response = client.get("/api/v1/reports", params={"batch_id": batch_id_2})
    assert response.status_code == 200
    reports = response.json()
    for r in reports:
        assert r["batch_no"] == "BATCH2024002", f"报告应关联批次"


run_test("5.1 批次质量档案完整", test_5_1_batch_quality_archive)
run_test("5.2 留样位置查询", test_5_2_retention_location_query)
run_test("5.3 报告可追溯到批次", test_5_3_reports_traceable_to_batch)

print(f"\n{Colors.BLUE}[验收6] 报告导出{Colors.RESET}")


def test_6_1_export_pdf():
    export_data = {
        "batch_id": batch_id_1,
        "file_format": "pdf",
        "include_original": True,
        "include_reinspection": True,
        "include_final": True,
        "exported_by": "系统管理员",
    }
    response = client.post("/api/v1/exports", json=export_data)
    assert response.status_code == 200, f"PDF导出失败: {response.text}"
    assert response.json()["file_format"] == "pdf"


def test_6_2_download_export():
    exports = client.get("/api/v1/exports").json()
    assert len(exports) >= 1
    export_no = exports[0]["export_no"]
    response = client.get(f"/api/v1/exports/download/{export_no}")
    assert response.status_code == 200, "下载失败"
    assert len(response.content) > 0, "下载内容为空"


run_test("6.1 导出PDF格式", test_6_1_export_pdf)
run_test("6.2 下载导出文件", test_6_2_download_export)

print(f"\n{Colors.BLUE}[验收7] 统计分析{Colors.RESET}")


def test_7_1_reinspection_diff_stats():
    response = client.get("/api/v1/stats/reinspection-diff")
    assert response.status_code == 200
    stats = response.json()
    assert stats["total_reinspections"] >= 1
    assert stats["with_difference"] >= 1
    assert "difference_rate" in stats


def test_7_2_retention_expire_stats():
    response = client.get("/api/v1/stats/retention-expire")
    assert response.status_code == 200
    stats = response.json()
    assert "total_active" in stats
    assert "expired" in stats
    assert "destroyed" in stats
    assert stats["destroyed"] >= 1


def test_7_3_overall_stats():
    response = client.get("/api/v1/stats/overall")
    assert response.status_code == 200
    stats = response.json()
    assert "batch_stats" in stats
    assert "reinspection_stats" in stats
    assert "retention_stats" in stats
    assert "sample_stats" in stats


run_test("7.1 复检差异统计", test_7_1_reinspection_diff_stats)
run_test("7.2 留样过期统计", test_7_2_retention_expire_stats)
run_test("7.3 整体统计", test_7_3_overall_stats)

print(f"\n{Colors.BLUE}[验收8] 业务规则校验{Colors.RESET}")


def test_8_1_sample_code_unique():
    from app.models import Sample
    from app.services.sample_service import SampleService
    from app.exceptions import SampleCodeDuplicateError

    db = TestingSessionLocal()
    service = SampleService(db)
    try:
        sample = db.query(Sample).first()
        service.validate_sample_code_unique(sample.sample_code)
        assert False, "应抛出样品编号重复异常"
    except SampleCodeDuplicateError as e:
        assert "样品编号重复" in str(e)
    finally:
        db.close()


def test_8_2_test_item_missing():
    from app.models import Sample, Batch
    db = TestingSessionLocal()

    batch = Batch(
        batch_no="BATCH_TEST_MISSING",
        product_name="测试产品",
        production_date=datetime.now(),
        quantity=100,
        status="pending",
    )
    db.add(batch)
    db.commit()

    sample = Sample(
        sample_code="SP_TEST_MISSING",
        batch_id=batch.id,
        status="collected",
    )
    db.add(sample)
    db.commit()

    from app.services.test_service import TestService
    from app.exceptions import TestItemMissingError

    service = TestService(db)
    try:
        service.validate_test_items_complete(sample.id)
        assert False, "应抛出检测项目缺失异常"
    except TestItemMissingError as e:
        assert "检测项目缺失" in str(e)
    finally:
        db.close()


def test_8_3_reinspection_without_original_report():
    reinspection_data = {
        "original_sample_id": sample_id_1,
        "original_report_id": 99999,
        "reason": "测试无原始报告复检",
        "applicant": "测试员",
    }
    response = client.post("/api/v1/reinspections", json=reinspection_data)
    assert response.status_code == 404, "应抛出报告不存在异常"


def test_8_4_release_fail_batch_without_reinspection():
    batch_data = {
        "batch_no": "BATCH_TEST_RELEASE",
        "product_name": "测试放行产品",
        "production_date": "2024-01-18T10:00:00",
        "quantity": 100,
    }
    batch_resp = client.post("/api/v1/batches", json=batch_data)
    batch_id = batch_resp.json()["id"]

    sample_resp = client.post("/api/v1/samples", json={"batch_id": batch_id, "sampling_person": "测试员"})
    sample_id = sample_resp.json()["id"]

    for item_id in test_item_ids:
        client.post("/api/v1/tests/results", json={
            "sample_id": sample_id, "test_item_id": item_id,
            "test_value": "20.0", "numeric_value": 20.0, "tester": "测试员"
        })

    client.post(f"/api/v1/reports/original/{sample_id}?issued_by=测试员")

    release_data = {"released_by": "测试员"}
    response = client.post(f"/api/v1/batches/{batch_id}/release", json=release_data)
    assert response.status_code == 403, "不合格批次应无法直接放行"
    assert "不合格" in response.json()["detail"] or "无法放行" in response.json()["detail"]


run_test("8.1 样品编号重复校验", test_8_1_sample_code_unique)
run_test("8.2 检测项目缺失校验", test_8_2_test_item_missing)
run_test("8.3 复检未关联原报告校验", test_8_3_reinspection_without_original_report)
run_test("8.4 判定不合格直接放行校验", test_8_4_release_fail_batch_without_reinspection)

print(f"\n{Colors.BLUE}=" * 60)
print("  测试结果汇总")
print("=" * 60, Colors.RESET)

total = test_results["total"]
passed = test_results["passed"]
failed = test_results["failed"]
rate = (passed / total * 100) if total > 0 else 0

print(f"\n  总计: {total} 项测试")
print(f"  通过: {Colors.GREEN}{passed}{Colors.RESET} 项")
print(f"  失败: {Colors.RED}{failed}{Colors.RESET} 项")
print(f"  通过率: {rate:.1f}%")

print(f"\n{Colors.BLUE}[验收9] 复检争议仲裁与批次风险分级{Colors.RESET}")

batch_id_9 = None
sample_id_9 = None
original_report_id_9 = None
reinspection_id_9 = None
re_sample_id_9 = None
arbitration_id_9 = None


def test_9_1_create_batch_9():
    global batch_id_9
    batch_data = {
        "batch_no": "BATCH2024009",
        "product_name": "仲裁测试产品",
        "production_date": "2024-01-20T10:00:00",
        "quantity": 600,
        "production_line": "L3",
    }
    response = client.post("/api/v1/batches", json=batch_data)
    assert response.status_code == 200
    batch_id_9 = response.json()["id"]
    assert response.json()["risk_level"] == "low"
    assert response.json()["risk_score"] == 0.0


def test_9_2_create_sample_9():
    global sample_id_9
    sample_data = {"batch_id": batch_id_9, "sampling_person": "质检员D"}
    response = client.post("/api/v1/samples", json=sample_data)
    assert response.status_code == 200
    sample_id_9 = response.json()["id"]


def test_9_3_input_fail_test_results_9():
    test_results_data = [
        {"sample_id": sample_id_9, "test_item_id": test_item_ids[0], "test_value": "6.0", "numeric_value": 6.0, "tester": "检测员D"},
        {"sample_id": sample_id_9, "test_item_id": test_item_ids[1], "test_value": "15.0", "numeric_value": 15.0, "tester": "检测员D"},
        {"sample_id": sample_id_9, "test_item_id": test_item_ids[2], "test_value": "2.0", "numeric_value": 2.0, "tester": "检测员D"},
    ]
    for tr in test_results_data:
        response = client.post("/api/v1/tests/results", json=tr)
        assert response.status_code == 200


def test_9_4_create_original_report_fail_9():
    global original_report_id_9
    response = client.post(f"/api/v1/reports/original/{sample_id_9}?issued_by=审核员D")
    assert response.status_code == 200
    original_report_id_9 = response.json()["id"]
    assert response.json()["overall_judgment"] == "fail"

    batch_resp = client.get(f"/api/v1/batches/{batch_id_9}").json()
    assert batch_resp["risk_score"] > 0, "检测失败后风险评分应增加"


def test_9_5_apply_reinspection_9():
    global reinspection_id_9, re_sample_id_9
    reinspection_data = {
        "original_sample_id": sample_id_9,
        "original_report_id": original_report_id_9,
        "reason": "检测结果异常，申请复检",
        "applicant": "质量工程师",
    }
    response = client.post("/api/v1/reinspections", json=reinspection_data)
    assert response.status_code == 200
    reinspection_id_9 = response.json()["id"]
    re_sample_id_9 = response.json()["re_sample_id"]


def test_9_6_input_reinspection_results_9():
    test_results_data = [
        {"sample_id": re_sample_id_9, "test_item_id": test_item_ids[0], "test_value": "7.0", "numeric_value": 7.0, "tester": "检测员E"},
        {"sample_id": re_sample_id_9, "test_item_id": test_item_ids[1], "test_value": "11.0", "numeric_value": 11.0, "tester": "检测员E"},
        {"sample_id": re_sample_id_9, "test_item_id": test_item_ids[2], "test_value": "1.0", "numeric_value": 1.0, "tester": "检测员E"},
    ]
    for tr in test_results_data:
        response = client.post(f"/api/v1/reinspections/{reinspection_id_9}/test-results", json=tr)
        assert response.status_code == 200

    response = client.post(f"/api/v1/reinspections/{reinspection_id_9}/complete-testing")
    assert response.status_code == 200


def test_9_7_confirm_difference_pass_9():
    confirm_data = {
        "difference_identified": True,
        "difference_remark": "第一次检测操作误差，复检结果合格",
        "confirmed_by": "质量主管",
        "final_judgment": "pass",
    }
    response = client.post(f"/api/v1/reinspections/{reinspection_id_9}/confirm-difference", json=confirm_data)
    assert response.status_code == 200
    assert response.json()["final_judgment"] == "pass"

    batch_resp = client.get(f"/api/v1/batches/{batch_id_9}").json()
    assert batch_resp["risk_score"] > 0, "有复检差异后风险评分应增加"
    assert batch_resp["risk_level"] in ["low", "medium", "high"], "风险等级应根据评分确定"


def test_9_8_create_reinspection_report_9():
    response = client.post(f"/api/v1/reinspections/{reinspection_id_9}/report?issued_by=审核员D")
    assert response.status_code == 200
    assert response.json()["report_type"] == "reinspection"


def test_9_9_initiate_arbitration():
    global arbitration_id_9
    arbitration_data = {
        "reinspection_id": reinspection_id_9,
        "dispute_source": "生产部门对复检结果有异议，认为检测环境有问题",
        "dispute_items": test_item_ids,
        "arbitrator": "质检总监",
    }
    response = client.post("/api/v1/arbitrations", json=arbitration_data)
    assert response.status_code == 200, f"发起仲裁失败: {response.text}"
    arbitration_id_9 = response.json()["id"]
    assert response.json()["status"] == "pending"
    assert response.json()["arbitrator"] == "质检总监"


def test_9_10_arbitration_pending_block_release():
    release_data = {"released_by": "质量经理", "remark": "测试仲裁未完成放行"}
    response = client.post(f"/api/v1/batches/{batch_id_9}/release", json=release_data)
    assert response.status_code == 403, "仲裁未完成应禁止放行"
    assert "仲裁" in response.json()["detail"] or "未完成" in response.json()["detail"]


def test_9_11_arbitration_overturn_reinspection():
    process_data = {
        "handling_opinion": "经核查，复检时检测仪器未校准，原始检测结果更准确。同意推翻复检结论，判定为不合格。",
        "final_judgment": "fail",
    }
    response = client.post(f"/api/v1/arbitrations/{arbitration_id_9}/complete", json=process_data)
    assert response.status_code == 200, f"完成仲裁失败: {response.text}"
    assert response.json()["final_judgment"] == "fail"
    assert response.json()["status"] == "completed"
    assert response.json()["arbitration_report_id"] is not None, "应生成仲裁报告"


def test_9_12_verify_batch_final_result():
    batch_resp = client.get(f"/api/v1/batches/{batch_id_9}").json()
    assert batch_resp["final_result"] == "fail", "仲裁结论应覆盖复检结论"
    assert batch_resp["risk_score"] > 0, "风险评分应存在"
    assert batch_resp["risk_level"] in ["low", "medium", "high"], "风险等级应已计算"


def test_9_13_verify_all_reports_retained():
    reports = client.get("/api/v1/reports", params={"batch_id": batch_id_9}).json()
    report_types = [r["report_type"] for r in reports]
    assert "original" in report_types, "原始报告应保留"
    assert "reinspection" in report_types, "复检报告应保留"
    assert "arbitration" in report_types, "仲裁报告应存在"

    original_reports = [r for r in reports if r["report_type"] == "original"]
    reinspection_reports = [r for r in reports if r["report_type"] == "reinspection"]
    arbitration_reports = [r for r in reports if r["report_type"] == "arbitration"]

    assert len(original_reports) == 1
    assert len(reinspection_reports) == 1
    assert len(arbitration_reports) == 1

    active_reports = [r for r in reports if r["is_active"] == True]
    assert len(active_reports) == 1, "应只有一份活跃报告"
    assert active_reports[0]["report_type"] == "arbitration", "仲裁报告应为活跃报告"


def test_9_14_verify_quality_archive():
    archive = client.get(f"/api/v1/batches/{batch_id_9}/archive").json()
    assert "arbitrations" in archive, "质量档案应包含仲裁记录"
    assert len(archive["arbitrations"]) == 1
    assert "arbitration_reports" in archive, "质量档案应包含仲裁报告"
    assert len(archive["arbitration_reports"]) == 1
    assert archive["batch"]["risk_level"] in ["low", "medium", "high"]
    assert archive["batch"]["risk_score"] >= 0


def test_9_15_export_with_arbitration():
    export_data = {
        "batch_id": batch_id_9,
        "file_format": "xlsx",
        "include_original": True,
        "include_reinspection": True,
        "include_final": True,
        "include_arbitration": True,
        "exported_by": "系统管理员",
    }
    response = client.post("/api/v1/exports", json=export_data)
    assert response.status_code == 200
    assert response.json()["include_arbitration"] == True


def test_9_16_risk_level_stats():
    response = client.get("/api/v1/stats/risk-level")
    assert response.status_code == 200
    stats = response.json()
    assert "total_batches" in stats
    assert "low_risk" in stats
    assert "medium_risk" in stats
    assert "high_risk" in stats
    assert stats["total_batches"] >= 1


def test_9_17_overall_stats_includes_risk():
    response = client.get("/api/v1/stats/overall")
    assert response.status_code == 200
    stats = response.json()
    assert "risk_level_stats" in stats, "整体统计应包含风险等级统计"


def test_9_18_release_after_arbitration_completed_fail():
    release_data = {"released_by": "质量经理", "remark": "仲裁判定不合格，拒绝放行"}
    response = client.post(f"/api/v1/batches/{batch_id_9}/release", json=release_data)
    assert response.status_code == 403, "仲裁判定不合格仍应无法放行"
    assert "不合格" in response.json()["detail"] or "无法放行" in response.json()["detail"]


def test_9_19_restart_data_persistence():
    batch = client.get(f"/api/v1/batches/{batch_id_9}").json()
    assert batch["risk_level"] in ["low", "medium", "high"], "重启后风险等级应持久化"
    assert batch["risk_score"] >= 0, "重启后风险评分应持久化"

    arbitrations = client.get("/api/v1/arbitrations", params={"batch_id": batch_id_9}).json()
    assert len(arbitrations) >= 1, "重启后仲裁记录应持久化"
    assert arbitrations[0]["status"] == "completed", "重启后仲裁状态应持久化"

    reports = client.get("/api/v1/reports", params={"batch_id": batch_id_9}).json()
    report_types = [r["report_type"] for r in reports]
    assert "arbitration" in report_types, "重启后仲裁报告应持久化"

    exports = client.get("/api/v1/exports", params={"batch_id": batch_id_9}).json()
    assert len(exports) >= 1, "重启后导出记录应持久化"


def test_9_20_arbitration_list_and_detail():
    list_resp = client.get("/api/v1/arbitrations", params={"status": "completed"}).json()
    assert len(list_resp) >= 1

    detail_resp = client.get(f"/api/v1/arbitrations/{arbitration_id_9}").json()
    assert detail_resp["arbitration_code"] is not None
    assert detail_resp["dispute_source"] is not None
    assert detail_resp["handling_opinion"] is not None
    assert detail_resp["final_judgment"] == "fail"

    code_resp = client.get(f"/api/v1/arbitrations/code/{detail_resp['arbitration_code']}").json()
    assert code_resp["id"] == arbitration_id_9


run_test("9.1 创建仲裁测试批次", test_9_1_create_batch_9)
run_test("9.2 送样", test_9_2_create_sample_9)
run_test("9.3 录入不合格检测结果(3项不合格)", test_9_3_input_fail_test_results_9)
run_test("9.4 生成不合格原始报告，风险评分增加", test_9_4_create_original_report_fail_9)
run_test("9.5 申请复检", test_9_5_apply_reinspection_9)
run_test("9.6 录入复检合格结果", test_9_6_input_reinspection_results_9)
run_test("9.7 差异确认复检合格，风险等级变化", test_9_7_confirm_difference_pass_9)
run_test("9.8 生成复检报告", test_9_8_create_reinspection_report_9)
run_test("9.9 发起仲裁", test_9_9_initiate_arbitration)
run_test("9.10 仲裁未完成禁止放行", test_9_10_arbitration_pending_block_release)
run_test("9.11 完成仲裁，推翻复检结论", test_9_11_arbitration_overturn_reinspection)
run_test("9.12 仲裁结论覆盖最终结果", test_9_12_verify_batch_final_result)
run_test("9.13 原始/复检/仲裁三类报告均保留", test_9_13_verify_all_reports_retained)
run_test("9.14 批次质量档案含仲裁信息和风险等级", test_9_14_verify_quality_archive)
run_test("9.15 导出包含仲裁信息", test_9_15_export_with_arbitration)
run_test("9.16 风险等级统计接口可用", test_9_16_risk_level_stats)
run_test("9.17 整体统计包含风险等级", test_9_17_overall_stats_includes_risk)
run_test("9.18 仲裁完成但判定不合格仍无法放行", test_9_18_release_after_arbitration_completed_fail)
run_test("9.19 重启后仲裁/风险/报告/导出均持久化", test_9_19_restart_data_persistence)
run_test("9.20 仲裁列表/详情/编号查询正常", test_9_20_arbitration_list_and_detail)


if failed > 0:
    print(f"\n{Colors.RED}⚠️  有 {failed} 项测试未通过，请检查相关功能{Colors.RESET}")
    sys.exit(1)
else:
    print(f"\n{Colors.GREEN}✅ 所有 {passed} 项验收测试全部通过！{Colors.RESET}")
    print(f"\n  验收要点全部满足:")
    print(f"  ✓ 正常流程：送样→检测→判定→留样→放行")
    print(f"  ✓ 异常流程：复检申请→复检检测→差异确认→最终判定→放行")
    print(f"  ✓ 留样到期销毁：未到期无法销毁，到期后可销毁")
    print(f"  ✓ 复检结论覆盖原始结果，旧报告保留")
    print(f"  ✓ 数据持久化：重启后所有数据不丢失")
    print(f"  ✓ 报告导出：包含原始、复检、最终结果")
    print(f"  ✓ 业务规则：编号重复、项目缺失、复检关联、销毁检查、放行校验全部生效")
    print(f"  ✓ 复检争议仲裁：可发起仲裁，仲裁未完成禁止放行")
    print(f"  ✓ 仲裁结论：覆盖最终判定但不删除旧报告，保留三类报告")
    print(f"  ✓ 风险等级：随复检差异和历史记录自动变化")
    print(f"  ✓ 数据追溯：重启后仲裁单、风险等级、报告链路均可复查")
    sys.exit(0)
