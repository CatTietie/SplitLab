# SDK Authentication & Multi-Environment Config Isolation Specification

## 1. 背景与目标

当前 SplitLab 的 SDK 端点（/api/v1/sdk/config 和 /api/v1/sdk/events）是完全开放的——任何人知道地址就能拉取配置和注入事件。SDK client 代码里有个 api_key 参数，但后端完全没有校验。这意味着：竞争对手可以拉取你的实验配置了解产品策略，恶意用户可以注入虚假事件污染实验数据，而且开发和生产环境共用同一套配置，无法隔离测试。

本扩展目标：为 SplitLab 引入 SDK 鉴权体系与多环境配置隔离，确保只有合法 SDK 能访问配置和上报事件，且开发、预发、生产环境的数据完全隔离。

## 2. 需求清单

### 2.1 SDK 鉴权

| 编号 | 需求 | 说明 |
|------|------|------|
| SA-1 | API Key 模型 | 新增 ApiKey 表，每个 key 关联一个环境（environment），包含 key_hash（SHA256）、name、environment_id、permissions（config_read + events_write）、is_active、created_by |
| SA-2 | Key 生成 | 后端生成 API Key 时输出明文 key 仅一次（格式 sk_live_xxxx 或 sk_test_xxxx），数据库仅存储 SHA256 哈希 |
| SA-3 | Key 前缀约定 | sk_live_ 前缀表示生产环境，sk_test_ 前缀表示测试/开发环境 |
| SA-4 | 请求鉴权 | SDK 请求必须携带 Authorization: Bearer sk_xxx 头，后端中间件校验 key 有效性、权限匹配、所属环境 |
| SA-5 | 无 Key 拒绝 | 不携带 Authorization 头的 SDK 请求返回 HTTP 401 |
| SA-6 | Key 失效 | API Key 可被禁用（is_active=false），禁用后该 Key 的所有请求返回 401 |
| SA-7 | Key 管理 API | 新增 /api/v1/api-keys CRUD 端点：创建（返回明文 key 仅一次）、列表（仅展示 key 前缀+名称）、禁用/启用、删除 |
| SA-8 | Key 权限管理 | 创建 API Key 时指定 permissions：config_read（允许拉取配置）、events_write（允许上报事件）。缺少对应权限时返回 HTTP 403 |

### 2.2 多环境隔离

| 编号 | 需求 | 说明 |
|------|------|------|
| ME-1 | 环境模型 | 新增 Environment 表，包含 name（production/staging/development）、description、org_id、is_default |
| ME-2 | 环境数据隔离 | Experiment、ExperimentLayer、Event 等表新增 environment_id 列，所有查询自动按 environment_id 过滤 |
| ME-3 | 环境初始化 | 系统启动时自动创建 "production" 默认环境，现有数据迁移到 production 环境 |
| ME-4 | 环境切换 | 前端顶部导航新增环境切换下拉框，切换后所有页面数据刷新为对应环境 |
| ME-5 | SDK 配置按环境分发 | SDK config 接口根据请求 API Key 的 environment_id 返回对应环境的配置，不同环境的配置完全独立 |
| ME-6 | 环境配置缓存隔离 | Redis 配置缓存 key 包含 environment_id：sdk:config:{env_id}、sdk:config:etag:{env_id} |
| ME-7 | 审计日志环境标记 | 审计日志记录 environment_id，方便按环境查看操作历史 |

### 2.3 Coordinator 环境感知

| 编号 | 需求 | 说明 |
|------|------|------|
| CE-1 | 按环境重建缓存 | Coordinator 重建配置缓存时，按 environment_id 分别重建 |
| CE-2 | 按环境清除缓存 | 后端实例宕机时，仅清除对应环境的缓存 |

### 2.4 前端交互

| 编号 | 需求 | 说明 |
|------|------|------|
| FE-1 | 环境切换器 | 顶部导航栏右侧新增环境切换下拉，显示当前环境标签（production=红/staging=黄/development=绿） |
| FE-2 | API Key 管理页 | 新增"API Keys"管理页面：创建 key 弹窗（选择环境+权限）、key 列表（展示前8位+名称+环境+权限+状态）、禁用/删除操作 |
| FE-3 | Key 创建一次性展示 | 创建成功后弹窗展示完整 key，提示"请立即复制，关闭后不可再查看" |
| FE-4 | 环境管理页 | 管理员可创建/编辑/删除环境（production 不可删除），每个环境显示关联的实验数量和 API Key 数量 |

## 3. 现有架构约束

### 3.1 必须保持的约束

- **SDK config ETag/304 机制不变**
- **SDK 事件批量上报格式不变**
- **桶空间分流模型不变**
- **实验状态机不变**
- **白名单机制不变**

### 3.2 不允许的改动

- 不修改 SDK 分流算法（splitter.py）
- 不引入 OAuth2 等复杂鉴权协议
- 不修改 MQTT topic 结构
- 不将鉴权逻辑放在 SDK 端（鉴权仅在后端中间件执行）

