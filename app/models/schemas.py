from uuid import UUID
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr


class ModerateRequest(BaseModel):
    user_id: str
    message: str


class ModerateResponse(BaseModel):
    safe: bool
    strike_count: Optional[int] = None
    warning: Optional[str] = None
    flagged: bool = False
    reason: Optional[str] = None
    severity: Optional[str] = None


class ViolationLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    app_id: UUID
    user_id: str
    message_text: str
    reason: str
    severity: str
    created_at: datetime


class UserViolationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    count: int
    flagged: bool
    flagged_at: Optional[datetime]


class ApiKeyCreateIn(BaseModel):
    app_name: str
    owner_email: str


class ApiKeyCreateOut(BaseModel):
    raw_key: str
    app_name: str
    owner_email: str


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    app_name: str
    owner_email: str
    created_at: datetime
    is_active: bool


class ApiKeyInfoOut(BaseModel):
    app_name: str
    owner_email: str


# ---------------------------------------------------------------------------
# Auth schemas
# ---------------------------------------------------------------------------

class RegisterIn(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = None


class VerifyOtpIn(BaseModel):
    email: str
    otp: str


class LoginIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: Optional[str]
    is_verified: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Provider schemas
# ---------------------------------------------------------------------------

class ProviderConnectIn(BaseModel):
    provider: str          # anthropic | openai | gemini
    api_key: str
    model: Optional[str] = None


class ProviderSwitchModelIn(BaseModel):
    provider: str
    model: str


class ProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider: str
    model: str
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime]
