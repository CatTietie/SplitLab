# 实验配置 Schema

## 层 (Layer)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string(128) | 是 | 唯一层名称 |
| description | string | 否 | 描述 |

创建后自动生成 `id`（UUID）和 `salt`（32字符随机hex）。

## 实验 (Experiment)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| layer_id | UUID | 是 | 所属流量层 |
| key | string(128) | 是 | SDK 查询标识，全局唯一 |
| name | string(256) | 是 | 显示名称 |
| description | string | 否 | 描述 |
| bucket_start | int [0,9999] | 是 | 桶范围起始（含） |
| bucket_end | int [0,9999] | 是 | 桶范围结束（含） |
| groups | Group[] | 是 | 实验组列表 |

### 状态机

```
draft → running → paused → running (循环)
                → full_rollout → archived
```

## 组 (Group)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string(64) | 是 | 组名（如 control, treatment） |
| traffic_percentage | int [0,100] | 是 | 流量百分比（组内所有百分比之和应等于100） |
| config_json | JSON | 否 | 该组的功能配置参数 |

## 白名单 (Whitelist)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| group_id | UUID | 是 | 强制分入的组 |
| user_id | string(256) | 是 | 用户标识 |

## 桶空间说明

- 总桶空间：0-9999（共10000桶，精度0.01%）
- 每个层使用独立的 salt 进行哈希，保证层间独立
- 同一层内的实验占据不重叠的桶范围，保证互斥
- 示例：层内实验A占据 [0, 4999]，实验B占据 [5000, 7499]，[7500, 9999] 未分配

## 创建实验示例

```json
{
  "layer_id": "550e8400-e29b-41d4-a716-446655440000",
  "key": "homepage_cta_color",
  "name": "首页CTA按钮颜色测试",
  "description": "测试蓝色和绿色CTA按钮的转化率差异",
  "bucket_start": 0,
  "bucket_end": 9999,
  "groups": [
    {"name": "control", "traffic_percentage": 50, "config_json": {"color": "blue"}},
    {"name": "treatment", "traffic_percentage": 50, "config_json": {"color": "green"}}
  ]
}
```
