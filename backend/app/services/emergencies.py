"""Emergency alerts and the doctor's "make room" action (PRD §8.6).

A channel raises an emergency (triage category + one sentence). The doctor board
surfaces it; the doctor either seats the patient now — shifting whoever was
scheduled to the next open slot and apologising to them — or marks it handled.
Never a substitute for clinical triage.
"""

import uuid
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.booking import Booking
from app.models.emergency import Emergency
from app.models.enums import (
    AppointmentStatus,
    BookingStatus,
    EmergencyStatus,
    NotificationEvent,
    SlotStatus,
)
from app.models.patient import Patient
from app.models.slot import Slot
from app.services import messaging, notifications
from app.services.dashboard import WAT, resolve_provider
from app.services.exceptions import ConflictError, NotFoundError


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today_bounds() -> tuple[datetime, datetime]:
    start = datetime.combine(datetime.now(WAT).date(), time.min, tzinfo=WAT)
    return start, start + timedelta(days=1)


def list_emergencies(db: Session, *, status: EmergencyStatus | None = None) -> list[dict]:
    stmt = select(Emergency)
    if status is not None:
        stmt = stmt.where(Emergency.status == status)
    stmt = stmt.order_by(Emergency.created_at.desc())
    rows = db.execute(stmt).scalars().all()
    return [_serialize(e) for e in rows]


def _serialize(e: Emergency) -> dict:
    return {
        "id": str(e.id),
        "patient_name": e.patient.full_name if e.patient else "Patient",
        "patient_phone": e.patient.phone if e.patient else None,
        "category": e.category,
        "description": e.description,
        "status": e.status.value,
        "created_at": e.created_at.isoformat(),
    }


def create_emergency(
    db: Session, *, patient_id: uuid.UUID, category: str, description: str
) -> dict:
    if db.get(Patient, patient_id) is None:
        raise NotFoundError(f"Patient {patient_id} not found")
    emg = Emergency(patient_id=patient_id, category=category, description=description)
    db.add(emg)
    db.commit()
    db.refresh(emg)
    notifications.dispatch(
        NotificationEvent.APPOINTMENT_NO_SHOW,  # reuse channel; emergency has no dedicated event
        {"emergency_id": str(emg.id), "category": category},
    )
    return _serialize(emg)


def acknowledge(db: Session, emergency_id: uuid.UUID) -> dict:
    emg = db.get(Emergency, emergency_id)
    if emg is None:
        raise NotFoundError(f"Emergency {emergency_id} not found")
    emg.status = EmergencyStatus.ACKNOWLEDGED
    db.commit()
    db.refresh(emg)
    return _serialize(emg)


def make_room(db: Session, emergency_id: uuid.UUID, *, provider_ref: str) -> dict:
    """Seat the emergency patient now, shifting the scheduled patient if needed.

    Strategy: take the provider's current queue head; if there's a later open slot
    today, move the head there (apology fires) and seat the emergency in the head's
    freed slot. Otherwise seat the emergency in the nearest open slot.
    """
    emg = db.get(Emergency, emergency_id)
    if emg is None:
        raise NotFoundError(f"Emergency {emergency_id} not found")
    provider = resolve_provider(db, provider_ref)
    start, end = _today_bounds()

    # Current queue head for this provider today.
    head = db.execute(
        select(Appointment)
        .where(
            Appointment.provider_id == provider.id,
            Appointment.status == AppointmentStatus.SCHEDULED,
            Appointment.scheduled_start >= start,
            Appointment.scheduled_start < end,
        )
        .order_by(Appointment.scheduled_start)
        .limit(1)
        .with_for_update()
    ).scalar_one_or_none()

    bumped_to: dict | None = None
    seat_slot: Slot | None = None

    if head is not None:
        head_slot = db.execute(
            select(Slot).where(Slot.id == head.slot_id).with_for_update()
        ).scalar_one()
        next_open = db.execute(
            select(Slot)
            .where(
                Slot.provider_id == provider.id,
                Slot.status == SlotStatus.OPEN,
                Slot.start_time > head_slot.start_time,
                Slot.start_time >= start,
                Slot.start_time < end,
            )
            .order_by(Slot.start_time)
            .limit(1)
            .with_for_update()
        ).scalar_one_or_none()

        if next_open is not None:
            # Shift the scheduled patient forward; their old slot seats the emergency.
            next_open.status = SlotStatus.BOOKED
            next_open.hold_expires_at = None
            head.slot_id = next_open.id
            head.scheduled_start = next_open.start_time
            head.scheduled_end = next_open.end_time
            head_booking = db.get(Booking, head.booking_id)
            if head_booking is not None:
                head_booking.slot_id = next_open.id
            db.flush()  # release head's old slot from the unique bookings.slot_id
            seat_slot = head_slot  # stays BOOKED; reused for the emergency
            bumped_to = {
                "patient_name": head.patient.full_name if head.patient else "Patient",
                "new_time": next_open.start_time.isoformat(),
            }
            if head.patient:
                messaging.send_to_patient(
                    head.patient,
                    f"Sorry — an emergency came up. Your appointment is moved to "
                    f"{next_open.start_time.astimezone(WAT):%H:%M}. Apologies for the change.",
                )

    if seat_slot is None:
        # Nobody to bump (or no later slot): take the nearest open slot today.
        seat_slot = db.execute(
            select(Slot)
            .where(
                Slot.provider_id == provider.id,
                Slot.status == SlotStatus.OPEN,
                Slot.start_time >= start,
                Slot.start_time < end,
            )
            .order_by(Slot.start_time)
            .limit(1)
            .with_for_update()
        ).scalar_one_or_none()
        if seat_slot is None:
            raise ConflictError("No room today — no open slots to seat the emergency")
        seat_slot.status = SlotStatus.BOOKED
        seat_slot.hold_expires_at = None

    # Seat the emergency patient: confirmed booking + scheduled appointment (paid at desk).
    amount = seat_slot.service.price_amount if seat_slot.service else 0
    currency = seat_slot.service.currency if seat_slot.service else "NGN"
    booking = Booking(
        patient_id=emg.patient_id,
        slot_id=seat_slot.id,
        service_id=seat_slot.service_id,
        status=BookingStatus.CONFIRMED,
        amount=amount,
        currency=currency,
    )
    db.add(booking)
    db.flush()

    seated = Appointment(
        booking_id=booking.id,
        patient_id=emg.patient_id,
        provider_id=seat_slot.provider_id,
        slot_id=seat_slot.id,
        scheduled_start=seat_slot.start_time,
        scheduled_end=seat_slot.end_time,
        status=AppointmentStatus.SCHEDULED,
        notes=f"Emergency: {emg.category} — {emg.description}",
    )
    db.add(seated)
    emg.status = EmergencyStatus.ACKNOWLEDGED
    db.commit()
    db.refresh(seated)

    return {
        "emergency": _serialize(emg),
        "seated": {"id": str(seated.id), "slot_time": seated.scheduled_start.isoformat()},
        "bumped_to": bumped_to,
    }
