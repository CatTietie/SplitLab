# Experiment Scheduling & Power-Driven Auto-Stop Specification

## 1. 背景与目标

当前 SplitLab 的实验启停完全靠人工操作——产品经理需要记得在周一早上启动实验、周五下午暂停收集数据，还需要反复刷新统计页面看样本量是否足够。更严重的是，实验经常因为"偷看"（peeking）而得出错误结论：在样本量不足时看到 p < 0.05 就急忙全量发布，事后发现是假阳性。产品文档 stats-methodology.md 明确警告了偷看问题，但平台没有技术手段来防止。

本扩展目标：为 SplitLab 引入实验调度（定时启停）和统计功效驱动的自动停止机制，让实验在合适的时机自动运行、在样本量足够且结论可靠时自动停止。

## 2. 需求清单

### 2.1 实验调度

| 编号 | 需求 | 说明 |
|------|------|------|
| ES-1 | 定时启动 | 实验新增 scheduled_start_at 字段（ISO8601 时间戳），设置后实验在 draft 状态下到达指定时间自动转为 running |
| ES-2 | 定时暂停 | 实验新增 scheduled_pause_at 字段，到达指定时间自动将 running 实验转为 paused |
| ES-3 | 时区支持 | 调度时间使用用户指定时区（默认 UTC），前端时间选择器显示用户本地时间 |
| ES-4 | 调度取消 | 产品经理可清除已设置的调度时间，恢复手动控制 |
| ES-5 | 调度状态展示 | 前端实验卡片显示调度状态：已调度启动时间 / 已调度暂停时间 / 无调度 |
| ES-6 | 调度修改 | 产品经理可修改调度时间，新时间覆盖旧时间 |

### 2.2 功效驱动自动停止

| 编号 | 需求 | 说明 |
|------|------|------|
| PS-1 | 最短运行时长 | 实验新增 minimum_runtime_hours 字段（默认 168 = 7天），在此时长内不执行自动停止决策，确保覆盖完整业务周期 |
| PS-2 | 样本量进度追踪 | 前端实验详情页展示样本量进度条：当前用户数 / 推荐最小样本数 |
| PS-3 | 自动停止条件 | 当同时满足以下条件时自动暂停实验：① 运行时长 ≥ minimum_runtime_hours；② 各组用户数 ≥ 推荐最小样本量；③ Z 检验 p < 0.05（使用 O'Brien-Fleming 校正后 α） |
| PS-4 | 自动停止行为 | 自动暂停实验 + SSE 推送通知 + 记录 DecisionLog + 审计日志 |
| PS-5 | 无效实验自动停止 | 当运行时长 ≥ minimum_runtime_hours 且样本量足够，但 p ≥ 0.2 时，推送"实验无显著差异，建议归档"通知（不自动归档，需人工确认） |
| PS-6 | 检测频率 | 与自动决策引擎共享检测周期（每 5 分钟） |
| PS-7 | 开关控制 | 实验新增 auto_stop_enabled 字段（Boolean，默认 True），设为 False 则不执行自动停止 |

### 2.3 防偷看机制

| 编号 | 需求 | 说明 |
|------|------|------|
| AP-1 | 早期结果隐藏 | 运行时长 < minimum_runtime_hours 时，统计页面显示"实验仍在最短运行期内，统计结果尚未稳定"提示，但仍展示数据（附加大号警告标签） |
| AP-2 | 序列检测校正 | 自动停止使用 O'Brien-Fleming 群组序贯设计，与护栏引擎共享校正逻辑，控制多次检测的总体假阳性率 |
| AP-3 | 检测次数追踪 | 实验新增 analysis_count 字段，每执行一次自动检测自增1，用于 O'Brien-Fleming α 值查表 |

### 2.4 前端交互

| 编号 | 需求 | 说明 |
|------|------|------|
| FE-1 | 调度时间选择器 | 实验创建/编辑弹窗新增调度区域：日期时间选择器 + 时区下拉 + 清除按钮 |
| FE-2 | 样本量进度 | 实验详情页统计区域顶部：进度条（当前/推荐）+ 预计达标时间估算 |
| FE-3 | 自动停止历史 | 实验详情页新增"决策历史"时间线：展示每次自动决策的时间和原因 |
| FE-4 | 最短运行期警告 | 统计图表区域叠加黄色半透明遮罩 + 提示文字，最短运行期结束后自动移除 |

## 3. 现有架构约束

### 3.1 必须保持的约束

- **手动操作不受限制**：调度和自动停止不阻止产品经理手动启停实验
- **现有状态机转换不变**
- **统计计算逻辑不变**
- **审计日志机制不变**

