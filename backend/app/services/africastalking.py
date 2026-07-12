"""Africa's Talking client wrapper.

Initialised lazily on first use so the app still starts if AT credentials
are missing (useful in local dev / unit tests).
"""

from __future__ import annotations

import threading

import africastalking

from app.core.config import settings

_lock = threading.Lock()
_initialised = False
_sms_service = None


def _ensure_initialised() -> None:
    global _initialised, _sms_service
    if _initialised:
        return
    with _lock:
        if _initialised:
            return
        africastalking.initialize(settings.at_username, settings.at_api_key)
        _sms_service = africastalking.SMS
        _initialised = True


def send_sms(message: str, recipients: list[str]) -> dict:
    """Send an SMS via Africa's Talking.

    ``recipients`` is a list of E.164 phone numbers, e.g. ["+2348012345678"].
    Returns the raw AT response dict.
    """
    _ensure_initialised()
    response = _sms_service.send(
        message=message,
        recipients=recipients,
        sender_id=settings.at_sender_id if settings.at_username != "sandbox" else None,
    )
    return response
