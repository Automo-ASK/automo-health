import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import SlotStatus

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.provider import Provider
    from app.models.service import Service


class Slot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A discrete, bookable window of a provider's time.

    Concurrency model (Day 2):
      * `status` transitions OPEN -> HELD -> BOOKED (or back to OPEN on expiry).
      * `hold_expires_at` is set when a slot is HELD; a Celery beat task releases
        stale holds back to OPEN.
      * `version_id` gives optimistic locking; the hold routine additionally uses
        `SELECT ... FOR UPDATE` to serialize concurrent hold attempts.
    """

    __tablename__ = "slots"
    __table_args__ = (
        UniqueConstraint("provider_id", "start_time", name="uq_slot_provider_start"),
        Index("ix_slots_status_start", "status", "start_time"),
        Index("ix_slots_hold_expiry", "hold_expires_at"),
    )

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    service_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id", ondelete="SET NULL"), index=True, nullable=True
    )

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status: Mapped[SlotStatus] = mapped_column(
        SAEnum(SlotStatus, name="slot_status"), nullable=False, default=SlotStatus.OPEN, index=True
    )
    hold_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Optimistic-lock version counter, bumped automatically on every UPDATE.
    version_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    provider: Mapped["Provider"] = relationship(back_populates="slots")
    service: Mapped["Service | None"] = relationship(back_populates="slots")
    booking: Mapped["Booking | None"] = relationship(back_populates="slot", uselist=False)

    __mapper_args__ = {"version_id_col": version_id}

    @property
    def provider_name(self) -> str | None:
        return self.provider.full_name if self.provider else None

    @property
    def duration_minutes(self) -> int | None:
        if self.service is not None:
            return self.service.duration_minutes
        delta = self.end_time - self.start_time
        return int(delta.total_seconds() / 60)
