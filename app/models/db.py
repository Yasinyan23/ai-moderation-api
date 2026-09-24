import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, SmallInteger, Text, DateTime, String, UniqueConstraint, func, text
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class GUID(TypeDecorator):
    """Platform-independent GUID type.

    Uses PostgreSQL's UUID type when available, otherwise uses String(36).
    Stores as uuid.UUID on the Python side.
    """

    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        return uuid.UUID(str(value))


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # OTP fields
    otp_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    otp_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    providers: Mapped[list["UserProvider"]] = relationship(
        "UserProvider", back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["Session"]] = relationship(
        "Session", back_populates="user", cascade="all, delete-orphan"
    )
    api_keys: Mapped[list["ApiKey"]] = relationship(
        "ApiKey", back_populates="user"
    )

    def __repr__(self):
        return f"<User id={self.id} email={self.email}>"


class UserProvider(Base):
    __tablename__ = "user_providers"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("users.id"), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)  # anthropic | openai | gemini
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="providers")

    def __repr__(self):
        return f"<UserProvider user={self.user_id} provider={self.provider}>"


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user: Mapped["User"] = relationship("User", back_populates="sessions")

    def __repr__(self):
        return f"<Session user={self.user_id} revoked={self.is_revoked}>"


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID, primary_key=True, default=uuid.uuid4
    )
    key_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    app_name: Mapped[str] = mapped_column(Text, nullable=False)
    owner_email: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # nullable FK for legacy keys (created before user system)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID, ForeignKey("users.id"), nullable=True
    )

    user: Mapped[Optional["User"]] = relationship("User", back_populates="api_keys")
    violations: Mapped[list["UserViolation"]] = relationship(
        "UserViolation", back_populates="api_key", cascade="all, delete-orphan"
    )
    violation_logs: Mapped[list["ViolationLog"]] = relationship(
        "ViolationLog", back_populates="api_key", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<ApiKey id={self.id} app={self.app_name}>"


class UserViolation(Base):
    __tablename__ = "user_violations"
    __table_args__ = (UniqueConstraint("app_id", "user_id", name="uq_user_violations_app_user"),)

    id: Mapped[uuid.UUID] = mapped_column(
        GUID, primary_key=True, default=uuid.uuid4
    )
    app_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("api_keys.id"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    flagged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    api_key: Mapped["ApiKey"] = relationship("ApiKey", back_populates="violations")

    def __repr__(self):
        return f"<UserViolation app={self.app_id} user={self.user_id} count={self.count}>"


class ViolationLog(Base):
    __tablename__ = "violation_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID, primary_key=True, default=uuid.uuid4
    )
    app_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("api_keys.id"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    api_key: Mapped["ApiKey"] = relationship("ApiKey", back_populates="violation_logs")

    def __repr__(self):
        return f"<ViolationLog app={self.app_id} user={self.user_id} severity={self.severity}>"
