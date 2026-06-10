# Gradual Rollout Engine Specification

## 1. 背景与目标

当前 SplitLab 的实验生命周期从 running 到 full_rollout 是一步到位的——产品经理点击"全量发布"后，treatment 组的流量从实验配比直接跳到100%。现实中，任何功能上线都需要渐进式灰度：先放5%流量观察10分钟，没问题再扩到20%，逐步到50%、100%。缺少渐进式灰度意味着每次全量发布都是一次"全有或全无"的赌注，无法在发现问题时及时止损。

本扩展目标：为 SplitLab 引入渐进式灰度发布引擎，支持按步骤自动推进流量、在护栏指标异常时自动回退、以及产品经理手动推进时的一键操作。

## 2. 需求清单

### 2.1 灰度步骤配置

| 编号 | 需求 | 说明 |
|------|------|------|
| GR-1 | 灰度步骤模型 | 实验新增 rollout_steps 字段（JSON 数组），每个步骤包含 traffic_percentage（treatment 组流量占比）与 hold_seconds（在该步骤停留的时长），如 [{traffic:5, hold:600}, {traffic:20, hold:1800}, {traffic:50, hold:3600}, {traffic:100, hold:0}] |
| GR-2 | 灰度启动 | 实验从 draft → running 时，如果配置了 rollout_steps，则进入"灰度模式"，从第一步开始执行 |
| GR-3 | 步骤自动推进 | 灰度模式下，hold_seconds 到期后自动推进到下一步骤；最后一步的 hold_seconds 为 0 表示停留直到手动操作 |
| GR-4 | 步骤手动推进 | 产品经理可在任意时刻点击"推进到下一步"，无需等待 hold_seconds 到期 |
| GR-5 | 步骤回退 | 产品经理可点击"回退到上一步"或"回退到初始状态"，回退后从该步骤重新开始 hold_seconds 计时 |
| GR-6 | 灰度进度展示 | 前端实验详情页展示灰度进度条（当前步骤/总步骤）、当前 treatment 流量占比、预计下一步时间 |
| GR-7 | 兼容无灰度实验 | 不配置 rollout_steps 的实验行为与当前完全一致（running → 手动 full_rollout） |

### 2.2 SDK 配置渲染

| 编号 | 需求 | 说明 |
|------|------|------|
| SR-1 | 动态流量占比 | 灰度模式下，SDK 配置中 treatment 组的 traffic_percentage 随当前灰度步骤动态变化，control 组自动补足剩余比例 |
| SR-2 | 配置即时生效 | 灰度步骤推进后，后端立即刷新 Redis 配置缓存，SDK 最迟 poll_interval 秒后获取新配比 |
| SR-3 | 多组实验支持 | 多于2组时（如 control/treatment_A/treatment_B），灰度步骤指定哪个组逐步扩量，其余组按原始比例缩放 |

### 2.3 自动回退（与护栏指标联动）

| 编号 | 需求 | 说明 |
|------|------|------|
| AR-1 | 护栏指标配置 | 实验新增 guardrail_metrics 字段，配置需要监控的护栏指标（如 bounce_rate、error_rate），每个护栏含 metric_name、threshold（恶化阈值）、direction（up=上升为异常 / down=下降为异常） |
| AR-2 | 护栏自动检测 | 灰度每个步骤的 hold_seconds 期间，后端自动计算护栏指标值；若护栏指标恶化超过阈值，自动触发回退到上一步 |
| AR-3 | 回退通知 | 自动回退时通过 SSE 推送事件到前端，弹窗提示"护栏指标 [metric_name] 恶化，已自动回退"，并记录审计日志 |
| AR-4 | 护栏不阻断手动推进 | 自动回退后，产品经理仍可手动推进（但需二次确认），手动推进后护栏监控继续生效 |
| AR-5 | 无护栏时不自动回退 | 不配置 guardrail_metrics 的实验，灰度步骤仅按时间推进，无自动回退 |

### 2.4 数据模型与状态

| 编号 | 需求 | 说明 |
|------|------|------|
| DM-1 | 实验状态扩展 | Experiment 新增 current_step_index（当前灰度步骤索引，null 表示非灰度模式） |
| DM-2 | 灰度步骤推进记录 | 新增 RolloutStepLog 表，记录每次步骤推进/回退的时间、步骤索引、触发方式（auto/manual/guardrail）、操作人 |
| DM-3 | 快照兼容 | 快照数据包含 rollout_steps 和 current_step_index，回滚时恢复到快照时的灰度状态 |

## 3. 现有架构约束

### 3.1 必须保持的约束

- **SDK 本地分流不变**：灰度配比变化通过 SDK config 传播，分流仍在 SDK 本地执行
- **桶空间模型不变**：total 10000 桶的精度不变，灰度步骤通过调整 treatment 组的 traffic_percentage 实现
- **审计日志不变**：灰度推进/回退均通过现有 audit_log 记录
- **配置缓存机制不变**：仍使用 Redis 缓存 + ETag/304，灰度推进时触发 invalidate_config_cache

### 3.2 不允许的改动

