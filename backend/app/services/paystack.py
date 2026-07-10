"""Thin Paystack client.

In development, if the secret key is still the placeholder we short-circuit the
network call and return a deterministic mock so the booking → payment flow is
exercisable without real credentials. Swap in a real `PAYSTACK_SECRET_KEY` to hit
the live API.
"""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_PLACEHOLDER_PREFIXES = ("sk_test_changeme", "sk_test_xxx")


def _is_configured() -> bool:
    key = settings.paystack_secret_key or ""
    return bool(key) and not key.startswith(_PLACEHOLDER_PREFIXES)


def initialize_transaction(
    *, email: str, amount_kobo: int, reference: str, currency: str
) -> dict:
    """Initialize a Paystack transaction.

    Returns a dict with at least: ``reference``, ``authorization_url``, ``access_code``.
    Raises ``httpx.HTTPStatusError`` on a live API failure.
    """
    if not _is_configured():
        logger.warning(
            "PAYSTACK_SECRET_KEY not configured — returning mock init for reference %s",
            reference,
        )
        return {
            "reference": reference,
            "authorization_url": f"https://checkout.paystack.com/mock/{reference}",
            "access_code": f"mock_{reference}",
            "mocked": True,
        }

    resp = httpx.post(
        f"{settings.paystack_base_url}/transaction/initialize",
        headers={
            "Authorization": f"Bearer {settings.paystack_secret_key}",
            "Content-Type": "application/json",
        },
        json={
            "email": email,
            "amount": amount_kobo,
            "currency": currency,
            "reference": reference,
            "callback_url": settings.paystack_callback_url,
        },
        timeout=20.0,
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    return {
        "reference": data["reference"],
        "authorization_url": data["authorization_url"],
        "access_code": data["access_code"],
        "mocked": False,
    }


def verify_transaction(reference: str) -> dict:
    """Verify a Paystack transaction by reference. Returns the ``data`` object.

    Mock mode reports a successful charge so the reconciliation path is testable.
    """
    if not _is_configured():
        logger.warning("PAYSTACK_SECRET_KEY not configured — mock verify for %s", reference)
        return {"reference": reference, "status": "success", "mocked": True}

    resp = httpx.get(
        f"{settings.paystack_base_url}/transaction/verify/{reference}",
        headers={"Authorization": f"Bearer {settings.paystack_secret_key}"},
        timeout=20.0,
    )
    resp.raise_for_status()
    return resp.json()["data"]
