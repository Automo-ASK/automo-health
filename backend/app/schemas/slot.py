import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import SlotStatus
from app.schemas.common import ORMModel


class SlotBase(BaseModel):
    provider_id: uuid.UUID
    service_id: uuid.UUID | None = None
    start_time: datetime
    end_time: datetime


class SlotCreate(SlotBase):
    """Create a single slot (open by default)."""


class SlotGenerateRequest(BaseModel):
    """Generate a range of slots for a provider from a simple window spec."""

    provider_id: uuid.UUID
    service_id: uuid.UUID | None = None
    range_start: datetime
    range_end: datetime
    slot_minutes: int = Field(default=30, ge=5, le=480)


class SlotRead(ORMModel):
    id: uuid.UUID
    provider_id: uuid.UUID
    service_id: uuid.UUID | None
    start_time: datetime
    end_time: datetime
    status: SlotStatus
    hold_expires_at: datetime | None


class SlotAvailabilityQuery(BaseModel):
    provider_id: uuid.UUID | None = None
    service_id: uuid.UUID | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    only_open: bool = True


class SlotHoldRequest(BaseModel):
    """Place a temporary hold on an OPEN slot."""

    patient_id: uuid.UUID


class SlotHoldResponse(ORMModel):
    id: uuid.UUID
    status: SlotStatus
    hold_expires_at: datetime | None
