# Multi-Dimensional User Targeting Specification

## 1. 背景与目标

当前 SplitLab 的实验定向完全依赖桶空间哈希分流，所有用户按同一规则随机分配。现实中，产品经理经常需要"只对移动端用户做实验"或"只对付费用户测试新功能"，但目前只能通过白名单逐个用户添加，无法按用户属性批量定向。更关键的是，桶空间随机分配无法保证各组在关键属性上的均衡——如果移动端用户集中在 treatment 组，实验结果的差异可能是设备差异而非功能效果。

本扩展目标：为 SplitLab 引入多维用户定向规则，支持按用户属性筛选实验人群，并在分流时保证各组在关键维度上的均衡性（分层抽样）。

## 2. 需求清单

### 2.1 用户属性收集

| 编号 | 需求 | 说明 |
|------|------|------|
| UA-1 | 属性上报接口 | SDK 新增 POST /api/v1/sdk/attributes 接口，业务代码调用 client.set_attributes(user_id, {"country":"CN","device":"mobile","plan":"premium"}) 上报用户属性 |
| UA-2 | 属性存储 | 用户属性存储在 PostgreSQL 的 user_attributes 表，key 为 (user_id, attribute_key)，value 为字符串 |
| UA-3 | 属性缓存 | 最近 1 小时内活跃用户的属性缓存到 Redis Hash（key: attr:{user_id}），减少 DB 查询 |
| UA-4 | 属性时效 | 属性值可被后续上报覆盖，以最后上报的值为准 |
| UA-5 | 属性键值约束 | attribute_key 为 [a-z_]+ 格式，最长 64 字符；attribute_value 为字符串，最长 256 字符；每用户最多 20 个属性 |

### 2.2 定向规则 DSL

| 编号 | 需求 | 说明 |
|------|------|------|
| TL-1 | 定向规则模型 | 实验新增 targeting_rules 字段（JSON），定义参与该实验的用户属性条件 |
| TL-2 | 规则语法 | 支持 AND/OR 逻辑组合，支持 eq/neq/in/contains/gt/lt 比较算子。示例：{"operator":"AND","conditions":[{"key":"country","op":"in","values":["CN","US"]},{"key":"device","op":"eq","value":"mobile"}]} |
| TL-3 | 规则嵌套 | 最多 3 层嵌套 |
| TL-4 | 定向评估位置 | 定向规则在 SDK 端评估——SDK config 中包含每个实验的 targeting_rules，SDK 在本地完成属性匹配后再分流 |
| TL-5 | 属性缺失处理 | 用户未上报某属性时，该属性的条件评估为 false（不满足定向） |
| TL-6 | 无定向规则 | 不配置 targeting_rules 的实验，所有进入桶范围的用户均参与（与当前行为一致） |

### 2.3 分层抽样均衡

| 编号 | 需求 | 说明 |
|------|------|------|
| SS-1 | 分层维度配置 | 实验新增 stratification_dimensions 字段（字符串数组），指定需要均衡的属性维度，如 ["country", "device"] |
| SS-2 | 分层哈希 | 对每个分层维度，使用独立哈希函数确保该维度在各组中均匀分布：bucket = hash(user_id + dimension_key + layer.salt) % 10000 |
| SS-3 | 均衡验证 | 实验运行期间，统计页面展示各分层维度在每组中的分布比例；若偏差超过 3%，展示警告标签 |
| SS-4 | 分层抽样算法 | SDK 分流时，先检查用户是否满足定向规则，若满足则按分层哈希 + 桶范围分配组；分层哈希仅用于验证均衡性，不影响分流结果（分流仍基于原始 hash + bucket） |

### 2.4 前端交互

| 编号 | 需求 | 说明 |
|------|------|------|
| FE-1 | 定向规则编辑器 | 实验创建/编辑弹窗新增"定向规则"区域：可视化条件组合器（拖拽添加条件，选择 AND/OR 逻辑） |
| FE-2 | 属性预览 | 定向规则区域下方展示"预估可达用户数"（基于已有属性数据的统计估算） |
| FE-3 | 分层维度选择 | 实验创建/编辑弹窗新增"分层维度"多选框 |
| FE-4 | 均衡性报告 | 实验统计页面新增"分层均衡性"标签页：各维度各组分布条形图 + 偏差百分比 |

## 3. 现有架构约束

### 3.1 必须保持的约束

- **桶空间分流模型不变**：定向规则是在分流前的过滤层，不影响桶空间分配逻辑
- **SDK 本地分流原则不变**：定向规则在 SDK 端评估，不引入服务端分流调用
- **现有实验无定向规则时行为不变**
- **事件上报格式向后兼容**

### 3.2 不允许的改动

- 不修改现有 splitter.py 的 get_bucket 和 get_variant 核心逻辑
- 不引入服务端分流（所有决策仍在 SDK 本地完成）
- 不修改 SDK config 的 ETag/304 机制
- 不修改 Event 表结构

## 4. 技术栈约束

- 后端：Python 3.11+ / FastAPI / asyncio
- 属性存储：PostgreSQL + Redis 缓存
- SDK：Python（config_poller + 本地属性缓存）
- 前端：React / Ant Design
- 定向评估：SDK 端纯 Python 实现

