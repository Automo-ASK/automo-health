"""Notification hooks.

`dispatch()` fires a domain event to configured sinks:
  1. SMS — patient-facing events (BOOKING_CREATED, BOOKING_CONFIRMED, BOOKING_EXPIRED)
     are delivered as AT SMS messages via sms_notifications.
  2. Webhook — if `NOTIFICATIONS_WEBHOOK_URL` is set, every event is POSTed as JSON.

In async mode (`NOTIFICATIONS_ASYNC=true`) the hook is enqueued to Celery so
the web request isn't blocked; if the broker is unreachable we fall back to
inline delivery.  In the default (sync) mode it's delivered inline directly.
"""

import logging

import httpx

from app.core.config import settings
from app.models.enums import NotificationEvent

logger = logging.getLogger(__name__)

_SMS_EVENTS = frozenset({
    NotificationEvent.BOOKING_CREATED.value,
    NotificationEvent.BOOKING_CONFIRMED.value,
    NotificationEvent.BOOKING_EXPIRED.value,
})


def _deliver(event: str, payload: dict) -> None:
    """Actually deliver a notification. Runs inside the Celery task (or inline)."""
    logger.info("notification %s: %s", event, payload)

    # ── SMS delivery for patient-facing events ────────────────────────────────
    booking_id = payload.get("booking_id")
    if event in _SMS_EVENTS and booking_id:
        from app.core.database import SessionLocal
        from app.services import sms_notifications

        lang = payload.get("lang")  # optional hint from USSD/SMS booking context
        db = SessionLocal()
        try:
            if event == NotificationEvent.BOOKING_CREATED.value:
                sms_notifications.send_booking_created(db, booking_id, lang=lang)
            elif event == NotificationEvent.BOOKING_CONFIRMED.value:
                sms_notifications.send_booking_confirmed(db, booking_id, lang=lang)
            elif event == NotificationEvent.BOOKING_EXPIRED.value:
                sms_notifications.send_booking_expired(db, booking_id, lang=lang)
        except Exception as exc:  # noqa: BLE001
            logger.error("SMS notification failed for %s/%s: %s", event, booking_id, exc)
        finally:
            db.close()

    # ── Webhook delivery ──────────────────────────────────────────────────────
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
