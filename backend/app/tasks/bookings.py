"""Booking maintenance tasks."""

import logging

from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.enums import NotificationEvent
from app.services import bookings as bookings_service
from app.services import notifications

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.bookings.expire_unpaid_bookings")
def expire_unpaid_bookings() -> int:
    """Expire bookings that never completed payment before their deadline.

    For each expired booking: mark it EXPIRED, abandon its pending payment, and
    release the held slot back to OPEN. The DB work lives in the booking service so
    it's shared with the test suite; hooks fire here after commit.
    """
    db = SessionLocal()
    try:
        expired_ids = bookings_service.expire_overdue_bookings(db)
    finally:
        db.close()

    # Fire hooks after the state is durably committed.
    for booking_id in expired_ids:
        notifications.dispatch(NotificationEvent.BOOKING_EXPIRED, {"booking_id": str(booking_id)})

    if expired_ids:
        logger.info("Expired %d unpaid booking(s)", len(expired_ids))
    return len(expired_ids)
