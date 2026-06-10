import asyncio
import uuid as uuid_module
import sqlite3

import pytest
import pytest_asyncio
from sqlalchemy import JSON, String, TypeDecorator, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.dialects.postgresql import UUID, JSONB
from httpx import AsyncClient, ASGITransport
import fakeredis.aioredis

from app.core.database import Base, get_db
from app.core.redis import get_redis
from app.main import app


# Register UUID adapter for SQLite
sqlite3.register_adapter(uuid_module.UUID, lambda u: str(u))


class StringUUID(TypeDecorator):
    """Store UUIDs as strings in SQLite, transparent conversion."""
    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return str(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return uuid_module.UUID(value) if not isinstance(value, uuid_module.UUID) else value
        return value


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Map PostgreSQL-specific types to SQLite-compatible types
for table in Base.metadata.tables.values():
    for column in table.columns:
        if isinstance(column.type, JSONB):
            column.type = JSON()
        elif isinstance(column.type, UUID):
            column.type = StringUUID()
    # Remove CHECK constraints (PG-specific syntax)
    table.constraints = {c for c in table.constraints if not hasattr(c, 'sqltext')}


engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


_fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)


async def override_get_db():
    async with TestingSessionLocal() as session:
        yield session


async def override_get_redis():
    yield _fake_redis


@pytest_asyncio.fixture(autouse=True)
async def clear_redis():
    yield
    await _fake_redis.flushall()


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_redis] = override_get_redis


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def layer_data():
    return {"name": f"test_layer_{uuid_module.uuid4().hex[:8]}", "description": "Test layer"}


@pytest.fixture
def experiment_data():
    return {
        "key": f"test_exp_{uuid_module.uuid4().hex[:8]}",
        "name": "Test Experiment",
        "description": "A test experiment",
        "bucket_start": 0,
        "bucket_end": 9999,
        "groups": [
            {"name": "control", "traffic_percentage": 50},
            {"name": "treatment", "traffic_percentage": 50},
        ],
    }
