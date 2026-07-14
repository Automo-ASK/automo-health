import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import AppointmentStatus
from app.schemas.common import ORMModel


class AppointmentRead(ORMModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    patient_id: uuid.UUID
    provider_id: uuid.UUID
    slot_id: uuid.UUID
    scheduled_start: datetime
    scheduled_end: datetime
    status: AppointmentStatus
    notes: str | None = None
    completed_at: datetime | None = None
    parent_appointment_id: uuid.UUID | None = None
    created_at: datetime


class AppointmentComplete(BaseModel):
    """Tick Done — optionally attach clinician notes."""

    notes: str | None = None


class AppointmentReschedule(BaseModel):
    new_slot_id: uuid.UUID


class FollowUpCreate(BaseModel):
    new_slot_id: uuid.UUID
    service_id: uuid.UUID | None = None
    notes: str | None = None
