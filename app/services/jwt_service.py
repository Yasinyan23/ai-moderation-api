"""Add jti (JWT ID) for uniqueness; include in token hash."""
import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt

from app.config import get_settings

logger = logging.getLogger(__name__)


def create_access_token(user_id: str, email: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=settings.jwt_expiry_days)
    payload = {
        "sub": str(user_id),
        "email": email,
        "jti": str(uuid.uuid4()),  # unique per token so each login gets a unique hash
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> Optional[dict]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError as e:
        logger.debug("JWT decode failed: %s", e)
        return None


def hash_token(token: str) -> str:
    """SHA-256 hash of the token for server-side revocation storage."""
    return hashlib.sha256(token.encode()).hexdigest()