- 不修改 SDK 分流算法（splitter.py）
- 不修改 MQTT topic 结构
- 不引入新的外部消息队列
- 不修改现有实验状态机的基础转换（draft→running→paused→full_rollout→archived），灰度模式是 running 状态内的子状态

## 4. 技术栈约束

- 后端：Python 3.11+ / FastAPI / asyncio
- 定时调度：asyncio 定时任务（不用 Celery/APScheduler，保持轻量）
- 数据存储：PostgreSQL / SQLAlchemy
- 配置缓存：Redis
- 前端：React / Ant Design / Recharts
- 实时推送：SSE（现有 /api/v1/events/stream）

## 5. 数据模型变更

### 5.1 Experiment 表新增列

| 列名 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `rollout_steps` | JSONB | Null | 灰度步骤配置数组 |
| `current_step_index` | Integer | Null | 当前步骤索引（null=非灰度模式） |
| `guardrail_metrics` | JSONB | Null | 护栏指标配置 |

### 5.2 新增 RolloutStepLog 表

```python
class RolloutStepLog(Base):
    __tablename__ = "rollout_step_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[uuid.UUID] = mapped_column(UUID, ForeignKey("experiments.id"))
    step_index: Mapped[int] = mapped_column(Integer)
    traffic_percentage: Mapped[int] = mapped_column(Integer)
    trigger_type: Mapped[str] = mapped_column(String(20))  # auto / manual / guardrail
    triggered_by: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
```

### 5.3 rollout_steps JSON 格式

```json
[
  {"traffic_percentage": 5, "hold_seconds": 600},
  {"traffic_percentage": 20, "hold_seconds": 1800},
  {"traffic_percentage": 50, "hold_seconds": 3600},
  {"traffic_percentage": 100, "hold_seconds": 0}
]
```

### 5.4 guardrail_metrics JSON 格式

```json
[
  {"metric_name": "bounce_rate", "threshold": 0.05, "direction": "up"},
  {"metric_name": "error_rate", "threshold": 0.02, "direction": "up"}
]
```

## 6. 灰度引擎设计

### 6.1 灰度推进流程

```
实验启动 (draft → running, rollout_steps 非空)
    │
    ▼
设置 current_step_index = 0
    │
    ├─ 构建 SDK config: treatment.traffic_percentage = steps[0].traffic_percentage
    ├─ 启动 hold_seconds 定时器
    │
    ▼
hold_seconds 到期
    │
    ├─ 检查护栏指标
    │   ├─ 护栏异常 → 自动回退（current_step_index -= 1）
    │   └─ 护栏正常 → 推进到下一步（current_step_index += 1）
    │
    ├─ 刷新 SDK config
    ├─ 记录 RolloutStepLog
    ├─ 触发 SSE 推送
    │
    ▼
到达最后一步 (traffic=100%, hold=0)
    │
    ▼
实验状态变为 full_rollout
```

### 6.2 config_service 渲染逻辑

灰度模式下，构建 SDK config 时：
- treatment 组的 traffic_percentage = rollout_steps[current_step_index].traffic_percentage
- control 组的 traffic_percentage = 100 - treatment_traffic
- 其余组按原始比例等比缩放

## 7. 边界条件与异常处理

| 场景 | 处理策略 |
|------|----------|
| rollout_steps 为空数组 | 等效无灰度，实验行为与当前一致 |
| 实验暂停时灰度定时器 | 暂停时取消定时器，恢复时从当前步骤继续计时 |
| 回退到第0步之前 | 不允许，最低回退到 step_index=0 |
| 最后一步 hold_seconds=0 | 停留等待手动操作或护栏触发 |
| 护栏指标数据不足（<30用户） | 不执行护栏检测，不触发回退 |
| 多实例部署时定时器 | 使用 Redis Sorted Set 存储定时器（score=到期时间戳），单实例执行 |
| 配置缓存刷新失败 | 灰度步骤推进仍记录到 DB，config_cache 下次 SDK 轮询时自动从 DB 重建 |
| 手动推进时二次确认 | 前端弹窗"护栏指标曾触发回退，确认继续推进？"，需点击确认 |

## 8. 验收标准

### 8.1 功能验收

- 配置4步灰度（5%→20%→50%→100%），启动实验后 treatment 组流量从5%开始，每步按 hold_seconds 自动推进
- SDK 配置随步骤推进动态更新，新配比最迟 poll_interval 秒生效
- 护栏指标恶化时自动回退到上一步，SSE 推送通知并记录审计日志
- 产品经理可手动推进/回退，回退后护栏监控继续
- 不配置 rollout_steps 的实验行为与当前完全一致

### 8.2 性能验收

- 灰度推进操作延迟不超过 100ms
- 护栏检测计算在 events 表 10 万行时不超过 500ms
- 灰度定时器不增加 Redis 负载

### 8.3 测试要求

- 单元测试：步骤推进逻辑、护栏阈值判定、多组流量缩放计算
- 集成测试：4步灰度全流程（启动→自动推进×3→full_rollout）、暂停恢复不影响计时
- 护栏测试：注入护栏指标恶化→自动回退→手动推进→二次确认