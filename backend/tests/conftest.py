"""Shared test fixtures."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import ChannelType


@pytest.fixture()
def client():
    """FastAPI test client."""
    return TestClient(app)


# ── Minimal ORM stubs ─────────────────────────────────────────────────────────

def make_conversation(
    *,
    phone: str = "+2348012345678",
    channel: str = ChannelType.SMS,
    language: str = "en",
    state: dict | None = None,
    history: list | None = None,
    last_reply: str | None = None,
) -> MagicMock:
    conv = MagicMock()
    conv.id = uuid.uuid4()
    conv.phone = phone
    conv.channel = channel
    conv.language = language
    conv.state = state or {}
    conv.history = history or []
    conv.last_reply = last_reply
    conv.last_message_at = datetime.now(timezone.utc)
    return conv


@pytest.fixture()
def mock_db():
    """Session mock that returns a fresh conversation by default."""
    db = MagicMock()
    conv = make_conversation()

    result = MagicMock()
    result.scalar_one_or_none.return_value = conv
    db.execute.return_value = result

    return db, conv


@pytest.fixture(autouse=True)
def no_at_sms():
    """Prevent any real SMS from being sent in tests."""
    with patch("app.services.africastalking.send_sms") as mock_send:
        mock_send.return_value = {"SMSMessageData": {"Recipients": []}}
        yield mock_send
