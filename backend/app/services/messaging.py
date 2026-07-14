"""Outbound patient messaging across channels (Day 6).

A thin router that sends a patient-facing message over the right channel. SMS goes
through Africa's Talking; WhatsApp/USSD are logged (the WhatsApp sender is owned by
the conversation workstream — this hook is where it plugs in). Delivery must never
break the caller, so every path is wrapped and failures are swallowed + logged.

In dev/test (no real AT credentials, or no phone on file) it degrades to logging so
the whole flow stays exercisable offline.
"""

from __future__ import annotations

import logging

from app.core.config import settings
from app.models.enums import ChannelType
from app.models.patient import Patient
from app.services import africastalking as at

logger = logging.getLogger(__name__)


def _at_configured() -> bool:
    key = settings.at_api_key or ""
    return bool(key) and key != "changeme" and not key.startswith("your_")


def send_to_patient(
    patient: Patient | None,
    message: str,
    *,
    channel: ChannelType | None = None,
) -> dict:
    """Best-effort deliver ``message`` to ``patient`` over ``channel`` (default SMS).

    Returns a small result dict ({"delivered": bool, "channel": ..., "detail": ...}).
    Never raises — notifications must not break the request path.
    """
    if patient is None:
        return {"delivered": False, "channel": None, "detail": "no patient"}

    chan = channel or ChannelType.SMS
    phone = patient.phone

    if chan in (ChannelType.WHATSAPP, ChannelType.USSD):
        # WhatsApp is delivered by the conversation service; USSD is session-bound and
        # can't be pushed to. Log so the intent is visible end-to-end.
        logger.info("message[%s] to %s: %s", chan.value, phone or patient.email, message)
        return {"delivered": False, "channel": chan.value, "detail": "logged (no outbound push)"}

    # SMS via Africa's Talking.
    if not phone:
        logger.info("message[sms] skipped — patient %s has no phone", patient.id)
        return {"delivered": False, "channel": "sms", "detail": "no phone on file"}

    if not _at_configured():
        logger.info("message[sms] (mock) to %s: %s", phone, message)
        return {"delivered": False, "channel": "sms", "detail": "mock (AT not configured)"}

    try:
        resp = at.send_sms(message, [phone])
        return {"delivered": True, "channel": "sms", "detail": resp}
    except Exception as exc:  # noqa: BLE001 — messaging must never break the caller
        logger.warning("SMS send failed for %s: %s", phone, exc)
        return {"delivered": False, "channel": "sms", "detail": str(exc)}
