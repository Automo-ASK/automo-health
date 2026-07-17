import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.provider import Provider
    from app.models.slot import Slot


class Service(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A bookable service offered by a provider (e.g. 'General Consultation')."""

    __tablename__ = "services"

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Stable human-readable identifier (e.g. "svc_consult") the dashboards address a
    # service by, independent of the generated UUID primary key.
    slug: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    # Monetary amounts are stored as integer minor units (e.g. kobo for NGN).
    price_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="NGN")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    provider: Mapped["Provider"] = relationship(back_populates="services")
    slots: Mapped[list["Slot"]] = relationship(back_populates="service")
