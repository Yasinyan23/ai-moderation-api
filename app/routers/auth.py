"""Auth router — register, verify OTP, login, logout."""
import logging
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_session
from app.models.db import Session as DbSession, User
from app.models.schemas import LoginIn, RegisterIn, TokenOut, VerifyOtpIn
from app.services.email import generate_otp, send_otp_email
from app.services.jwt_service import create_access_token, decode_access_token, hash_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth")

_OTP_TTL_MINUTES = 10


@router.post("/register", status_code=201)
async def register(
    body: RegisterIn,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Create a new user account and send an OTP verification email."""
    existing = await session.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    otp = generate_otp()
    otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=_OTP_TTL_MINUTES)

    user = User(
        email=body.email,
        password_hash=password_hash,
        full_name=body.full_name,
        otp_code=otp,
        otp_expires_at=otp_expires_at,
    )
    session.add(user)
    await session.commit()

    try:
        await send_otp_email(body.email, otp)
    except Exception:
        logger.warning("OTP email delivery failed for %s — user can request resend", body.email)

    return {"message": "Check your email for your verification code"}


@router.post("/verify", response_model=TokenOut)
async def verify_otp(
    body: VerifyOtpIn,
    session: AsyncSession = Depends(get_session),
) -> TokenOut:
    """Verify OTP and return a JWT access token."""
    result = await session.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_verified:
        raise HTTPException(status_code=400, detail="Email already verified — please login")

    now = datetime.now(timezone.utc)
    if not user.otp_code or user.otp_code != body.otp:
        raise HTTPException(status_code=400, detail="Invalid verification code")

    otp_expires = user.otp_expires_at
    if otp_expires and otp_expires.tzinfo is None:
        otp_expires = otp_expires.replace(tzinfo=timezone.utc)
    if not otp_expires or now > otp_expires:
        raise HTTPException(status_code=400, detail="Verification code has expired")

    user.is_verified = True
    user.otp_code = None
    user.otp_expires_at = None

    token = create_access_token(str(user.id), user.email)
    token_hash = hash_token(token)
    settings = get_settings()
    db_session = DbSession(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=now + timedelta(days=settings.jwt_expiry_days),
    )
    session.add(db_session)
    await session.commit()

    logger.info("User %s verified and logged in", user.email)
    return TokenOut(access_token=token)


@router.post("/login", response_model=TokenOut)
async def login(
    body: LoginIn,
    session: AsyncSession = Depends(get_session),
) -> TokenOut:
    """Authenticate and return a JWT access token."""
    result = await session.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not bcrypt.checkpw(body.password.encode(), user.password_hash.encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Email not verified — check your inbox")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    now = datetime.now(timezone.utc)
    token = create_access_token(str(user.id), user.email)
    token_hash = hash_token(token)
    settings = get_settings()
    db_session = DbSession(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=now + timedelta(days=settings.jwt_expiry_days),
    )
    session.add(db_session)
    await session.commit()

    logger.info("User %s logged in", user.email)
    return TokenOut(access_token=token)


@router.post("/logout")
async def logout(
    authorization: str = Header(..., alias="Authorization"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Revoke the current session token."""
    token = authorization.removeprefix("Bearer ").strip()
    token_hash = hash_token(token)

    result = await session.execute(
        select(DbSession).where(DbSession.token_hash == token_hash)
    )
    db_session = result.scalar_one_or_none()
    if not db_session:
        raise HTTPException(status_code=401, detail="Session not found")

    db_session.is_revoked = True
    await session.commit()

    logger.info("Session revoked for token hash %s…", token_hash[:12])
    return {"message": "Logged out"}
