import uuid
from datetime import datetime
from typing import Literal

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


# ---- WhatsApp channel booking ------------------------------------------------

class ChannelPatientInput(BaseModel):
    phone: str
    name: str
    preferred_language: str = "en"
    preferred_channel: str = "whatsapp"
    consent: bool = True


class ChannelBookingCreate(BaseModel):
    """Payload sent by the WhatsApp channel to create a booking+hold."""

    slot_id: uuid.UUID
    service_id: uuid.UUID
    type: Literal["physical", "virtual", "lab"] = "physical"
    patient: ChannelPatientInput
    channel: str = "whatsapp"


class SlotSummary(BaseModel):
    id: uuid.UUID
    start_time: datetime
    provider_name: str | None = None


class AppointmentHold(BaseModel):
    """Returned when a channel creates a booking (PENDING_PAYMENT hold)."""

    id: uuid.UUID           # booking id — used as appointment reference in the channel
    status: str
    type: str
    patient_id: uuid.UUID
    slot: SlotSummary | None = None
    amount: int
    consultation_fee: int
    platform_fee: int
    currency: str
    hold_expires_at: datetime | None
