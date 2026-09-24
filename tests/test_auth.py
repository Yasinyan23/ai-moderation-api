"""Tests for /auth endpoints."""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.main import app
from app.database import get_session
from app.models.db import Base

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="function")
async def auth_db():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    yield Session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(scope="function")
async def auth_client(auth_db):
    async def override_session():
        async with auth_db() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_register_returns_message(auth_client):
    r = await auth_client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "secret123"},
    )
    assert r.status_code == 201
    assert "message" in r.json()


@pytest.mark.asyncio
async def test_register_duplicate_email(auth_client):
    await auth_client.post(
        "/auth/register",
        json={"email": "dup@example.com", "password": "pass"},
    )
    r = await auth_client.post(
        "/auth/register",
        json={"email": "dup@example.com", "password": "pass"},
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_login_unverified_user(auth_client):
    await auth_client.post(
        "/auth/register",
        json={"email": "bob@example.com", "password": "mypass"},
    )
    r = await auth_client.post(
        "/auth/login",
        json={"email": "bob@example.com", "password": "mypass"},
    )
    assert r.status_code == 403
    assert "not verified" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_login_wrong_password(auth_client):
    await auth_client.post(
        "/auth/register",
        json={"email": "carol@example.com", "password": "correct"},
    )
    r = await auth_client.post(
        "/auth/login",
        json={"email": "carol@example.com", "password": "wrong"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_verify_and_login_flow(auth_db, auth_client):
    """Full register → OTP verify → login flow."""
    from sqlalchemy import select
    from app.models.db import User

    await auth_client.post(
        "/auth/register",
        json={"email": "dave@example.com", "password": "pass123", "full_name": "Dave"},
    )

    # Fetch the OTP directly from the DB (simulates email delivery in tests)
    async with auth_db() as s:
        result = await s.execute(select(User).where(User.email == "dave@example.com"))
        user = result.scalar_one()
        otp = user.otp_code

    assert otp is not None

    # Verify with correct OTP
    r = await auth_client.post(
        "/auth/verify",
        json={"email": "dave@example.com", "otp": otp},
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    assert token

    # Can now login
    r2 = await auth_client.post(
        "/auth/login",
        json={"email": "dave@example.com", "password": "pass123"},
    )
    assert r2.status_code == 200
    assert r2.json()["access_token"]


@pytest.mark.asyncio
async def test_verify_wrong_otp(auth_client):
    await auth_client.post(
        "/auth/register",
        json={"email": "eve@example.com", "password": "pass"},
    )
    r = await auth_client.post(
        "/auth/verify",
        json={"email": "eve@example.com", "otp": "000000"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_logout_revokes_session(auth_db, auth_client):
    """Logout should make subsequent requests with the same token fail."""
    from sqlalchemy import select
    from app.models.db import User

    await auth_client.post(
        "/auth/register",
        json={"email": "frank@example.com", "password": "pw"},
    )
    async with auth_db() as s:
        result = await s.execute(select(User).where(User.email == "frank@example.com"))
        otp = result.scalar_one().otp_code

    r = await auth_client.post(
        "/auth/verify",
        json={"email": "frank@example.com", "otp": otp},
    )
    token = r.json()["access_token"]

    # Logout
    r2 = await auth_client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200

    # Using the same token after logout should fail
    r3 = await auth_client.get(
        "/providers/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r3.status_code == 401
