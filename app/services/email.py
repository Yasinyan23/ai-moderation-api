"""OTP email delivery — logs to stdout when SMTP is not configured."""
import logging
import random
import string

import aiosmtplib
from email.message import EmailMessage

from app.config import get_settings

logger = logging.getLogger(__name__)


def generate_otp(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))


async def send_otp_email(to_email: str, otp: str) -> None:
    settings = get_settings()

    if not settings.smtp_enabled:
        # Development fallback — print OTP so the developer can use it
        logger.info("OTP for %s: %s  (SMTP not configured — printed to log)", to_email, otp)
        return

    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to_email
    msg["Subject"] = "Your mod verification code"
    msg.set_content(
        f"Your verification code is: {otp}\n\n"
        "This code expires in 10 minutes. Do not share it with anyone."
    )

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_pass,
            start_tls=True,
        )
        logger.info("OTP email sent to %s", to_email)
    except Exception as e:
        logger.error("Failed to send OTP email to %s: %s", to_email, e)
        raise
