import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import PaymentProvider, PaymentStatus
from app.schemas.common import ORMModel


class PaymentRead(ORMModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    provider: PaymentProvider
    status: PaymentStatus
    amount: int
    currency: str
    reference: str
    authorization_url: str | None
    access_code: str | None
    paid_at: datetime | None
    created_at: datetime


class PaymentInitializeRequest(BaseModel):
    """Initialize (or re-initialize) payment for an existing booking."""

    booking_id: uuid.UUID


class PaymentVerifyResponse(BaseModel):
    reference: str
    status: PaymentStatus
    booking_id: uuid.UUID


class PaystackWebhookEvent(BaseModel):
    """Loose envelope for a Paystack webhook payload."""

    event: str
    data: dict