## 5. 数据模型变更

### 5.1 新增 UserAttribute 表

```python
class UserAttribute(Base):
    __tablename__ = "user_attributes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(256), nullable=False)
    attribute_key: Mapped[str] = mapped_column(String(64), nullable=False)
    attribute_value: Mapped[str] = mapped_column(String(256), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "attribute_key", name="uq_user_attr"),
        Index("idx_user_attr_key_value", "attribute_key", "attribute_value"),
    )
```

### 5.2 Experiment 表新增列

| 列名 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `targeting_rules` | JSONB | Null | 定向规则条件树 |
| `stratification_dimensions` | JSONB | Null | 分层维度列表 ["country","device"] |

### 5.3 SDK Config 扩展

每个实验配置新增字段：

```json
{
  "id": "...",
  "key": "homepage_cta",
  "targeting_rules": {
    "operator": "AND",
    "conditions": [
      {"key": "country", "op": "in", "values": ["CN", "US"]},
      {"key": "device", "op": "eq", "value": "mobile"}
    ]
  },
  "stratification_dimensions": ["country", "device"],
  ...
}
```

### 5.4 定向规则 DSL 语法

```
TargetingRule := LogicalExpr | ConditionExpr
LogicalExpr   := { "operator": "AND" | "OR", "rules": TargetingRule[] }
ConditionExpr := { "key": string, "op": Operator, "value": string | null, "values": string[] | null }
Operator      := "eq" | "neq" | "in" | "not_in" | "contains" | "gt" | "lt" | "gte" | "lte"
```

## 6. SDK 定向评估设计

### 6.1 评估流程

```
get_variant(user_id, experiment_key)
    │
    ├─ 查找实验配置
    ├─ 检查白名单
    │
    ├─ 评估定向规则 (targeting_rules)
    │   ├─ 无 targeting_rules → 跳过，继续分流
    │   ├─ 有 targeting_rules → 从本地属性缓存读取用户属性
    │   │   ├─ 属性缺失 → 返回 None（不参与）
    │   │   └─ 递归评估条件树
    │   │       ├─ true → 继续分流
    │   │       └─ false → 返回 None
    │
    └─ 执行桶空间分流（现有逻辑不变）
```

### 6.2 SDK 属性管理

```python
class SplitLabClient:
    def set_attributes(self, user_id: str, attributes: dict[str, str]):
        """设置用户属性，存入本地缓存并异步上报"""
        self._attributes_cache[user_id] = attributes
        self._attr_buffer.append((user_id, attributes))

    def get_attributes(self, user_id: str) -> dict[str, str]:
        """获取用户属性（本地缓存）"""
        return self._attributes_cache.get(user_id, {})
```

### 6.3 分层均衡性验证

后端统计 API 新增分层均衡性计算：

```sql
-- 按组和属性值统计用户分布
SELECT g.name as group_name, ua.attribute_value, COUNT(DISTINCT e.user_id)
FROM events e
JOIN experiment_groups g ON e.group_id = g.id
JOIN user_attributes ua ON e.user_id = ua.user_id
WHERE e.experiment_id = :exp_id AND ua.attribute_key = :dimension
GROUP BY g.name, ua.attribute_value
```

## 7. 边界条件与异常处理

| 场景 | 处理策略 |
|------|----------|
| 用户属性缓存为空 | 定向规则评估为 false，用户不参与实验 |
| 定向规则引用不存在的属性键 | 该条件评估为 false（属性缺失） |
| 属性值类型不匹配（gt/lt 比较非数字） | 尝试 float() 转换，失败则评估为 false |
| 大量用户同时上报属性 | 批量 INSERT ON CONFLICT UPDATE，Redis 缓存批量 SET |
| SDK 属性上报失败 | 本地缓存仍可用，属性上报走 WAL 重试 |
| 分层维度超过 5 个 | 拒绝创建，返回 400 |
| 定向规则嵌套超过 3 层 | 拒绝创建，返回 400 |
| 配置过大（定向规则 + 属性键过多） | SDK config 响应体超过 1MB 时警告，超过 5MB 拒绝 |

## 8. 验收标准

### 8.1 功能验收

- 配置定向规则"country in [CN, US] AND device eq mobile"后，仅满足条件的用户参与实验，其他用户 get_variant 返回 None
- SDK 属性上报后，30秒内可在后端统计中查询到该用户的属性值
- 分层维度均衡性报告显示各组分布，偏差超过3%时显示警告
- 不配置定向规则的实验行为与当前完全一致

### 8.2 性能验收

- SDK 端定向评估延迟不超过 0.1ms
- 属性上报批量接口（100用户×5属性）不超过 200ms
- 定向规则+属性值增加 SDK config 体积不超过 50%
- 分层均衡性查询在 10 万事件时不超过 1 秒

### 8.3 测试要求

- 单元测试：定向规则评估（AND/OR/各算子）、属性缺失、嵌套规则、均衡性计算
- 集成测试：上报属性→配置定向规则→SDK 分流验证→统计页面展示分布
- 边界测试：超长属性值、特殊字符、大量属性键、规则嵌套限制