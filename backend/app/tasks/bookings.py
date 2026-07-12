"""Booking maintenance tasks."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.booking import Booking
from app.models.enums import BookingStatus, NotificationEvent, PaymentStatus, SlotStatus
from app.models.slot import Slot
from app.services import notifications

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.bookings.expire_unpaid_bookings")
def expire_unpaid_bookings() -> int:
    """Expire bookings that never completed payment before their deadline.

    For each expired booking: mark it EXPIRED, abandon its pending payment, and
    release the held slot back to OPEN.
    """
    now = datetime.now(timezone.utc)
    expired_ids: list[str] = []
    db = SessionLocal()
    try:
        bookings = db.execute(
            select(Booking)
            .where(
                Booking.status == BookingStatus.PENDING_PAYMENT,
                Booking.expires_at.is_not(None),
                Booking.expires_at <= now,
            )
            .with_for_update(skip_locked=True)
        ).scalars().all()

        for booking in bookings:
            booking.status = BookingStatus.EXPIRED

            if booking.payment is not None and booking.payment.status == PaymentStatus.PENDING:
                booking.payment.status = PaymentStatus.ABANDONED

            slot = db.execute(
                select(Slot).where(Slot.id == booking.slot_id).with_for_update()
            ).scalar_one_or_none()
            if slot is not None and slot.status == SlotStatus.HELD:
                slot.status = SlotStatus.OPEN
                slot.hold_expires_at = None

            expired_ids.append(str(booking.id))

        db.commit()
    finally:
        db.close()

    # Fire hooks after the state is durably committed.
    for booking_id in expired_ids:
        notifications.dispatch(NotificationEvent.BOOKING_EXPIRED, {"booking_id": booking_id})

    if expired_ids:
        logger.info("Expired %d unpaid booking(s)", len(expired_ids))
    return len(expired_ids)
