import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import BookingStatus

if TYPE_CHECKING:
    from app.models.appointment import Appointment
    from app.models.patient import Patient
    from app.models.payment import Payment
    from app.models.slot import Slot


class Booking(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A patient's intent to take a slot. Created as PENDING_PAYMENT (Day 2).

    A booking becomes CONFIRMED once its payment succeeds, at which point the
    slot is marked BOOKED and an Appointment is created. It EXPIRES if payment
    is not completed before `expires_at`.
    """

    __tablename__ = "bookings"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    slot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("slots.id", ondelete="RESTRICT"), unique=True, index=True, nullable=False
    )
    service_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id", ondelete="SET NULL"), index=True, nullable=True
    )

    status: Mapped[BookingStatus] = mapped_column(
        SAEnum(BookingStatus, name="booking_status"),
        nullable=False,
        default=BookingStatus.PENDING_PAYMENT,
        index=True,
    )

    # Snapshot of the amount owed at booking time (minor units, e.g. kobo).
    amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="NGN")

    # Deadline for completing payment; enforced by a Celery expiry task.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    patient: Mapped["Patient"] = relationship(back_populates="bookings")
    slot: Mapped["Slot"] = relationship(back_populates="booking")
    payment: Mapped["Payment | None"] = relationship(back_populates="booking", uselist=False)
    appointment: Mapped["Appointment | None"] = relationship(back_populates="booking", uselist=False)
