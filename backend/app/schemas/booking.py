import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import BookingStatus
from app.schemas.common import ORMModel


class BookingCreate(BaseModel):
    """Create a booking against a (held or open) slot.

    On Day 2 this holds the slot, snapshots the price, and returns the booking
    as PENDING_PAYMENT together with a payment init payload.
    """

    patient_id: uuid.UUID
    slot_id: uuid.UUID
    service_id: uuid.UUID | None = None


class BookingRead(ORMModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    slot_id: uuid.UUID
    service_id: uuid.UUID | None
    status: BookingStatus
    amount: int
    currency: str
    expires_at: datetime | None
    created_at: datetime


class PaymentInit(BaseModel):
    """Everything the client needs to redirect the customer to Paystack."""

    reference: str
    authorization_url: str | None
    access_code: str | None


class BookingCreateResponse(BaseModel):
    booking: BookingRead
    payment: PaymentInit
