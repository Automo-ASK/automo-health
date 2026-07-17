from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.service import Service
    from app.models.slot import Slot


class Provider(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A practitioner/clinician that patients book appointments with."""

    __tablename__ = "providers"

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    # Stable human-readable identifier (e.g. "prov_ade") the dashboards address a
    # provider by, so their config survives re-seeds that regenerate UUIDs.
    slug: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    specialty: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")

    services: Mapped[list["Service"]] = relationship(back_populates="provider")
    slots: Mapped[list["Slot"]] = relationship(back_populates="provider")
