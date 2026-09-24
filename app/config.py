from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Existing
    database_url: str
    anthropic_api_key: str = ""
    admin_secret: str
    app_env: str = "development"
    log_level: str = "info"

    # Auth / JWT
    fernet_secret: str = ""
    jwt_secret: str = "change-me-jwt-secret"
    jwt_expiry_days: int = 30

    # SMTP (optional — OTP is logged if not configured)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = "noreply@mod.example.com"

    # Service URL shown in CLI provider auth guidance
    service_url: str = "http://localhost:8000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def smtp_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_user)


@lru_cache
def get_settings() -> Settings:
    return Settings()
