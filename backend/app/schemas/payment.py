import uuid
from datetime import datetime

from pydantic import BaseModel, model_validator

from app.models.enums import PaymentProvider, PaymentStatus, VirtualAccountStatus
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


class VirtualAccountRequest(BaseModel):
    booking_id: uuid.UUID


class VirtualAccountRead(ORMModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    provider: PaymentProvider
    status: VirtualAccountStatus
    account_number: str
    account_name: str
    bank_name: str | None
    expected_amount: int
    currency: str
    expires_at: datetime | None


class PaymentLinkRequest(BaseModel):
    """Accept either booking_id (internal callers) or appointment_id (WhatsApp channel)."""

    booking_id: uuid.UUID | None = None
    appointment_id: uuid.UUID | None = None  # WhatsApp alias for booking_id
    include_virtual_account: bool = True

    @model_validator(mode="after")
    def resolve_booking_id(self) -> "PaymentLinkRequest":
        if self.booking_id is None and self.appointment_id is not None:
            self.booking_id = self.appointment_id
        if self.booking_id is None:
            raise ValueError("Either booking_id or appointment_id is required")
        return self


class PaymentLinkResponse(BaseModel):
    """In-chat-shareable payment payload.

    Includes both the original internal fields and WhatsApp-channel aliases so
    both callers get everything they need from a single endpoint.
    """

    booking_id: uuid.UUID
    amount: int
    currency: str
    reference: str | None
    checkout_url: str | None
    virtual_account: VirtualAccountRead | None
    chat_message: str
    # WhatsApp-compatible shape
    payment_id: uuid.UUID | None = None
    method: str = "link"
    url: str | None = None  # same as checkout_url
    expires_at: datetime | None = None


class ReconcileResponse(BaseModel):
    status: str
    detail: str
    booking_id: uuid.UUID | None = None
    appointment_id: uuid.UUID | None = None


class PaymentVerifyResponse(BaseModel):
    reference: str
    status: str
    detail: str
    booking_id: uuid.UUID | None = None
    appointment_id: uuid.UUID | None = None


class PaystackWebhookEvent(BaseModel):
    """Loose envelope for a Paystack webhook payload."""

    event: str
    data: dict
