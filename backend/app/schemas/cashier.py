import uuid

from pydantic import BaseModel

from app.models.enums import BookingStatus
from app.schemas.common import ORMModel


class OutstandingBooking(ORMModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    slot_id: uuid.UUID
    status: BookingStatus
    amount: int
    currency: str


class CashCollectRequest(BaseModel):
    booking_id: uuid.UUID
    amount: int  # minor units (kobo); must match the booking amount exactly
    reference: str | None = None  # optional desk receipt number


class CashCollectResponse(BaseModel):
    status: str
    detail: str
    booking_id: uuid.UUID | None = None
    appointment_id: uuid.UUID | None = None
