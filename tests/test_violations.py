import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.models.db import Base, ApiKey, UserViolation
from app.services.violations import get_or_create_violation, increment_strike, is_flagged

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    app_id = uuid.uuid4()
    async with Session() as s:
        async with s.begin():
            key = ApiKey(id=app_id, key_hash="x", app_name="t", owner_email="t@t.com")
            s.add(key)
    async with Session() as s:
        yield s, app_id
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_increment_strike(session):
    s, app_id = session
    async with s.begin():
        v = await get_or_create_violation(s, app_id, "user1")
        v = await increment_strike(s, v)
        assert v.count == 1
        assert v.flagged is False


@pytest.mark.asyncio
async def test_flagged_at_5(session):
    s, app_id = session
    async with s.begin():
        v = await get_or_create_violation(s, app_id, "user2")
        for _ in range(5):
            v = await increment_strike(s, v)
        assert v.count == 5
        assert v.flagged is True
        assert v.flagged_at is not None


@pytest.mark.asyncio
async def test_is_flagged(session):
    s, app_id = session
    result = await is_flagged(s, app_id, "user3")
    assert result is False