### 3.2 不允许的改动

- 不引入外部调度框架（不用 Celery/APScheduler）
- 不修改 SDK 代码
- 不修改 Event 表结构
- 不修改 config_service 核心逻辑

## 4. 技术栈约束

- 后端：Python 3.11+ / FastAPI / asyncio
- 定时调度：asyncio 后台任务 + Redis Sorted Set（调度时间戳为 score）
- 数据存储：PostgreSQL / SQLAlchemy
- 前端：React / Ant Design
- 实时推送：SSE

## 5. 数据模型变更

### 5.1 Experiment 表新增列

| 列名 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `scheduled_start_at` | DateTime | Null | 定时启动时间 |
| `scheduled_pause_at` | DateTime | Null | 定时暂停时间 |
| `timezone` | String(32) | "UTC" | 调度时区 |
| `minimum_runtime_hours` | Integer | 168 | 最短运行时长（小时） |
| `auto_stop_enabled` | Boolean | True | 是否启用自动停止 |
| `analysis_count` | Integer | 0 | 已执行自动检测次数 |

## 6. 调度引擎设计

### 6.1 调度定时器

使用 Redis Sorted Set 存储待执行调度：

```
Key: schedule:timers
Score: Unix timestamp (到期时间)
Value: {"experiment_id": "uuid", "action": "start"|"pause"}
```

后台 asyncio 任务每 10 秒扫描 `ZRANGEBYSCORE schedule:timers 0 <now>`，取出到期任务执行。

### 6.2 自动停止检测流程

```
每 5 分钟:
    for each running experiment with auto_stop_enabled=True:
        │
        ├─ 检查最短运行期
        │   └─ (now - started_at) < minimum_runtime_hours → 跳过
        │
        ├─ 检查样本量
        │   └─ 各组用户数 < 推荐最小样本量 → 跳过
        │
        ├─ analysis_count += 1
        │
        ├─ 计算统计值（使用 O'Brien-Fleming α）
        │
        ├─ p < α ?
        │   ├─ Yes → 自动暂停 + 推送 + 记录
        │   └─ No → p ≥ 0.2 ?
        │       ├─ Yes → 推送"建议归档"通知
        │       └─ No → 继续运行
```

### 6.3 预计达标时间

基于当前用户增速估算：

```python
def estimate_time_to_significance(
    current_users: int,
    required_users: int,
    users_per_hour: float,
) -> float | None:
    if users_per_hour <= 0:
        return None  # 无法估算
    remaining = required_users - current_users
    if remaining <= 0:
        return 0  # 已达标
    return remaining / users_per_hour  # 小时数
```

## 7. 边界条件与异常处理

| 场景 | 处理策略 |
|------|----------|
| 调度时间已过去 | 立即执行对应操作（启动/暂停） |
| 调度时间与手动操作冲突 | 手动操作优先，调度到期时检查当前状态，若已在目标状态则跳过 |
| 实验已暂停后调度启动到达 | 执行启动操作（从 paused → running） |
| minimum_runtime_hours 设为 0 | 无最短运行期保护，首次检测即可触发自动停止 |
| 分析次数超过 O'Brien-Fleming 表范围 | 使用最后一次的 α 值 |
| 用户增速为 0 | 预计达标时间显示"无法估算" |
| 多实例部署时调度执行 | 使用 Redis ZPOPMIN 原子操作，确保同一调度只执行一次 |
| 自动停止后产品经理恢复实验 | analysis_count 不重置，继续累计检测次数 |

## 8. 验收标准

### 8.1 功能验收

- 设置 scheduled_start_at 后，实验在指定时间自动启动
- 设置 scheduled_pause_at 后，实验在指定时间自动暂停
- 实验运行满 minimum_runtime_hours 且样本量足够且 p < α 时自动暂停
- 运行期内统计页面展示警告，提醒结果可能不稳定
- 不设置调度的实验行为与当前一致

### 8.2 性能验收

- 调度扫描在 100 个待调度实验时不超过 50ms
- 自动停止检测在 20 个 running 实验时不超过 10 秒
- 预计达标时间计算为纯算术，延迟可忽略

### 8.3 测试要求

- 单元测试：调度时间到期执行、最短运行期判定、O'Brien-Fleming 检测次数追踪、预计达标时间计算
- 集成测试：配置调度启动→等待触发→自动运行→样本量达标→自动停止→SSE 通知
- 冲突测试：调度启动前手动启动→调度到期时状态检查跳过