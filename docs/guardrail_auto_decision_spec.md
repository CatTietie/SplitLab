# Guardrail Metrics & Auto-Decision Engine Specification

## 1. 背景与目标

当前 SplitLab 的统计分析只支持单个目标事件（goal_event）的 Z 检验，产品经理需要手动查看结果并决定是否全量发布。这有两个严重问题：一是实验期间无法同时监控"反面指标"（如转化率提升了但跳出率也恶化了），产品经理可能因为只看目标指标而忽略系统性风险；二是没有自动决策机制——即使数据已经明确显示某组胜出或某组有害，实验仍需人工介入才能暂停或全量发布，深夜和周末经常无人看管。

本扩展目标：为 SplitLab 引入护栏指标体系和自动决策引擎，在实验运行期间持续监控多个指标，当护栏指标恶化时自动暂停，当主指标达到显著时自动提示或全量发布。

## 2. 需求清单

### 2.1 多指标体系

| 编号 | 需求 | 说明 |
|------|------|------|
| MM-1 | 指标类型分类 | 实验指标分为 primary_metric（主指标，1个）和 guardrail_metrics（护栏指标，0-N个）。主指标用于判断实验胜负，护栏指标用于监控不应恶化的底线 |
| MM-2 | 指标配置格式 | 实验新增 metrics_config 字段：{primary: {event_name: "purchase", direction: "up"}, guardrails: [{event_name: "bounce_rate", direction: "up", threshold: 0.05}]}。direction 表示哪个方向为"好"：up=上升好，down=下降好 |
| MM-3 | 多指标同时计算 | 统计 API 返回所有配置指标（primary + guardrails）的各组转化率、置信区间和 Z 检验结果 |
| MM-4 | 护栏恶化判定 | 护栏指标的 treatment 组相比 control 组恶化超过 threshold 时判定为"护栏触发"。direction=up 时恶化=上升，direction=down 时恶化=下降 |
| MM-5 | 护栏严重度 | 护栏触发时区分 warning（恶化超过 threshold 但未达 2×threshold）和 critical（恶化超过 2×threshold），两种级别触发不同操作 |

### 2.2 自动决策引擎

| 编号 | 需求 | 说明 |
|------|------|------|
| AD-1 | 自动暂停 | 护栏 critical 触发时自动暂停实验（status → paused），并推送通知 |
| AD-2 | 自动提示 | 护栏 warning 触发时不暂停，但通过 SSE 推送警告通知到前端，前端弹窗展示 |
| AD-3 | 自动全量提示 | 主指标达到统计显著（p < 0.05）且护栏未触发时，通过 SSE 推送"建议全量发布"通知，但不自动执行 |
| AD-4 | 检测频率 | 自动决策引擎每 5 分钟对 running 状态的实验执行一次指标检测 |
| AD-5 | 样本量门槛 | 实验每组用户数未达到推荐最小样本量时，不执行自动决策（避免样本不足导致误判） |
| AD-6 | 冷却期 | 自动暂停后，30 分钟内不重复检测同一实验（避免反复暂停/恢复） |
| AD-7 | 决策日志 | 每次自动决策记录到 DecisionLog 表，包含实验 ID、决策类型、触发指标、指标值、时间 |

### 2.3 统计方法扩展

| 编号 | 需求 | 说明 |
|------|------|------|
| SE-1 | 序列检测校正 | 由于每 5 分钟检测一次（多次 peeking），使用 O'Brien-Fleming 群组序贯设计校正显著性水平，控制总体假阳性率在 0.05 |
| SE-2 | 效应量估计 | 统计结果新增 lift 字段（treatment 相对 control 的提升百分比），附带 lift 的 95% 置信区间 |
| SE-3 | 贝叶斯补充 | 除频率派 Z 检验外，可选输出贝叶斯后验概率 P(treatment > control)，辅助产品决策 |

### 2.4 前端展示

| 编号 | 需求 | 说明 |
|------|------|------|
| FE-1 | 多指标仪表盘 | 实验统计页面展示所有指标的卡片：主指标突出显示，护栏指标依次排列，每个卡片含转化率、lift、p-value、护栏状态徽标 |
| FE-2 | 护栏趋势图 | 每个护栏指标的时间序列折线图：control vs treatment，叠加恶化阈值参考线 |
| FE-3 | 决策通知面板 | 前端新增"决策通知"浮动面板，展示最近的自动决策（暂停/警告/建议） |
| FE-4 | 指标配置界面 | 实验创建/编辑弹窗新增"指标配置"区域：主指标选择 + 护栏指标添加 + 阈值设置 |

## 3. 现有架构约束

### 3.1 必须保持的约束

- **现有 Z 检验结果不变**：不配置 metrics_config 时，统计 API 行为与当前一致（单 goal_event）
- **SDK 事件上报格式不变**
- **实验状态机基础转换不变**
- **审计日志机制不变**

### 3.2 不允许的改动

- 不修改 SDK 代码（多指标监控是后端侧行为）
- 不修改 Event 表结构
- 不修改 splitter.py
- 不引入新的外部计算引擎（如 Spark）

## 4. 技术栈约束

- 后端：Python 3.11+ / FastAPI / asyncio
- 统计计算：scipy + 纯 Python（O'Brien-Fleming 校正表预计算）
- 定时调度：asyncio 后台任务
- 数据存储：PostgreSQL / SQLAlchemy
- 前端：React / Ant Design / Recharts
- 实时推送：SSE

