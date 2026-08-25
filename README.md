# 质检样品留样与复检流程服务

## 项目用途

本服务实现了完整的质检样品留样与复检流程管理，适用于生产企业的质量检验部门。主要功能包括：

- **批次送检管理**：生产批次送检后自动生成唯一的样品编号
- **样品留样管理**：自动分配留样库位，支持留样到期提醒与销毁
- **检测流程管理**：支持多检测项录入、自动判定、检测报告生成
- **复检流程管理**：异常批次可发起复检，保留原始检测结果
- **差异确认与放行**：复检结果差异确认，最终批次放行控制
- **报告导出**：支持Excel/PDF格式导出，包含原始结果、复检结果和最终判定
- **统计分析**：复检差异统计、批次质量分析、留样过期预警
- **数据追溯**：所有报告可追溯到批次，支持批次质量档案查询

## 技术架构

- **Web框架**: FastAPI 0.104.1
- **数据库**: SQLAlchemy 2.0 + SQLite
- **数据验证**: Pydantic 2.5
- **导出功能**: openpyxl (Excel) + reportlab (PDF)
- **API文档**: 自动生成 Swagger UI

## 目录结构

```
lym-0636/
├── app/
│   ├── __init__.py
│   ├── config.py              # 配置文件
│   ├── database.py            # 数据库连接
│   ├── exceptions.py          # 自定义异常
│   ├── models.py              # 数据模型
│   ├── schemas.py             # Pydantic模型
│   ├── services/              # 业务逻辑层
│   │   ├── __init__.py
│   │   ├── base_service.py
│   │   ├── batch_service.py
│   │   ├── sample_service.py
│   │   ├── test_service.py
│   │   ├── retention_service.py
│   │   ├── reinspection_service.py
│   │   ├── report_service.py
│   │   ├── export_service.py
│   │   └── stats_service.py
│   └── routers/               # API路由层
│       ├── __init__.py
│       ├── batch_router.py
│       ├── sample_router.py
│       ├── test_router.py
│       ├── retention_router.py
│       ├── reinspection_router.py
│       ├── report_router.py
│       ├── export_router.py
│       └── stats_router.py
├── data/                      # 数据库文件目录
├── exports/                   # 导出文件目录
├── tests/                     # 测试脚本
├── main.py                    # 应用入口
├── requirements.txt
├── pyproject.toml
└── README.md
```

## 启动方式

### 1. 安装依赖

```bash
python3 -m pip install -r requirements.txt
```

### 2. 启动服务

```bash
python3 main.py
```

或者使用 uvicorn 直接启动：

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. 访问服务

- 服务地址: http://localhost:8000
- API文档: http://localhost:8000/docs
- 健康检查: http://localhost:8000/health

## 核心业务流程

### 正常流程

```
创建批次 → 送样(生成样品编号) → 录入检测结果 → 生成原始报告 → 留样(分配库位)
                                                              ↓
                                                  合格 → 批次放行
                                                  ↓
                                                不合格 → 申请复检
                                                              ↓
                                              复检取样 → 录入复检结果
                                                              ↓
                                          差异确认 → 生成最终报告 → 放行/拒收
```

### 数据流转说明

1. **批次(Batch)** → 生产批次信息，关联多个样品和报告
2. **样品(Sample)** → 每个批次送检后生成，包含唯一样品编号和留样位置
3. **检测项(TestItem)** → 预设的检测项目标准，包括上下限和判定规则
4. **检测结果(TestResult)** → 每个样品的具体检测数据，关联检测项
5. **留样(Retention)** → 样品入库记录，包含库位、留样期限、销毁状态
6. **复检(ReInspection)** → 复检申请记录，关联原始样品、原始报告和复检样品
7. **报告(Report)** → 检测报告，分为原始报告、复检报告、最终报告
8. **导出记录(ExportRecord)** → 记录每次导出操作，包含导出内容和文件路径

## 关键业务规则校验

| 校验规则 | 实现位置 | 异常类型 |
|---------|---------|---------|
| 样品编号重复 | SampleService.create_sample | SampleCodeDuplicateError |
| 检测项目缺失 | TestService.validate_test_items_complete | TestItemMissingError |
| 复检未关联原报告 | ReInspectionService.validate_reinspection_request | ReInspectionLinkError |
| 留样已销毁仍复检 | ReInspectionService.validate_reinspection_request | RetentionDestroyedError |
| 判定不合格直接放行 | BatchService.validate_release | ReleaseNotAllowedError |
| 留样未到期销毁 | RetentionService.validate_destroy | RetentionNotExpiredError |

## 验收路径

### 验收1：正常流程 - 合格批次放行

**API调用顺序**：

1. 创建检测项
   ```
   POST /api/v1/tests/items
   ```

2. 创建批次
   ```
   POST /api/v1/batches
   ```

3. 送样（生成样品编号）
   ```
   POST /api/v1/samples
   ```

4. 录入检测结果
   ```
   POST /api/v1/tests/results
   ```

5. 生成原始检测报告
   ```
   POST /api/v1/reports/original/{sample_id}
   ```

6. 留样（分配库位）
   ```
   POST /api/v1/retentions
   ```

7. 放行批次
   ```
   POST /api/v1/batches/{batch_id}/release
   ```

**验收要点**：
- 样品编号唯一且自动生成
- 留样位置自动分配（格式：A-01-01）
- 检测值自动判定（pass/fail）
- 批次状态流转正确
- 放行成功

### 验收2：异常流程 - 不合格批次复检

**API调用顺序**：

1. 同验收1步骤1-5，但录入不合格检测结果

