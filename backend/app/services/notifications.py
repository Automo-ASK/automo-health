"""Notification hooks (Day 4).

`dispatch()` fires a domain event to configured sinks. It prefers to enqueue a
Celery task so the web request isn't blocked, but falls back to delivering inline
if no broker is reachable (e.g. in tests or local dev without Redis). Delivery
currently logs the event and, if `NOTIFICATIONS_WEBHOOK_URL` is set, POSTs it.
Swap `_deliver` for email/SMS/push providers as they come online.
"""

import logging

import httpx

from app.core.config import settings
from app.models.enums import NotificationEvent

logger = logging.getLogger(__name__)


def _deliver(event: str, payload: dict) -> None:
    """Actually deliver a notification. Runs inside the Celery task (or inline)."""
    logger.info("notification %s: %s", event, payload)
    url = settings.notifications_webhook_url
    if url:
        try:
            httpx.post(url, json={"event": event, "data": payload}, timeout=10.0)
        except Exception as exc:  # noqa: BLE001 — notifications must never break the caller
            logger.warning("notification webhook POST failed for %s: %s", event, exc)


def dispatch(event: NotificationEvent | str, payload: dict) -> None:
    """Fire a notification hook.

    In async mode (``NOTIFICATIONS_ASYNC=true``) the hook is enqueued to Celery so
    the request isn't blocked; if the broker is unreachable we fall back to inline
    delivery. In the default (sync) mode it's delivered inline directly.
    """
    name = event.value if isinstance(event, NotificationEvent) else event

    if settings.notifications_async:
        try:
            from app.tasks.notifications import fire_notification

            fire_notification.delay(name, payload)
            return
        except Exception as exc:  # noqa: BLE001 — broker down: deliver inline instead
            logger.warning("enqueue failed for %s (%s); delivering inline", name, exc)

    _deliver(name, payload)
