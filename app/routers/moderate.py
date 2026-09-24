import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.middleware.auth import require_api_key
from app.models.db import ApiKey
from app.models.schemas import ApiKeyInfoOut, ModerateRequest, ModerateResponse
from app.services.provider_factory import get_provider_for_key
from app.services.violations import (
    get_or_create_violation,
    increment_strike,
    is_flagged,
    log_violation,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/keys/me", response_model=ApiKeyInfoOut)
async def get_key_info(
    api_key: ApiKey = Depends(require_api_key),
) -> ApiKeyInfoOut:
    return ApiKeyInfoOut(app_name=api_key.app_name, owner_email=api_key.owner_email)


@router.post("/moderate", response_model=ModerateResponse)
async def moderate(
    body: ModerateRequest,
    api_key: ApiKey = Depends(require_api_key),
    session: AsyncSession = Depends(get_session),
) -> ModerateResponse:
    try:
        if await is_flagged(session, api_key.id, body.user_id):
            return ModerateResponse(
                safe=False,
                flagged=True,
                warning="Your account has been restricted. Contact support.",
            )

        provider = await get_provider_for_key(api_key.user_id, session)
        result = await provider.moderate(body.message)
        if result.safe:
            return ModerateResponse(safe=True)

        violation = await get_or_create_violation(session, api_key.id, body.user_id)
        violation = await increment_strike(session, violation)
        await log_violation(
            session,
            api_key.id,
            body.user_id,
            body.message,
            result.reason or "",
            result.severity or "low",
        )
        await session.commit()

        if violation.flagged:
            return ModerateResponse(
                safe=False,
                flagged=True,
                strike_count=violation.count,
                warning="Your account has been permanently restricted.",
            )

        return ModerateResponse(
            safe=False,
            flagged=False,
            strike_count=violation.count,
            reason=result.reason,
            severity=result.severity,
            warning=f"Warning {violation.count}/5: {result.reason}",
        )
    except Exception:
        await session.rollback()
        raise
