import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.routers import health, moderate, admin
from app.routers import auth as auth_router
from app.routers import providers as providers_router

CYAN = "\033[36m"
RESET = "\033[0m"
WHITE = "\033[97m"

BANNER = f"""{CYAN}
  ███╗   ███╗ ██████╗ ██████╗ ███████╗██████╗  █████╗ ████████╗ ██████╗ ██████╗
  ████╗ ████║██╔═══██╗██╔══██╗██╔════╝██╔══██╗██╔══██╗╚══██╔══╝██╔═══██╗██╔══██╗
  ██╔████╔██║██║   ██║██║  ██║█████╗  ██████╔╝███████║   ██║   ██║   ██║██████╔╝
  ██║╚██╔╝██║██║   ██║██║  ██║██╔══╝  ██╔══██╗██╔══██║   ██║   ██║   ██║██╔══██╗
  ██║ ╚═╝ ██║╚██████╔╝██████╔╝███████╗██║  ██║██║  ██║   ██║   ╚██████╔╝██║  ██║
  ╚═╝     ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝
{RESET}"""


def _configure_logging(settings) -> None:
    """Configure structured logging with reduced noise from third-party libraries."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )

    # Suppress noisy third-party loggers that add no value in production
    _noisy = [
        "uvicorn.access",        # per-request HTTP logs (too verbose at INFO)
        "sqlalchemy.engine",     # SQL query echo
        "sqlalchemy.pool",       # connection pool churn
        "httpx",                 # outbound HTTP client debug
        "httpcore",              # underlying httpx transport
        "anthropic",             # SDK internals
        "openai",                # SDK internals
        "google.generativeai",   # SDK internals
        "google.auth",           # credentials refresh noise
    ]
    for name in _noisy:
        logging.getLogger(name).setLevel(logging.WARNING)

    # Keep uvicorn error/startup logs visible
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)


def _log_banner(settings) -> None:
    logger = logging.getLogger("moderator.startup")
    logger.info(BANNER)
    logger.info("%s  AI Message Moderation Service%s", WHITE, RESET)
    logger.info("%s  ─────────────────────────────%s", WHITE, RESET)
    logger.info("%s  env:    %s%s", WHITE, settings.app_env, RESET)
    logger.info("%s  db:     connected%s", WHITE, RESET)
    logger.info("%s  auth:   JWT (HS256, %d days)%s", WHITE, settings.jwt_expiry_days, RESET)
    logger.info("%s  smtp:   %s%s", WHITE, "enabled" if settings.smtp_enabled else "disabled (OTP logged)", RESET)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    _configure_logging(settings)
    _log_banner(settings)
    yield


app = FastAPI(title="Moderator", version="1.0.0", lifespan=lifespan)
app.include_router(health.router)
app.include_router(moderate.router)
app.include_router(admin.router)
app.include_router(auth_router.router)
app.include_router(providers_router.router)
