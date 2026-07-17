import uuid
from datetime import date as _date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.appointment import (
    AppointmentComplete,
    AppointmentHold,
    AppointmentRead,
    AppointmentReschedule,
    ChannelBookingCreate,
    SlotSummary,
)
from app.schemas.dashboard import (
    CloseVisitRequest,
    DashboardFollowUpRequest,
    DayRow,
    QueueItem,
)
from app.models.slot import Slot
from app.services import appointments as appointments_service
from app.services import bookings as bookings_service
from app.services import dashboard as dashboard_service
from app.services import patients as patients_service
from app.services.exceptions import NotFoundError, SlotUnavailableError

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


@router.get("", response_model=list[QueueItem], summary="Provider queue (doctor / lab board)")
def provider_queue(
    provider_id: str,
    date: _date | None = None,
    db: Session = Depends(get_db),
) -> list[QueueItem]:
    """Today's live queue for a provider (accepts a slug like ``prov_ade`` or a UUID).

    Rows are enriched for the board: position, is_next, patient, visit type, and any
    home reading / test details. Paid bookings from the channels appear on their own.
    """
    try:
        rows = dashboard_service.provider_queue(db, provider_id, date)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return [QueueItem(**r) for r in rows]


@router.get("/day", response_model=list[DayRow], summary="Day summary (cashier)")
def appointments_day(date: _date | None = None, db: Session = Depends(get_db)) -> list[DayRow]:
    """Every appointment on the day (all providers) plus still-owing holds."""
    return [DayRow(**r) for r in dashboard_service.day_summary(db, date)]


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
    "/{appointment_id}/close",
    summary="Close a visit (doctor / lab): done / follow-up / admitted",
)
def close_visit(
    appointment_id: uuid.UUID,
    payload: CloseVisitRequest | None = None,
    db: Session = Depends(get_db),
):
    """Tick Done / Admitted (and, for the lab, set the collection date). Advances the queue."""
    payload = payload or CloseVisitRequest()
    return dashboard_service.close_visit(
        db, appointment_id, state=payload.state, collection_date=payload.collection_date
    )


@router.post(
    "/{appointment_id}/follow-up",
    status_code=201,
    summary="Book a follow-up appointment",
)
def create_follow_up(
    appointment_id: uuid.UUID,
    payload: DashboardFollowUpRequest,
    db: Session = Depends(get_db),
):
    """Book a follow-up for the same patient off this appointment (clinician action).

    Accepts ``slot_id`` (dashboard) or ``new_slot_id``; ``service_id`` may be a slug.
    Returns the booked appointment with ``provider_name`` / ``service_name`` for the UI.
    """
    slot_id = payload.slot_id or payload.new_slot_id
    if slot_id is None:
        raise HTTPException(status_code=422, detail="slot_id is required")

    service_uuid = None
    if payload.service_id:
        try:
            service_uuid = dashboard_service.resolve_service(db, payload.service_id).id
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    appt = appointments_service.create_follow_up(
        db, appointment_id, new_slot_id=slot_id, service_id=service_uuid, notes=None
    )
    slot = db.get(Slot, appt.slot_id)
    provider_name = slot.provider_name if slot else None
    service_name = slot.service.name if slot and slot.service else None
    return {
        "id": str(appt.id),
        "provider_name": provider_name,
        "service_name": service_name,
        "slot_time": appt.scheduled_start.isoformat(),
        "status": "confirmed",
    }
