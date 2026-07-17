import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import EmergencyStatus

if TYPE_CHECKING:
    from app.models.patient import Patient


class Emergency(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An emergency alert raised by a patient over a channel (PRD §8.6).

    Carries a triage category plus a one-sentence description; the doctor board
    surfaces it immediately and either seats the patient now ("make room") or marks
    it handled. Never a substitute for clinical triage.
    """

    __tablename__ = "emergencies"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[EmergencyStatus] = mapped_column(
        SAEnum(EmergencyStatus, name="emergency_status"),
        nullable=False,
        default=EmergencyStatus.OPEN,
        index=True,
    )

    patient: Mapped["Patient"] = relationship()
