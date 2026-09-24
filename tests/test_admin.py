import pytest


@pytest.mark.asyncio
async def test_violations_requires_admin(async_client):
    response = await async_client.get("/admin/violations")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_violations_wrong_secret(async_client):
    response = await async_client.get(
        "/admin/violations", headers={"X-Admin-Secret": "wrong"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_users_flagged_only(async_client):
    from app.config import get_settings

    settings = get_settings()
    response = await async_client.get(
        "/admin/users?flagged_only=true",
        headers={"X-Admin-Secret": settings.admin_secret},
    )
    assert response.status_code == 200
    assert response.json() == []