2. 申请复检
   ```
   POST /api/v1/reinspections
   ```

3. 录入复检结果
   ```
   POST /api/v1/reinspections/{reinspection_id}/test-results
   ```

4. 完成复检检测
   ```
   POST /api/v1/reinspections/{reinspection_id}/complete-testing
   ```

5. 差异确认
   ```
   POST /api/v1/reinspections/{reinspection_id}/confirm-difference
   ```

6. 生成最终报告
   ```
   POST /api/v1/reports/final/{batch_id}
   ```

7. 放行批次
   ```
   POST /api/v1/batches/{batch_id}/release
   ```

**验收要点**：
- 复检必须关联原始报告
- 原始报告自动标记为非活跃
- 复检结论覆盖原始结果
- 旧报告保留可查询
- 必须差异确认后才能放行

### 验收3：留样到期销毁

**API调用顺序**：

1. 同验收1步骤1-6

2. 检查过期留样（可手动修改数据库模拟过期）
   ```
   POST /api/v1/retentions/check-expired
   ```

3. 销毁留样
   ```
   POST /api/v1/retentions/{retention_id}/destroy
   ```

**验收要点**：
- 未到期留样无法销毁
- 销毁后留样位置释放
- 已销毁留样无法复检

### 验收4：数据持久化验证

1. 完成以上验收后，重启服务
2. 验证以下数据依然存在：
   - 样品位置信息
   - 检测结果
   - 复检链路关系
   - 导出记录

### 验收5：数据追溯

1. 查询批次质量档案
   ```
   GET /api/v1/batches/{batch_id}/archive
   ```

2. 验证：
   - 可追溯到批次所有样品
   - 可查看原始报告和复检报告
   - 可查看留样信息和复检记录

### 验收6：报告导出

1. 导出批次档案
   ```
   POST /api/v1/exports
   ```

2. 下载导出文件
   ```
   GET /api/v1/exports/download/{export_no}
   ```

**验收要点**：
- 导出包含原始结果、复检结果和最终判定
- 支持Excel和PDF两种格式
- 导出记录可查询

### 验收7：统计分析

1. 复检差异统计
   ```
   GET /api/v1/stats/reinspection-diff
   ```

2. 留样位置查询
   ```
   GET /api/v1/retentions/locations
   ```

3. 留样过期统计
   ```
   GET /api/v1/stats/retention-expire
   ```

## API接口清单

### 批次管理
- `POST /api/v1/batches` - 创建批次
- `GET /api/v1/batches` - 获取批次列表
- `GET /api/v1/batches/{batch_id}` - 获取批次详情
- `POST /api/v1/batches/{batch_id}/release` - 放行批次
- `GET /api/v1/batches/{batch_id}/archive` - 获取批次质量档案

### 样品管理
- `POST /api/v1/samples` - 送样/创建样品
- `GET /api/v1/samples` - 获取样品列表
- `GET /api/v1/samples/{sample_id}` - 获取样品详情

### 检测管理
- `POST /api/v1/tests/items` - 创建检测项
- `GET /api/v1/tests/items` - 获取检测项列表
- `POST /api/v1/tests/results` - 录入检测结果
- `GET /api/v1/tests/results` - 获取检测结果列表

### 留样管理
- `POST /api/v1/retentions` - 创建留样
- `GET /api/v1/retentions` - 获取留样列表
- `GET /api/v1/retentions/locations` - 获取留样位置列表
- `POST /api/v1/retentions/{retention_id}/destroy` - 销毁留样
- `POST /api/v1/retentions/check-expired` - 检查过期留样

### 复检管理
- `POST /api/v1/reinspections` - 申请复检
- `GET /api/v1/reinspections` - 获取复检列表
- `POST /api/v1/reinspections/{id}/test-results` - 录入复检结果
- `POST /api/v1/reinspections/{id}/complete-testing` - 完成复检检测
- `POST /api/v1/reinspections/{id}/confirm-difference` - 确认复检差异

### 报告管理
- `GET /api/v1/reports` - 获取报告列表
- `GET /api/v1/reports/{report_id}` - 获取报告详情
- `POST /api/v1/reports/original/{sample_id}` - 生成原始检测报告
- `POST /api/v1/reports/final/{batch_id}` - 生成最终报告

### 导出管理
- `POST /api/v1/exports` - 导出报告
- `GET /api/v1/exports` - 获取导出记录列表
- `GET /api/v1/exports/download/{export_no}` - 下载导出文件

### 统计分析
- `GET /api/v1/stats/overall` - 获取整体统计
- `GET /api/v1/stats/reinspection-diff` - 复检差异统计
- `GET /api/v1/stats/batch-quality` - 批次质量统计
- `GET /api/v1/stats/reinspection-trend` - 复检趋势统计

## 配置说明

在 `app/config.py` 中可配置以下参数：

- `SAMPLE_CODE_PREFIX`: 样品编号前缀（默认"SP"）
- `RETENTION_PERIOD_DAYS`: 留样期限天数（默认90天）
- `WAREHOUSE_ZONES`: 库区列表（默认["A", "B", "C"]）
- `SHELVES_PER_ZONE`: 每区货架数（默认10）
- `POSITIONS_PER_SHELF`: 每架货位数（默认20）

## 数据持久化

所有数据存储在 SQLite 数据库文件中：
- 路径: `data/quality_inspection.db`
- 导出文件存储在: `exports/` 目录

重启服务后所有数据不会丢失。

## 运行测试

```bash
cd tests
python3 test_acceptance.py
```

详细测试脚本见 `tests/test_acceptance.py`。
