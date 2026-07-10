import uuid

from fastapi import APIRouter, HTTPException, status

from app.schemas.appointment import AppointmentRead

router = APIRouter(prefix="/appointments", tags=["appointments"])

_NOT_IMPLEMENTED = "Stub endpoint — appointment lifecycle lands on Day 2+."


@router.get("", response_model=list[AppointmentRead], summary="List appointments")
def list_appointments(
    patient_id: uuid.UUID | None = None,
    provider_id: uuid.UUID | None = None,
) -> list[AppointmentRead]:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)


@router.get("/{appointment_id}", response_model=AppointmentRead, summary="Get an appointment")
def get_appointment(appointment_id: uuid.UUID) -> AppointmentRead:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)


@router.post("/{appointment_id}/cancel", response_model=AppointmentRead, summary="Cancel an appointment")
def cancel_appointment(appointment_id: uuid.UUID) -> AppointmentRead:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)
