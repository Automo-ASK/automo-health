import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import LabOrderStatus

if TYPE_CHECKING:
    from app.models.appointment import Appointment
    from app.models.patient import Patient


class LabOrder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A lab test ordered off the back of an appointment (Day 6).

    Lifecycle: ORDERED -> COLLECTED -> RESULTED (or CANCELLED). The `result` text
    is filled in when a lab tech enters the outcome.
    """

    __tablename__ = "lab_orders"

    appointment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), index=True, nullable=False
    )

    test_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[LabOrderStatus] = mapped_column(
        SAEnum(LabOrderStatus, name="lab_order_status"),
        nullable=False,
        default=LabOrderStatus.ORDERED,
        index=True,
    )

    # Optional charge for the test, in minor units (kobo). Collected by the cashier.
    price_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="NGN")

    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    resulted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    appointment: Mapped["Appointment"] = relationship()
    patient: Mapped["Patient"] = relationship()
