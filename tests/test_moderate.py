import pytest


@pytest.mark.asyncio
async def test_safe_message(async_client, mock_ai):
    mock_ai["safe"] = True
    response = await async_client.post(
        "/moderate",
        json={"user_id": "user1", "message": "hello"},
        headers={"X-API-Key": "mod_live_testkey1234"},
    )
    assert response.status_code == 200
    assert response.json()["safe"] is True


@pytest.mark.asyncio
async def test_unsafe_message_strike1(async_client, mock_ai):
    mock_ai["safe"] = False
    mock_ai["reason"] = "hate speech"
    mock_ai["severity"] = "high"
    response = await async_client.post(
        "/moderate",
        json={"user_id": "user2", "message": "bad message"},
        headers={"X-API-Key": "mod_live_testkey1234"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["safe"] is False
    assert data["strike_count"] == 1
    assert data["flagged"] is False


@pytest.mark.asyncio
async def test_missing_api_key(async_client):
    response = await async_client.post("/moderate", json={"user_id": "u", "message": "m"})
    assert response.status_code == 422  # Header missing = validation error


@pytest.mark.asyncio
async def test_invalid_api_key(async_client):
    response = await async_client.post(
        "/moderate",
        json={"user_id": "u", "message": "m"},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 401
