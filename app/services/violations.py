import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import UserViolation, ViolationLog


async def get_or_create_violation(
    session: AsyncSession, app_id: uuid.UUID, user_id: str
) -> UserViolation:
    result = await session.execute(
        select(UserViolation).where(
            UserViolation.app_id == app_id, UserViolation.user_id == user_id
        )
    )
    violation = result.scalar_one_or_none()
    if violation is None:
        violation = UserViolation(app_id=app_id, user_id=user_id)
        session.add(violation)
        await session.flush()
    return violation


async def increment_strike(
    session: AsyncSession, violation: UserViolation
) -> UserViolation:
    violation.count += 1
    if violation.count >= 5:
        violation.flagged = True
        violation.flagged_at = datetime.now(timezone.utc)
    await session.flush()
    return violation


async def log_violation(
    session: AsyncSession,
    app_id: uuid.UUID,
    user_id: str,
    message: str,
    reason: str,
    severity: str,
) -> None:
    log = ViolationLog(
        app_id=app_id,
        user_id=user_id,
        message_text=message,
        reason=reason,
        severity=severity,
    )
    session.add(log)
    await session.flush()


async def is_flagged(
    session: AsyncSession, app_id: uuid.UUID, user_id: str
) -> bool:
    result = await session.execute(
        select(UserViolation.flagged).where(
            UserViolation.app_id == app_id, UserViolation.user_id == user_id
        )
    )
    row = result.scalar_one_or_none()
    return bool(row) if row is not None else False
