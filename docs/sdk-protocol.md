# SDK ↔ Backend 接口协议

## 1. 配置拉取

**GET** `/api/v1/sdk/config`

### 请求头

| Header | 说明 |
|--------|------|
| If-None-Match | 上次响应的 ETag 值（可选） |

### 响应

- **200 OK**：返回完整配置 JSON，附 `ETag` 响应头
- **304 Not Modified**：配置未变化，无响应体

### 响应体格式

```json
{
  "layers": [
    {
      "id": "uuid-string",
      "name": "homepage_tests",
      "salt": "a1b2c3d4e5f67890...",
      "experiments": [
        {
          "id": "uuid-string",
          "key": "homepage_cta",
          "status": "running",
          "bucket_start": 0,
          "bucket_end": 9999,
          "groups": [
            {"id": "uuid", "name": "control", "traffic_percentage": 50, "config_json": {}},
            {"id": "uuid", "name": "treatment", "traffic_percentage": 50, "config_json": {}}
          ],
          "whitelist": {"user_123": "treatment"}
        }
      ]
    }
  ],
  "version": "1"
}
```

### SDK 行为

- 启动时立即拉取一次
- 之后每 `poll_interval` 秒（默认30秒）轮询
- 使用 ETag 避免重复传输
- 服务端不可达时保持本地缓存配置
- 配置变更后最迟 `poll_interval` 秒内生效

---

## 2. 事件上报

**POST** `/api/v1/sdk/events`

### 请求体

```json
{
  "events": [
    {
      "experiment_key": "homepage_cta",
      "group_name": "treatment",
      "user_id": "user_456",
      "event_name": "button_clicked",
      "metadata": {"page": "home", "position": "top"},
      "event_time": "2026-06-08T12:00:00+08:00"
    }
  ]
}
```

### 响应

```json
{"accepted": 5}
```

### SDK 行为

- 每次 `track()` 调用先写入本地 WAL 文件（JSONL 格式）
- 后台线程每 `flush_interval` 秒批量发送
- 单批次最大 500 条事件
- 发送成功后清除 WAL 中对应条目
- 发送失败（网络错误/5xx）保留在缓冲区，下次重试
- 进程启动时自动恢复 WAL 中的未发送事件

### 零丢失保证

```
track() → append WAL → buffer
             ↓
     flush timer → HTTP POST → success → clear WAL
                             → failure → retain, retry next cycle
```

---

## 3. 分流算法（SDK 本地执行）

```python
import hashlib

def get_bucket(user_id: str, salt: str) -> int:
    """将用户映射到 [0, 9999] 的桶。"""
    raw = f"{user_id}{salt}".encode("utf-8")
    digest = hashlib.md5(raw).hexdigest()
    return int(digest[:8], 16) % 10000
```

### 决策流程

1. 查找 `experiment_key` 对应的实验和层
2. 检查白名单：如果 user_id 在白名单中，直接返回指定组
3. 计算 `bucket = get_bucket(user_id, layer.salt)`
4. 检查 bucket 是否在实验的 [bucket_start, bucket_end] 范围内
5. 如果不在范围内，返回 None（用户不参与该实验）
6. 将 bucket 映射到组：按 traffic_percentage 依次分配

---

## 4. SDK 公共接口

```python
from splitlab import SplitLabClient

# 初始化
client = SplitLabClient(
    api_url="http://localhost:8000",
    api_key="sk-xxx",           # 可选
    poll_interval=30,           # 配置轮询间隔（秒）
    flush_interval=5,           # 事件刷新间隔（秒）
    buffer_size=100,            # 事件缓冲区大小
    persistence_path="events.jsonl",  # WAL 文件路径
)

# 获取用户分组（纯本地计算，无网络调用）
variant = client.get_variant(user_id="user_123", experiment_key="homepage_cta")
# 返回: "control" | "treatment" | None

# 上报转化事件
client.track(
    user_id="user_123",
    event_name="purchase",
    experiment_key="homepage_cta",
    group_name="treatment",
    metadata={"amount": 99.9},
)

# 优雅关闭（刷新剩余事件）
client.close()
```
