import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.enums import AppointmentStatus
from app.schemas.appointment import (
    AppointmentComplete,
    AppointmentRead,
    AppointmentReschedule,
    FollowUpCreate,
)
from app.services import appointments as appointments_service

router = APIRouter(prefix="/appointments", tags=["appointments"])


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
    response_model=AppointmentRead,
    summary="Cancel an appointment",
)
def cancel_appointment(appointment_id: uuid.UUID, db: Session = Depends(get_db)) -> AppointmentRead:
    """Cancel a scheduled appointment and release its slot."""
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
