"""Slot maintenance tasks."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.booking import Booking
from app.models.enums import BookingStatus, SlotStatus
from app.models.slot import Slot

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.slots.release_expired_holds")
def release_expired_holds() -> int:
    """Return standalone expired holds to OPEN.

    Handles holds placed via ``POST /slots/{id}/hold`` that were never converted
    into a booking. Holds backed by a pending booking are handled by
    ``expire_unpaid_bookings`` so booking + slot state stay consistent.
    """
    now = datetime.now(timezone.utc)
    released = 0
    db = SessionLocal()
    try:
        pending_slot_ids = select(Booking.slot_id).where(
            Booking.status == BookingStatus.PENDING_PAYMENT
        )
        slots = db.execute(
            select(Slot)
            .where(
                Slot.status == SlotStatus.HELD,
                Slot.hold_expires_at.is_not(None),
                Slot.hold_expires_at <= now,
                Slot.id.not_in(pending_slot_ids),
            )
            .with_for_update(skip_locked=True)
        ).scalars().all()

        for slot in slots:
            slot.status = SlotStatus.OPEN
            slot.hold_expires_at = None
            released += 1

        db.commit()
        if released:
            logger.info("Released %d expired slot hold(s)", released)
        return released
    finally:
        db.close()
