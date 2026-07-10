import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AppointmentStatus

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.patient import Patient


class Appointment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A confirmed, scheduled encounter. Created when a booking is CONFIRMED."""

    __tablename__ = "appointments"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    slot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("slots.id", ondelete="RESTRICT"), unique=True, index=True, nullable=False
    )

    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status: Mapped[AppointmentStatus] = mapped_column(
        SAEnum(AppointmentStatus, name="appointment_status"),
        nullable=False,
        default=AppointmentStatus.SCHEDULED,
        index=True,
    )

    patient: Mapped["Patient"] = relationship(back_populates="appointments")
    booking: Mapped["Booking"] = relationship(back_populates="appointment")
