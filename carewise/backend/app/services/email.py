"""Transactional email delivery via Resend's HTTP API.

If RESEND_API_KEY isn't configured, sending no-ops and logs the content
instead — same honest-fallback pattern as demo-mode LLM responses, so the
reset flow is still testable locally without a real email account.
"""
from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

RESEND_API_URL = "https://api.resend.com/emails"


async def send_password_reset_email(to_email: str, reset_link: str) -> bool:
    subject = "Reset your CareWise password"
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
      <h2 style="color: #4F7A4E;">Reset your password</h2>
      <p>We received a request to reset the password for your CareWise account.
      This link expires in {settings.reset_token_expire_minutes} minutes.</p>
      <p style="margin: 24px 0;">
        <a href="{reset_link}" style="background:#4F7A4E;color:#fff;padding:10px 20px;
           border-radius:8px;text-decoration:none;">Reset password</a>
      </p>
      <p style="color:#928B83;font-size:13px;">
        If you didn't request this, you can safely ignore this email —
        your password won't be changed.
      </p>
    </div>
    """

    if not settings.resend_api_key:
        logger.info(
            "RESEND_API_KEY not configured — password reset link for %s: %s",
            to_email, reset_link,
        )
        return False

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(
                RESEND_API_URL,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json={
                    "from": settings.resend_from_email,
                    "to": [to_email],
                    "subject": subject,
                    "html": html,
                },
            )
            response.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("Failed to send password reset email to %s: %s", to_email, e)
            return False
