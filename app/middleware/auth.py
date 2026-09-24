import logging

import bcrypt
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_session
from app.models.db import ApiKey, Session as DbSession, User
from app.services.jwt_service import decode_access_token, hash_token

logger = logging.getLogger(__name__)


async def require_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
    session: AsyncSession = Depends(get_session),
) -> ApiKey:
    result = await session.execute(select(ApiKey).where(ApiKey.is_active == True))
    for row in result.scalars():
        if bcrypt.checkpw(x_api_key.encode(), row.key_hash.encode()):
            if not row.is_active:
                raise HTTPException(status_code=403, detail="API key is inactive")
            return row
    raise HTTPException(status_code=401, detail="Invalid or missing API key")


async def require_admin(
    x_admin_secret: str = Header(..., alias="X-Admin-Secret"),
) -> None:
    if x_admin_secret != get_settings().admin_secret:
        raise HTTPException(status_code=401, detail="Invalid admin secret")


async def require_jwt(
    authorization: str = Header(..., alias="Authorization"),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Validate a Bearer JWT and return the authenticated User.

    Checks that the token is not expired and that the session has not been
    revoked server-side.
    """
    token = authorization.removeprefix("Bearer ").strip()
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    token_hash = hash_token(token)
    sess_result = await session.execute(
        select(DbSession).where(DbSession.token_hash == token_hash)
    )
    db_session = sess_result.scalar_one_or_none()
    if not db_session or db_session.is_revoked:
        raise HTTPException(status_code=401, detail="Session revoked or not found")

    user_result = await session.execute(
        select(User).where(User.id == db_session.user_id)
    )
    user = user_result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user
