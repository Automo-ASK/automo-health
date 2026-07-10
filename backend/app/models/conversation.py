import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Short-term context store for SMS and WhatsApp AI conversations.

    USSD sessions are too short-lived and stateless to warrant a DB row — handle
    those with the accumulated ``text`` field that Africa's Talking sends on each
    request.  This table is for channels where a multi-turn conversation persists
    across separate inbound messages (SMS, WhatsApp).
    """

    __tablename__ = "conversations"

    phone: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="en")

    # Arbitrary booking-in-progress state (service_type, slot_id, etc.)
    state: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )

    # Last N turns of the conversation for LLM context window
    history: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )

    # Optional link to a patient record once identity is known
    patient_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )

    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Free-text snapshot of the last outbound reply (for debugging / audit)
    last_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
