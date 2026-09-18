"""Web Push delivery — sends browser notifications via VAPID."""
from __future__ import annotations

import json
import logging

from pywebpush import WebPushException, webpush
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.db import PushSubscription

logger = logging.getLogger(__name__)
settings = get_settings()


async def send_push_to_user(db: AsyncSession, user_id: int, title: str, body: str, tag: str = "carewise") -> int:
    """Send a push notification to every subscription the user has registered.

    Returns the number of subscriptions successfully notified. Expired/invalid
    subscriptions (410 Gone / 404) are removed automatically.
    """
    if not settings.vapid_private_key:
        logger.info("Push skipped for user_id=%s: no VAPID_PRIVATE_KEY configured.", user_id)
        return 0

    result = await db.execute(select(PushSubscription).where(PushSubscription.user_id == user_id))
    subs = list(result.scalars())
    if not subs:
        return 0

    payload = json.dumps({"title": title, "body": body, "tag": tag})
    sent = 0
    stale_ids: list[int] = []

    for sub in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.vapid_claim_email},
            )
            sent += 1
        except WebPushException as e:
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):
                stale_ids.append(sub.id)
            else:
                logger.warning("Push failed for subscription id=%s: %s", sub.id, e)

    if stale_ids:
        await db.execute(delete(PushSubscription).where(PushSubscription.id.in_(stale_ids)))
        await db.commit()

    return sent