## 5. 数据模型变更

### 5.1 Experiment 表新增列

| 列名 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `metrics_config` | JSONB | Null | 指标配置（primary + guardrails） |
| `auto_decision_enabled` | Boolean | True | 是否启用自动决策 |

### 5.2 新增 DecisionLog 表

```python
class DecisionLog(Base):
    __tablename__ = "decision_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[uuid.UUID] = mapped_column(UUID, ForeignKey("experiments.id"))
    decision_type: Mapped[str] = mapped_column(String(32))  # auto_pause / warning / suggest_rollout
    trigger_metric: Mapped[str] = mapped_column(String(128))
    metric_value: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    details: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
```

### 5.3 metrics_config JSON 格式

```json
{
  "primary": {
    "event_name": "purchase",
    "direction": "up"
  },
  "guardrails": [
    {
      "event_name": "bounce_rate",
      "direction": "up",
      "threshold": 0.05
    },
    {
      "event_name": "error_rate",
      "direction": "up",
      "threshold": 0.02
    }
  ]
}
```

### 5.4 统计 API 响应扩展

```json
{
  "experiment_id": "uuid",
  "primary_metric": {
    "event_name": "purchase",
    "groups": [...],
    "z_statistic": 4.2,
    "p_value": 0.0001,
    "is_significant": true,
    "lift": 0.15,
    "lift_ci_lower": 0.08,
    "lift_ci_upper": 0.22,
    "bayesian_prob": 0.998
  },
  "guardrail_metrics": [
    {
      "event_name": "bounce_rate",
      "status": "warning",
      "groups": [...],
      "z_statistic": 2.1,
      "p_value": 0.036,
      "deterioration": 0.06,
      "threshold": 0.05
    }
  ]
}
```

## 6. 自动决策引擎设计

### 6.1 检测流程

```
每 5 分钟执行:
    for each running experiment with auto_decision_enabled=True:
        │
        ├─ 检查样本量门槛
        │   └─ 未达标 → 跳过
        │
        ├─ 计算所有指标（primary + guardrails）
        │   ├─ 使用 O'Brien-Fleming 校正后的 α 值
        │
        ├─ 评估护栏状态
        │   ├─ 任一护栏 critical → 自动暂停 + 推送 + 记录日志
        │   ├─ 任一护栏 warning → 推送警告 + 记录日志
        │   └─ 护栏正常 → 继续
        │
        ├─ 评估主指标
        │   ├─ 显著 + direction 匹配 → 推送"建议全量发布" + 记录日志
        │   └─ 不显著 → 无操作
        │
        └─ 冷却期检查（同一实验30分钟内不重复暂停）
```

### 6.2 O'Brien-Fleming 校正

预计算不同 interim analysis 次数对应的 α 值：

| 检测次数 | 累计 α | 单次 α |
|----------|--------|--------|
| 1 (首次) | 0.05 | 0.0000 (极严格) |
| 2 | 0.05 | 0.0048 |
| 3 | 0.05 | 0.0125 |
| 4 | 0.05 | 0.0250 |
| ≥5 | 0.05 | 0.0410 |

使用当前检测次数查表得到单次 α 值，替换 Z 检验中的固定 0.05。

## 7. 边界条件与异常处理

| 场景 | 处理策略 |
|------|----------|
| 无 metrics_config | 不执行自动决策，统计 API 退化到当前单 goal_event 行为 |
| primary_metric 的 event_name 在事件中不存在 | 统计结果为空，不触发决策 |
| 护栏 event_name 无事件 | 该护栏评估为"正常"（无恶化证据），不触发 |
| 多个护栏同时触发 | 按 critical > warning 优先级处理，只记录一条最严重的决策 |
| 自动暂停后产品经理手动恢复 | 恢复后 30 分钟冷却期继续生效 |
| O'Brien-Fleming 检测次数超过预计算表 | 使用最后一次的 α 值 |
| 贝叶斯计算数值不稳定 | 降级为仅输出频率派结果，bayesian_prob 返回 null |
| 护栏 threshold 为 0 | 表示任何恶化都触发，等效于 direction 匹配即触发 |

## 8. 验收标准

### 8.1 功能验收

- 配置主指标 + 2个护栏指标后，统计 API 同时返回所有指标的转化率和检验结果
- 护栏恶化超过 2×threshold 时实验自动暂停，SSE 推送通知
- 护栏恶化超过 1×threshold 但未达 2× 时推送警告不暂停
- 主指标显著且护栏未触发时推送"建议全量发布"但不自动执行
- 样本量未达标时不执行自动决策
- 不配置 metrics_config 时统计 API 行为与当前完全一致

### 8.2 性能验收

- 多指标统计计算（1 primary + 3 guardrails）在 10 万事件时不超过 1 秒
- 自动决策检测循环在 20 个 running 实验时不超过 10 秒
- O'Brien-Fleming 校正计算为纯查表，延迟可忽略

### 8.3 测试要求

- 单元测试：O'Brien-Fleming α 值查表、护栏恶化判定（warning/critical 边界）、lift 计算与置信区间
- 集成测试：配置3指标→注入数据→护栏 critical→自动暂停→SSE 推送→手动恢复
- 序列检测测试：连续5次检测→α 值逐步放宽→第5次检测时更易达到显著