"""Providers router — connect, disconnect, list, and switch-model for AI providers."""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_session
from app.middleware.auth import require_jwt
from app.models.db import User, UserProvider
from app.models.schemas import ProviderConnectIn, ProviderOut, ProviderSwitchModelIn
from app.services.crypto import decrypt_key, encrypt_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/providers", dependencies=[Depends(require_jwt)])

SUPPORTED_PROVIDERS = {"anthropic", "openai", "gemini"}
DEFAULT_MODELS = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-1.5-flash",
}
KEY_PREFIXES = {
    "anthropic": "sk-ant-",
    "openai": "sk-",
    "gemini": "AIza",
}


def _validate_key_format(provider: str, api_key: str) -> None:
    """Raise if the key doesn't match the expected prefix for the provider."""
    prefix = KEY_PREFIXES.get(provider)
    if prefix and not api_key.startswith(prefix):
        raise HTTPException(
            status_code=422,
            detail=f"API key for {provider} should start with '{prefix}'",
        )


async def _live_validate_key(provider: str, api_key: str, model: str) -> None:
    """Make a minimal live call to verify the key is valid."""
    try:
        if provider == "anthropic":
            from app.services.claude import ClaudeProvider
            p = ClaudeProvider(api_key=api_key, model=model)
            await p.moderate("test")
        elif provider == "openai":
            from app.services.openai import OpenAIProvider
            p = OpenAIProvider(api_key=api_key, model=model)
            await p.moderate("test")
        elif provider == "gemini":
            from app.services.gemini import GeminiProvider
            p = GeminiProvider(api_key=api_key, model=model)
            await p.moderate("test")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Provider key validation failed for %s: %s", provider, e)
        raise HTTPException(status_code=422, detail=f"Key validation failed: {e}")


@router.post("/connect", response_model=ProviderOut, status_code=201)
async def connect_provider(
    body: ProviderConnectIn,
    current_user: User = Depends(require_jwt),
    session: AsyncSession = Depends(get_session),
) -> ProviderOut:
    """Validate and store a provider API key for the authenticated user."""
    if body.provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported provider. Choose from: {', '.join(SUPPORTED_PROVIDERS)}",
        )

    settings = get_settings()
    if not settings.fernet_secret:
        raise HTTPException(
            status_code=500,
            detail="FERNET_SECRET not configured on server",
        )

    _validate_key_format(body.provider, body.api_key)
    model = body.model or DEFAULT_MODELS[body.provider]
    await _live_validate_key(body.provider, body.api_key, model)

    # Deactivate any existing provider of this type
    existing = await session.execute(
        select(UserProvider).where(
            UserProvider.user_id == current_user.id,
            UserProvider.provider == body.provider,
        )
    )
    for old in existing.scalars():
        old.is_active = False

    encrypted = encrypt_key(body.api_key, settings.fernet_secret)
    provider = UserProvider(
        user_id=current_user.id,
        provider=body.provider,
        encrypted_key=encrypted,
        model=model,
    )
    session.add(provider)
    await session.commit()
    await session.refresh(provider)

    logger.info("User %s connected provider %s (model=%s)", current_user.email, body.provider, model)
    return ProviderOut.model_validate(provider)


@router.delete("/disconnect")
async def disconnect_provider(
    body: ProviderSwitchModelIn,
    current_user: User = Depends(require_jwt),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Mark a provider as inactive (does not delete the record)."""
    result = await session.execute(
        select(UserProvider).where(
            UserProvider.user_id == current_user.id,
            UserProvider.provider == body.provider,
            UserProvider.is_active.is_(True),
        )
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Active provider not found")

    provider.is_active = False
    await session.commit()

    logger.info("User %s disconnected provider %s", current_user.email, body.provider)
    return {"status": "disconnected", "provider": body.provider}


@router.get("/me", response_model=list[ProviderOut])
async def list_providers(
    current_user: User = Depends(require_jwt),
    session: AsyncSession = Depends(get_session),
) -> list[ProviderOut]:
    """Return all connected (active) providers — never exposes raw keys."""
    result = await session.execute(
        select(UserProvider).where(
            UserProvider.user_id == current_user.id,
            UserProvider.is_active.is_(True),
        )
    )
    return [ProviderOut.model_validate(p) for p in result.scalars()]


@router.patch("/switch-model", response_model=ProviderOut)
async def switch_model(
    body: ProviderSwitchModelIn,
    current_user: User = Depends(require_jwt),
    session: AsyncSession = Depends(get_session),
) -> ProviderOut:
    """Update the model used for a connected provider."""
    result = await session.execute(
        select(UserProvider).where(
            UserProvider.user_id == current_user.id,
            UserProvider.provider == body.provider,
            UserProvider.is_active.is_(True),
        )
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Active provider not found")

    provider.model = body.model
    await session.commit()
    await session.refresh(provider)

    logger.info("User %s switched %s model to %s", current_user.email, body.provider, body.model)
    return ProviderOut.model_validate(provider)
