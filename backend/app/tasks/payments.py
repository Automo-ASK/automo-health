"""Payment maintenance tasks (Day 6 hardening).

`reverify_pending_payments` re-checks still-pending payments against Paystack, so a
booking is confirmed even if its webhook was dropped or never delivered. It's a
safety net on top of the webhook, not a replacement — reconciliation is idempotent,
so double delivery is harmless.
"""

import logging

from sqlalchemy import select

from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.booking import Booking
from app.models.enums import BookingStatus, PaymentProvider, PaymentStatus
from app.models.payment import Payment
from app.services import paystack, reconciliation

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.payments.reverify_pending_payments")
def reverify_pending_payments(limit: int = 100) -> int:
    """Re-verify pending Paystack payments on still-open bookings; reconcile any that
    have since succeeded. Returns the number newly confirmed."""
    confirmed = 0
    db = SessionLocal()
    try:
        rows = db.execute(
            select(Payment)
            .join(Booking, Booking.id == Payment.booking_id)
            .where(
                Payment.status == PaymentStatus.PENDING,
                Payment.provider == PaymentProvider.PAYSTACK,
                Booking.status == BookingStatus.PENDING_PAYMENT,
            )
            .limit(limit)
        ).scalars().all()

        references = [p.reference for p in rows]
    finally:
        db.close()

    for reference in references:
        db = SessionLocal()
        try:
            data = paystack.verify_transaction(reference)
            data.setdefault("reference", reference)
            if (data.get("status") or "").lower() != "success":
                continue
            result = reconciliation.reconcile_from_paystack(db, data)
            if result.status == "confirmed":
                confirmed += 1
        except Exception as exc:  # noqa: BLE001 — one bad ref shouldn't stop the sweep
            logger.warning("reverify failed for %s: %s", reference, exc)
        finally:
            db.close()

    if confirmed:
        logger.info("reverify sweep confirmed %d payment(s)", confirmed)
    return confirmed
