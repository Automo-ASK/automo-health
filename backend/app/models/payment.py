import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import PaymentProvider, PaymentStatus

if TYPE_CHECKING:
    from app.models.booking import Booking


class Payment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A payment attempt against a booking, brokered through Paystack.

    Paystack flow:
      1. Initialize transaction -> returns `reference`, `authorization_url`, `access_code`.
      2. Customer pays on the hosted page (authorization_url).
      3. Verify (via callback and/or webhook) flips status to SUCCESS/FAILED.
    """

    __tablename__ = "payments"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )

    provider: Mapped[PaymentProvider] = mapped_column(
        SAEnum(PaymentProvider, name="payment_provider"),
        nullable=False,
        default=PaymentProvider.PAYSTACK,
    )
    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus, name="payment_status"),
        nullable=False,
        default=PaymentStatus.PENDING,
        index=True,
    )

    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # minor units (kobo)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="NGN")

    # Paystack transaction identifiers.
    reference: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    authorization_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_code: Mapped[str | None] = mapped_column(String(100), nullable=True)

    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Raw gateway payload from the last verify/webhook, for audit/debugging.
    gateway_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    booking: Mapped["Booking"] = relationship(back_populates="payment")
