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


async def send_verification_email(to_email: str, verify_link: str) -> bool:
    subject = "Confirm your email for CareWise"
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
      <h2 style="color: #4F7A4E;">Confirm your email</h2>
      <p>Thanks for joining CareWise. Please confirm this is your email address, so we can
      help you get back in if you ever forget your password.
      This link expires in {settings.verify_email_expire_hours} hours.</p>
      <p style="margin: 24px 0;">
        <a href="{verify_link}" style="background:#4F7A4E;color:#fff;padding:10px 20px;
           border-radius:8px;text-decoration:none;">Confirm my email</a>
      </p>
      <p style="color:#716A62;font-size:13px;">
        If you didn't create a CareWise account, you can ignore this email.
      </p>
    </div>
    """
    return await _send(to_email, subject, html, fallback_log=f"email confirmation link for {to_email}: {verify_link}")


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
    return await _send(to_email, subject, html, fallback_log=f"password reset link for {to_email}: {reset_link}")


async def _send(to_email: str, subject: str, html: str, fallback_log: str) -> bool:
    """Send via Resend, or log the content when RESEND_API_KEY isn't configured."""
    if not settings.resend_api_key:
        logger.info("RESEND_API_KEY not configured, so not sent. %s", fallback_log)
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
            logger.error("Failed to send '%s' email to %s: %s", subject, to_email, e)
            return False
