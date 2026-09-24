import secrets
import uuid
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.middleware.auth import require_admin
from app.models.db import ApiKey, UserViolation, ViolationLog
from app.models.schemas import (
    ApiKeyCreateIn,
    ApiKeyCreateOut,
    ApiKeyOut,
    UserViolationOut,
    ViolationLogOut,
)

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


@router.get("/violations", response_model=list[ViolationLogOut])
async def get_violations(
    app_id: Optional[uuid.UUID] = Query(None),
    user_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[ViolationLogOut]:
    q = select(ViolationLog)
    if app_id:
        q = q.where(ViolationLog.app_id == app_id)
    if user_id:
        q = q.where(ViolationLog.user_id == user_id)
    q = q.limit(limit).offset(offset)
    result = await session.execute(q)
    return [ViolationLogOut.model_validate(row) for row in result.scalars()]


@router.get("/users", response_model=list[UserViolationOut])
async def get_users(
    app_id: Optional[uuid.UUID] = Query(None),
    flagged_only: bool = Query(False),
    session: AsyncSession = Depends(get_session),
) -> list[UserViolationOut]:
    q = select(UserViolation)
    if app_id:
        q = q.where(UserViolation.app_id == app_id)
    if flagged_only:
        q = q.where(UserViolation.flagged == True)
    result = await session.execute(q)
    return [UserViolationOut.model_validate(row) for row in result.scalars()]


@router.patch("/users/{user_id}/unban")
async def unban_user(
    user_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(
        select(UserViolation).where(UserViolation.user_id == user_id)
    )
    violations = result.scalars().all()
    if not violations:
        raise HTTPException(status_code=404, detail="User not found")
    for v in violations:
        v.count = 0
        v.flagged = False
        v.flagged_at = None
    await session.commit()
    return {"status": "unbanned", "user_id": user_id}


@router.post("/keys", response_model=ApiKeyCreateOut)
async def create_key(
    body: ApiKeyCreateIn,
    session: AsyncSession = Depends(get_session),
) -> ApiKeyCreateOut:
    raw_key = "mod_live_" + secrets.token_urlsafe(16)
    key_hash = bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode()
    api_key = ApiKey(
        key_hash=key_hash,
        app_name=body.app_name,
        owner_email=body.owner_email,
    )
    session.add(api_key)
    await session.commit()
    return ApiKeyCreateOut(
        raw_key=raw_key,
        app_name=body.app_name,
        owner_email=body.owner_email,
    )


@router.get("/keys", response_model=list[ApiKeyOut])
async def list_keys(
    session: AsyncSession = Depends(get_session),
) -> list[ApiKeyOut]:
    result = await session.execute(select(ApiKey))
    return [ApiKeyOut.model_validate(row) for row in result.scalars()]


@router.patch("/keys/{app_name}/revoke")
async def revoke_key(
    app_name: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(
        select(ApiKey).where(ApiKey.app_name == app_name, ApiKey.is_active.is_(True))
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="Active key not found for that app name")
    key.is_active = False
    await session.commit()
    return {"status": "revoked", "app_name": app_name}
