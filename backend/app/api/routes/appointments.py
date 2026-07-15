import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.enums import AppointmentStatus
from app.schemas.appointment import (
    AppointmentComplete,
    AppointmentHold,
    AppointmentRead,
    AppointmentReschedule,
    ChannelBookingCreate,
    FollowUpCreate,
    SlotSummary,
)
from app.models.slot import Slot
from app.services import appointments as appointments_service
from app.services import bookings as bookings_service
from app.services import patients as patients_service
from app.services.exceptions import SlotUnavailableError

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.post(
    "",
    response_model=AppointmentHold,
    status_code=status.HTTP_201_CREATED,
    summary="Create a booking hold (channel intake)",
)
def create_channel_booking(
    payload: ChannelBookingCreate, db: Session = Depends(get_db)
) -> AppointmentHold:
    """Find-or-create the patient by phone, hold the slot, initialize payment.

    Used by the WhatsApp (and SMS) channel. Returns an ``AppointmentHold`` with
    ``id`` set to the booking UUID so the channel can use it as the appointment
    reference for payment polling and cancellation.

    Raises 409 if the slot is no longer available.
    """
    patient = patients_service.get_or_create_by_phone(db, payload.patient.phone)
    if payload.patient.name and not patient.full_name:
        patient.full_name = payload.patient.name
        db.flush()

    try:
        booking, _payment = bookings_service.create_booking(
            db,
            patient_id=patient.id,
            slot_id=payload.slot_id,
            service_id=payload.service_id,
        )
    except SlotUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    slot = db.get(Slot, payload.slot_id)
    slot_summary = None
    if slot is not None:
        slot_summary = SlotSummary(
            id=slot.id,
            start_time=slot.start_time,
            provider_name=slot.provider_name,
        )

    return AppointmentHold(
        id=booking.id,
        status=booking.status.value,
        type=payload.type,
        patient_id=patient.id,
        slot=slot_summary,
        amount=booking.amount,
        consultation_fee=booking.amount,
        platform_fee=0,
        currency=booking.currency,
        hold_expires_at=booking.expires_at,
    )


@router.get("", response_model=list[AppointmentRead], summary="List appointments")
def list_appointments(
    patient_id: uuid.UUID | None = None,
    provider_id: uuid.UUID | None = None,
    status: AppointmentStatus | None = None,
    db: Session = Depends(get_db),
) -> list[AppointmentRead]:
    """List appointments, optionally filtered by patient, provider, or status."""
    return appointments_service.list_appointments(
        db, patient_id=patient_id, provider_id=provider_id, status=status
    )


@router.get("/{appointment_id}", response_model=AppointmentRead, summary="Get an appointment")
def get_appointment(appointment_id: uuid.UUID, db: Session = Depends(get_db)) -> AppointmentRead:
    return appointments_service.get_appointment(db, appointment_id)


@router.post(
    "/{appointment_id}/complete",
    response_model=AppointmentRead,
    summary="Mark an appointment done",
)
def complete_appointment(
    appointment_id: uuid.UUID,
    payload: AppointmentComplete | None = None,
    db: Session = Depends(get_db),
) -> AppointmentRead:
    """Tick Done — mark the appointment COMPLETED with optional clinician notes."""
    notes = payload.notes if payload else None
    return appointments_service.complete_appointment(db, appointment_id, notes=notes)


@router.post(
    "/{appointment_id}/no-show",
    response_model=AppointmentRead,
    summary="Mark an appointment as a no-show",
)
def no_show_appointment(appointment_id: uuid.UUID, db: Session = Depends(get_db)) -> AppointmentRead:
    return appointments_service.mark_no_show(db, appointment_id)


@router.post(
    "/{appointment_id}/cancel",
    summary="Cancel an appointment or booking hold",
)
def cancel_appointment(appointment_id: uuid.UUID, db: Session = Depends(get_db)):
    """Cancel a scheduled appointment and release its slot.

    Also accepts a booking UUID from the channel flow (PENDING_PAYMENT hold) so
    the WhatsApp channel can release a hold without needing a separate bookings endpoint.
    """
    from app.models.booking import Booking as BookingModel
    from sqlalchemy import select as _select
    # Check bookings first (WhatsApp channel flow uses booking IDs as appointment refs).
    booking = db.execute(
        _select(BookingModel).where(BookingModel.id == appointment_id)
    ).scalar_one_or_none()
    if booking is not None:
        bookings_service.cancel_booking(db, appointment_id)
        return {"id": str(appointment_id), "status": "cancelled"}
    # Fall back to confirmed appointment.
    return appointments_service.cancel_appointment(db, appointment_id)


@router.post(
    "/{appointment_id}/reschedule",
    response_model=AppointmentRead,
    summary="Reschedule an appointment onto a new slot",
)
def reschedule_appointment(
    appointment_id: uuid.UUID,
    payload: AppointmentReschedule,
    db: Session = Depends(get_db),
) -> AppointmentRead:
    return appointments_service.reschedule_appointment(
        db, appointment_id, new_slot_id=payload.new_slot_id
    )


@router.post(
    "/{appointment_id}/follow-up",
    response_model=AppointmentRead,
    status_code=201,
    summary="Book a follow-up appointment",
)
def create_follow_up(
    appointment_id: uuid.UUID,
    payload: FollowUpCreate,
    db: Session = Depends(get_db),
) -> AppointmentRead:
    """Book a follow-up for the same patient off this appointment (clinician action)."""
    return appointments_service.create_follow_up(
        db,
        appointment_id,
        new_slot_id=payload.new_slot_id,
        service_id=payload.service_id,
        notes=payload.notes,
    )
