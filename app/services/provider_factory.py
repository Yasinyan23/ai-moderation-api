"""Resolve the correct AI provider for a given ApiKey at request time."""
import logging
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.db import UserProvider
from app.services.ai import AIProvider
from app.services.claude import ClaudeProvider
from app.services.crypto import decrypt_key

logger = logging.getLogger(__name__)

DEFAULT_MODELS = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-1.5-flash",
}


async def get_active_provider(session: AsyncSession, user_id: uuid.UUID) -> Optional[UserProvider]:
    result = await session.execute(
        select(UserProvider).where(
            UserProvider.user_id == user_id,
            UserProvider.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def get_provider_for_key(user_id: Optional[uuid.UUID], session: AsyncSession) -> AIProvider:
    """Return the AI provider for a given user_id.

    Falls back to the environment-configured ClaudeProvider for legacy API keys
    (user_id is None) or if no provider is connected.
    """
    settings = get_settings()

    if user_id is None:
        logger.debug("Legacy API key (no user_id) — using environment ClaudeProvider")
        return ClaudeProvider()

    user_provider = await get_active_provider(session, user_id)
    if user_provider is None:
        logger.debug("No active provider for user %s — falling back to environment Claude", user_id)
        return ClaudeProvider()

    if not settings.fernet_secret:
        logger.warning("FERNET_SECRET not set — cannot decrypt provider key, falling back to Claude")
        return ClaudeProvider()

    raw_key = decrypt_key(user_provider.encrypted_key, settings.fernet_secret)

    match user_provider.provider:
        case "anthropic":
            return ClaudeProvider(api_key=raw_key, model=user_provider.model)
        case "openai":
            from app.services.openai import OpenAIProvider
            return OpenAIProvider(api_key=raw_key, model=user_provider.model)
        case "gemini":
            from app.services.gemini import GeminiProvider
            return GeminiProvider(api_key=raw_key, model=user_provider.model)
        case _:
            logger.error("Unknown provider %s for user %s", user_provider.provider, user_id)
            return ClaudeProvider()
