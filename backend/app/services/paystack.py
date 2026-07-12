"""Thin Paystack client.

In development, if the secret key is still the placeholder we short-circuit the
network call and return a deterministic mock so the booking → payment flow is
exercisable without real credentials. Swap in a real `PAYSTACK_SECRET_KEY` to hit
the live API.
"""

import hashlib
import hmac
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_PLACEHOLDER_PREFIXES = ("sk_test_changeme", "sk_test_xxx")


def _is_configured() -> bool:
    key = settings.paystack_secret_key or ""
    return bool(key) and not key.startswith(_PLACEHOLDER_PREFIXES)


def is_mock() -> bool:
    """True when running without real Paystack credentials (dev/test)."""
    return not _is_configured()


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.paystack_secret_key}",
        "Content-Type": "application/json",
    }


def verify_signature(raw_body: bytes, signature: str | None) -> bool:
    """Verify a Paystack webhook signature.

    Paystack signs the raw request body with HMAC-SHA512 using your secret key and
    sends it in the ``x-paystack-signature`` header. In mock mode (no real key) we
    accept the request so the webhook flow is testable locally.
    """
    if is_mock():
        return True
    if not signature:
        return False
    expected = hmac.new(
        settings.paystack_secret_key.encode(), raw_body, hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


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
        headers=_headers(),
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
        headers=_headers(),
        timeout=20.0,
    )
    resp.raise_for_status()
    return resp.json()["data"]


def create_customer(*, email: str, full_name: str, phone: str | None = None) -> dict:
    """Create (or fetch) a Paystack customer. Returns the customer object."""
    first, _, last = full_name.partition(" ")
    if is_mock():
        code = f"CUS_mock_{abs(hash(email)) % 10**10:010d}"
        logger.warning("Paystack not configured — mock customer %s for %s", code, email)
        return {"customer_code": code, "email": email, "mocked": True}

    resp = httpx.post(
        f"{settings.paystack_base_url}/customer",
        headers=_headers(),
        json={"email": email, "first_name": first, "last_name": last, "phone": phone},
        timeout=20.0,
    )
    resp.raise_for_status()
    return resp.json()["data"]


def create_dedicated_virtual_account(
    *, customer_code: str, email: str, preferred_bank: str | None = None
) -> dict:
    """Provision a dedicated NUBAN for a customer.

    Returns a dict with ``account_number``, ``account_name``, ``bank_name`` and the
    ``customer_code``. Mock mode returns a deterministic fake account so bank-transfer
    reconciliation can be exercised without real credentials.
    """
    bank = preferred_bank or settings.paystack_dva_preferred_bank
    if is_mock():
        acct = f"{abs(hash(customer_code)) % 10**10:010d}"
        logger.warning("Paystack not configured — mock DVA %s for %s", acct, customer_code)
        return {
            "account_number": acct,
            "account_name": "Automo Health / Test",
            "bank_name": "Test Bank",
            "customer_code": customer_code,
            "mocked": True,
        }

    resp = httpx.post(
        f"{settings.paystack_base_url}/dedicated_account",
        headers=_headers(),
        json={"customer": customer_code, "preferred_bank": bank},
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    return {
        "account_number": data["account_number"],
        "account_name": data["account_name"],
        "bank_name": data.get("bank", {}).get("name"),
        "customer_code": customer_code,
        "raw": data,
        "mocked": False,
    }
