"""Appointment lifecycle & doctor actions (Day 5).

Statuses: SCHEDULED -> COMPLETED ("tick Done") / NO_SHOW / CANCELLED. A confirmed
appointment can also be:
  * rescheduled onto a different open slot (releases the old slot, books the new one);
  * used to spawn a follow-up appointment for the same patient/provider.

All slot transitions take row locks (``SELECT ... FOR UPDATE``) so they can't race
concurrent bookings/holds. Notification hooks fire after the state is committed, and
the patient is messaged over their channel.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.booking import Booking
from app.models.enums import (
    AppointmentStatus,
    BookingStatus,
    NotificationEvent,
    SlotStatus,
)
from app.models.service import Service
from app.models.slot import Slot
from app.services import messaging, notifications
from app.services.exceptions import ConflictError, NotFoundError
from app.services.slots import _is_holdable


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_appointment(db: Session, appointment_id: uuid.UUID) -> Appointment:
    appt = db.get(Appointment, appointment_id)
    if appt is None:
        raise NotFoundError(f"Appointment {appointment_id} not found")
    return appt


def list_appointments(
    db: Session,
    *,
    patient_id: uuid.UUID | None = None,
    provider_id: uuid.UUID | None = None,
    status: AppointmentStatus | None = None,
) -> list[Appointment]:
    stmt = select(Appointment)
    if patient_id is not None:
        stmt = stmt.where(Appointment.patient_id == patient_id)
    if provider_id is not None:
        stmt = stmt.where(Appointment.provider_id == provider_id)
    if status is not None:
        stmt = stmt.where(Appointment.status == status)
    stmt = stmt.order_by(Appointment.scheduled_start)
    return list(db.execute(stmt).scalars().all())


def _lock_appointment(db: Session, appointment_id: uuid.UUID) -> Appointment:
    appt = db.execute(
        select(Appointment).where(Appointment.id == appointment_id).with_for_update()
    ).scalar_one_or_none()
    if appt is None:
        raise NotFoundError(f"Appointment {appointment_id} not found")
    return appt


def complete_appointment(
    db: Session, appointment_id: uuid.UUID, *, notes: str | None = None
) -> Appointment:
    """Tick Done. Marks a SCHEDULED appointment COMPLETED and stamps clinician notes."""
    appt = _lock_appointment(db, appointment_id)

    if appt.status == AppointmentStatus.COMPLETED:
        return appt
    if appt.status != AppointmentStatus.SCHEDULED:
        raise ConflictError(f"Cannot complete a {appt.status.value} appointment")

    appt.status = AppointmentStatus.COMPLETED
    appt.completed_at = _utcnow()
    if notes:
        appt.notes = notes
    db.commit()
    db.refresh(appt)

    notifications.dispatch(
        NotificationEvent.APPOINTMENT_COMPLETED,
        {"appointment_id": str(appt.id), "patient_id": str(appt.patient_id)},
    )
    messaging.send_to_patient(
        appt.patient, "Your appointment is marked complete. Get well soon! 🙏"
    )
    return appt


def mark_no_show(db: Session, appointment_id: uuid.UUID) -> Appointment:
    """Mark a SCHEDULED appointment as a no-show (patient didn't attend)."""
    appt = _lock_appointment(db, appointment_id)

    if appt.status == AppointmentStatus.NO_SHOW:
        return appt
    if appt.status != AppointmentStatus.SCHEDULED:
        raise ConflictError(f"Cannot mark a {appt.status.value} appointment as no-show")

    appt.status = AppointmentStatus.NO_SHOW
    db.commit()
    db.refresh(appt)

    notifications.dispatch(
        NotificationEvent.APPOINTMENT_NO_SHOW,
        {"appointment_id": str(appt.id), "patient_id": str(appt.patient_id)},
    )
    return appt


def cancel_appointment(db: Session, appointment_id: uuid.UUID) -> Appointment:
    """Cancel a scheduled appointment and release its slot back to OPEN."""
    appt = _lock_appointment(db, appointment_id)

    if appt.status == AppointmentStatus.CANCELLED:
        return appt
    if appt.status == AppointmentStatus.COMPLETED:
        raise ConflictError("Cannot cancel a completed appointment")

    appt.status = AppointmentStatus.CANCELLED

    # Release the slot and cancel the owning booking.
    slot = db.execute(
        select(Slot).where(Slot.id == appt.slot_id).with_for_update()
    ).scalar_one_or_none()
    if slot is not None:
        slot.status = SlotStatus.OPEN
        slot.hold_expires_at = None

    booking = db.execute(
        select(Booking).where(Booking.id == appt.booking_id).with_for_update()
    ).scalar_one_or_none()
    if booking is not None and booking.status not in (
        BookingStatus.CANCELLED,
        BookingStatus.EXPIRED,
    ):
        booking.status = BookingStatus.CANCELLED

    db.commit()
    db.refresh(appt)

    notifications.dispatch(
        NotificationEvent.APPOINTMENT_CANCELLED,
        {"appointment_id": str(appt.id), "patient_id": str(appt.patient_id)},
    )
    messaging.send_to_patient(
        appt.patient, "Your appointment has been cancelled. Reply to rebook anytime."
    )
    return appt


def reschedule_appointment(
    db: Session, appointment_id: uuid.UUID, *, new_slot_id: uuid.UUID
) -> Appointment:
    """Move a scheduled appointment onto a different open slot.

    Locks both slots, releases the old one to OPEN, books the new one, and repoints
    the appointment and its booking at the new slot/time.
    """
    appt = _lock_appointment(db, appointment_id)
    if appt.status != AppointmentStatus.SCHEDULED:
        raise ConflictError(f"Cannot reschedule a {appt.status.value} appointment")

    if new_slot_id == appt.slot_id:
        raise ConflictError("New slot is the same as the current slot")

    now = _utcnow()

    # Lock both slots in a stable order (by id) to avoid deadlocks.
    ids = sorted([appt.slot_id, new_slot_id], key=str)
    locked = {
        s.id: s
        for s in db.execute(
            select(Slot).where(Slot.id.in_(ids)).with_for_update()
        ).scalars().all()
    }
    old_slot = locked.get(appt.slot_id)
    new_slot = locked.get(new_slot_id)
    if new_slot is None:
        db.rollback()
        raise NotFoundError(f"Slot {new_slot_id} not found")
    if not _is_holdable(new_slot, now):
        db.rollback()
        raise ConflictError(
            f"Slot {new_slot_id} is not available (status={new_slot.status.value})"
        )

    if old_slot is not None:
        old_slot.status = SlotStatus.OPEN
        old_slot.hold_expires_at = None

    new_slot.status = SlotStatus.BOOKED
    new_slot.hold_expires_at = None

    appt.slot_id = new_slot.id
    appt.provider_id = new_slot.provider_id
    appt.scheduled_start = new_slot.start_time
    appt.scheduled_end = new_slot.end_time

    booking = db.get(Booking, appt.booking_id)
    if booking is not None:
        booking.slot_id = new_slot.id

    db.commit()
    db.refresh(appt)

    notifications.dispatch(
        NotificationEvent.APPOINTMENT_RESCHEDULED,
        {
            "appointment_id": str(appt.id),
            "patient_id": str(appt.patient_id),
            "scheduled_start": appt.scheduled_start.isoformat(),
        },
    )
    messaging.send_to_patient(
        appt.patient,
        f"Your appointment has been rescheduled to {appt.scheduled_start:%a %d %b, %H:%M}.",
    )
    return appt


def create_follow_up(
    db: Session,
    appointment_id: uuid.UUID,
    *,
    new_slot_id: uuid.UUID,
    service_id: uuid.UUID | None = None,
    notes: str | None = None,
) -> Appointment:
    """Book a follow-up appointment for the same patient off an existing appointment.

    A follow-up is a clinician-scheduled visit: it books the chosen open slot
    immediately (booking CONFIRMED, appointment SCHEDULED) and links back to the
    parent. Any charge is settled separately at the desk (cashier).
    """
    parent = get_appointment(db, appointment_id)
    now = _utcnow()

    slot = db.execute(
        select(Slot).where(Slot.id == new_slot_id).with_for_update()
    ).scalar_one_or_none()
    if slot is None:
        raise NotFoundError(f"Slot {new_slot_id} not found")
    if not _is_holdable(slot, now):
        db.rollback()
        raise ConflictError(
            f"Slot {new_slot_id} is not available (status={slot.status.value})"
        )

    # Price the follow-up from the chosen/slot service (for reporting; collected later).
    resolved_service_id = service_id or slot.service_id
    amount = 0
    currency = slot.service.currency if slot.service else "NGN"
    if resolved_service_id is not None:
        service = db.get(Service, resolved_service_id)
        if service is None:
            db.rollback()
            raise NotFoundError(f"Service {resolved_service_id} not found")
        amount = service.price_amount
        currency = service.currency

    slot.status = SlotStatus.BOOKED
    slot.hold_expires_at = None

    booking = Booking(
        patient_id=parent.patient_id,
        slot_id=slot.id,
        service_id=resolved_service_id,
        status=BookingStatus.CONFIRMED,
        amount=amount,
        currency=currency,
    )
    db.add(booking)
    db.flush()

    appt = Appointment(
        booking_id=booking.id,
        patient_id=parent.patient_id,
        provider_id=slot.provider_id,
        slot_id=slot.id,
        scheduled_start=slot.start_time,
        scheduled_end=slot.end_time,
        status=AppointmentStatus.SCHEDULED,
        parent_appointment_id=parent.id,
        notes=notes,
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)

    notifications.dispatch(
        NotificationEvent.APPOINTMENT_FOLLOW_UP,
        {
            "appointment_id": str(appt.id),
            "parent_appointment_id": str(parent.id),
            "patient_id": str(appt.patient_id),
            "scheduled_start": appt.scheduled_start.isoformat(),
        },
    )
    messaging.send_to_patient(
        appt.patient,
        f"A follow-up has been booked for {appt.scheduled_start:%a %d %b, %H:%M}.",
    )
    return appt
