import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import PaymentProvider, VirtualAccountStatus

if TYPE_CHECKING:
    from app.models.booking import Booking


class VirtualAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A dedicated bank account (NUBAN) provisioned per booking.

    The customer pays by bank transfer into this account; the provider then fires
    a webhook we reconcile against the booking. `expected_amount` is snapshotted so
    reconciliation can enforce an exact-amount match, and `customer_code` /
    `account_number` let us resolve the owning booking from a transfer event.
    """

    __tablename__ = "virtual_accounts"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )

    provider: Mapped[PaymentProvider] = mapped_column(
        SAEnum(PaymentProvider, name="payment_provider"),
        nullable=False,
        default=PaymentProvider.PAYSTACK,
    )
    status: Mapped[VirtualAccountStatus] = mapped_column(
        SAEnum(VirtualAccountStatus, name="virtual_account_status"),
        nullable=False,
        default=VirtualAccountStatus.ACTIVE,
        index=True,
    )

    # Bank account details shown to the customer.
    account_number: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    account_name: Mapped[str] = mapped_column(String(255), nullable=False)
    bank_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Provider identifiers used to resolve the booking from a webhook.
    customer_code: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)

    # Snapshot for exact-amount reconciliation (minor units, e.g. kobo).
    expected_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="NGN")

    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    booking: Mapped["Booking"] = relationship(back_populates="virtual_account")
