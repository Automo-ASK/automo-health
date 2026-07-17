import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Text
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

    # Clinician notes; set on completion ("tick Done") or when creating a follow-up.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Dashboard context (PRD §8–9). Virtual consults carry the patient-reported
    # home reading; lab visits carry the test details and, once results are ready,
    # the collection date the patient is told to come in on.
    home_reading: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    collection_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Set when this appointment was created as a follow-up of an earlier one.
    parent_appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("appointments.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    patient: Mapped["Patient"] = relationship(back_populates="appointments")
    booking: Mapped["Booking"] = relationship(back_populates="appointment")
    parent: Mapped["Appointment | None"] = relationship(
        remote_side="Appointment.id", backref="follow_ups"
    )
