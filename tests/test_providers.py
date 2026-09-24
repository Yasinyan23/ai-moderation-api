"""Tests for /providers endpoints."""
import pytest
from cryptography.fernet import Fernet
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.main import app
from app.config import get_settings
from app.database import get_session
from app.models.db import Base, User
from app.services.jwt_service import create_access_token, hash_token
from app.models.db import Session as DbSession
from datetime import datetime, timedelta, timezone

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
TEST_FERNET = Fernet.generate_key().decode()


@pytest.fixture(scope="function")
async def provider_db():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    yield Session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(scope="function")
async def authenticated_client(provider_db, monkeypatch):
    """Client with a valid JWT for a verified user."""
    import bcrypt

    # Patch FERNET_SECRET so encryption works
    monkeypatch.setenv("FERNET_SECRET", TEST_FERNET)
    get_settings.cache_clear()

    async def override_session():
        async with provider_db() as session:
            yield session

    app.dependency_overrides[get_session] = override_session

    # Create a verified user directly in the DB
    async with provider_db() as s:
        user = User(
            email="provider_test@example.com",
            password_hash=bcrypt.hashpw(b"pass", bcrypt.gensalt()).decode(),
            is_verified=True,
            is_active=True,
        )
        s.add(user)
        await s.commit()
        await s.refresh(user)
        user_id = user.id
        user_email = user.email

    # Create a session for the user
    async with provider_db() as s:
        token = create_access_token(str(user_id), user_email)
        th = hash_token(token)
        db_session = DbSession(
            user_id=user_id,
            token_hash=th,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        s.add(db_session)
        await s.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, token

    app.dependency_overrides.clear()
    monkeypatch.delenv("FERNET_SECRET", raising=False)
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_list_providers_empty(authenticated_client):
    client, token = authenticated_client
    r = await client.get(
        "/providers/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_connect_provider_bad_key_prefix(authenticated_client):
    client, token = authenticated_client
    r = await client.post(
        "/providers/connect",
        json={"provider": "anthropic", "api_key": "wrong-prefix-key"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_connect_unsupported_provider(authenticated_client):
    client, token = authenticated_client
    r = await client.post(
        "/providers/connect",
        json={"provider": "cohere", "api_key": "somekey"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_connect_provider_no_fernet_secret(monkeypatch, provider_db):
    """Should return 500 when FERNET_SECRET is not configured."""
    import bcrypt

    monkeypatch.setenv("FERNET_SECRET", "")
    get_settings.cache_clear()

    async def override_session():
        async with provider_db() as session:
            yield session

    app.dependency_overrides[get_session] = override_session

    async with provider_db() as s:
        user = User(
            email="nofernet@example.com",
            password_hash=bcrypt.hashpw(b"x", bcrypt.gensalt()).decode(),
            is_verified=True,
            is_active=True,
        )
        s.add(user)
        await s.commit()
        await s.refresh(user)
        user_id = user.id
        user_email = user.email

    async with provider_db() as s:
        token = create_access_token(str(user_id), user_email)
        th = hash_token(token)
        sess = DbSession(
            user_id=user_id,
            token_hash=th,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        s.add(sess)
        await s.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/providers/connect",
            json={"provider": "anthropic", "api_key": "sk-ant-testkey"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 500

    app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_disconnect_nonexistent_provider(authenticated_client):
    client, token = authenticated_client
    r = await client.request(
        "DELETE",
        "/providers/disconnect",
        json={"provider": "openai", "model": "gpt-4o-mini"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_providers_require_auth(provider_db):
    async def override_session():
        async with provider_db() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/providers/me")
    assert r.status_code == 422  # missing Authorization header
    app.dependency_overrides.clear()
