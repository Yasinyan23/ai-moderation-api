import pytest
import pytest_asyncio
import bcrypt
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.main import app
from app.database import get_session
from app.models.db import Base, ApiKey

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def test_db():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    yield Session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_api_key(test_db):
    raw = "mod_live_testkey1234"
    hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
    async with test_db() as session:
        async with session.begin():
            key = ApiKey(key_hash=hashed, app_name="test-app", owner_email="test@example.com")
            session.add(key)
    return raw, hashed


@pytest.fixture
def mock_ai(monkeypatch):
    from app.services import claude
    from app.services.ai import ModerationResult

    results = {"safe": True, "reason": None, "severity": None}

    async def fake_moderate(self, message: str) -> ModerationResult:
        return ModerationResult(**results)

    monkeypatch.setattr(claude.ClaudeProvider, "moderate", fake_moderate)
    return results


@pytest_asyncio.fixture(scope="function")
async def async_client(test_db, test_api_key, mock_ai):
    async def override_session():
        async with test_db() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