## 4. 技术栈约束

- 后端：Python 3.11+ / FastAPI / asyncio
- Key 存储：PostgreSQL / SQLAlchemy
- Key 校验：SHA256 哈希比对 + Redis 缓存活跃 key
- 环境隔离：PostgreSQL 列级过滤 + Redis key 命名空间
- 前端：React / Ant Design
- SDK：仅需在请求头中添加 Authorization

## 5. 数据模型变更

### 5.1 新增 Environment 表

```python
class Environment(Base):
    __tablename__ = "environments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
```

### 5.2 新增 ApiKey 表

```python
class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(12), nullable=False)  # "sk_live_" / "sk_test_"
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA256
    environment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("environments.id"))
    permissions: Mapped[dict] = mapped_column(JSONB, default={"config_read": True, "events_write": True})
    is_active: Mapped[bool] = mapped_column(default=True)
    last_used_at: Mapped[datetime | None] = mapped_column()
    created_by: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
```

### 5.3 现有表新增 environment_id 列

| 表 | 新增列 | 默认值 | 说明 |
|------|--------|--------|------|
| experiments | environment_id | (迁移时设为 production env id) | 环境归属 |
| experiment_layers | environment_id | (迁移时设为 production env id) | 环境归属 |
| events | environment_id | (迁移时设为 production env id) | 环境归属 |

## 6. 鉴权中间件设计

### 6.1 鉴权流程

```
SDK 请求到达 (Authorization: Bearer sk_live_abc123)
    │
    ├─ 提取 Bearer token
    │   ├─ 无 token → 401
    │
    ├─ 计算 SHA256(token)
    │
    ├─ 查询 Redis 缓存 (api_key:hash:{sha256})
    │   ├─ 命中 → 获取 {environment_id, permissions, is_active}
    │   └─ 未命中 → 查询 PostgreSQL → 缓存到 Redis (TTL=300s)
    │
    ├─ 检查 is_active
    │   └─ False → 401
    │
    ├─ 检查 permissions
    │   ├─ GET /sdk/config → 需要 config_read
    │   ├─ POST /sdk/events → 需要 events_write
    │   └─ 权限不足 → 403
    │
    └─ 注入 request.state.environment_id 和 request.state.api_key_id
```

### 6.2 config_service 环境感知

```python
async def get_cached_config(redis_client, db, environment_id):
    cache_key = f"sdk:config:{environment_id}"
    etag_key = f"sdk:config:etag:{environment_id}"
    cached = await redis_client.get(cache_key)
    etag = await redis_client.get(etag_key)
    if cached and etag:
        return cached, etag
    # 从 DB 查询该环境的配置并缓存
    config = await build_sdk_config(db, environment_id)
    ...
```

## 7. 边界条件与异常处理

| 场景 | 处理策略 |
|------|----------|
| API Key 被泄露 | 管理员立即禁用该 key，创建新 key 替换 |
| Key 的 environment_id 不存在 | 鉴权失败，返回 401 |
| 同一 Key 同时用于 config 和 events | 只要 permissions 都包含即可 |
| Key 缓存与 DB 不一致 | 缓存 TTL=300s，禁用 Key 时主动删除缓存 |
| 环境删除时有活跃 Key | 拒绝删除环境，需先禁用或删除关联 Key |
| 数据迁移时 environment_id 为 Null | 迁移脚本将现有数据全部分配到 production 环境 |
| SDK 未携带 Authorization | 返回 401，错误信息 "Missing Authorization header" |
| 前端 API 与 SDK API 鉴权分离 | 前端管理 API 使用未来扩展的用户登录体系，SDK API 使用 API Key |
| 生产环境被误删 | is_default=True 的环境不可删除 |

## 8. 验收标准

### 8.1 功能验收

- 不携带 API Key 的 SDK 请求返回 401
- 携带有效 API Key 的请求正常访问，环境隔离生效
- sk_live_ 前缀的 Key 只能访问 production 环境的配置和事件
- sk_test_ 前缀的 Key 只能访问 development/staging 环境
- 缺少 config_read 权限的 Key 请求 /sdk/config 返回 403
- 缺少 events_write 权限的 Key 请求 /sdk/events 返回 403
- Key 禁用后所有请求立即返回 401
- 前端可创建/查看/禁用 API Key，创建时明文 key 仅展示一次

### 8.2 性能验收

- 鉴权中间件延迟不超过 5ms（Redis 缓存命中时）
- 缓存未命中时鉴权延迟不超过 50ms
- 环境过滤不影响查询性能（environment_id 列建立索引）
- 配置缓存按环境隔离，不增加缓存体积

### 8.3 测试要求

- 单元测试：Key 生成与哈希校验、权限匹配、环境隔离过滤
- 集成测试：创建 Key → SDK 请求带 Key → 成功访问 → 禁用 Key → 请求失败
- 隔离测试：development 环境的实验不影响 production 环境的统计
- 降级测试：Redis 不可用时鉴权走 DB 查询，不阻塞 SDK 请求