"""Day 7 — SMS inbound route edge case tests.

Tests cover the full state machine: commands, slot-offered fast path,
AI paths, human handoff, and the misunderstood-count escalation.

Uses app.dependency_overrides to inject a mock DB session (the correct way
to override FastAPI generator-based dependencies in tests), and patches
the AI service and AT SMS calls so no real services are required.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.core.database import get_db
from app.main import app
from app.models.enums import ChannelType, Intent, Language, SuggestedAction
from app.schemas.ai_service import AIInterpretResponse, ExtractedEntities


# ── Shared helpers ────────────────────────────────────────────────────────────

PHONE = "+2348012345678"
TO    = "AUTOMO"
DATE  = "2026-07-14 09:00:00"


def _form(text: str, *, phone: str = PHONE) -> dict[str, str]:
    return {"from": phone, "to": TO, "text": text, "date": DATE}


def _make_conv(
    *,
    language: str = "en",
    state: dict | None = None,
    history: list | None = None,
) -> MagicMock:
    conv = MagicMock()
    conv.id = uuid.uuid4()
    conv.phone = PHONE
    conv.channel = ChannelType.SMS
    conv.language = language
    conv.state = dict(state or {})
    conv.history = list(history or [])
    conv.last_reply = None
    conv.last_message_at = datetime.now(timezone.utc)
    return conv


def _make_db(conv: MagicMock) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = conv
    db.execute.return_value = result
    return db


def _ai_response(
    *,
    intent: Intent = Intent.UNKNOWN,
    language: Language = Language.EN,
    service_type: str | None = None,
    suggested_action: SuggestedAction | None = None,
    reply: str = "How can I help you?",
) -> AIInterpretResponse:
    return AIInterpretResponse(
        intent=intent,
        language=language,
        entities=ExtractedEntities(service_type=service_type),
        reply=reply,
        confidence=0.9,
        needs_clarification=False,
        suggested_action=suggested_action,
    )


@contextmanager
def _inject_db(conv: MagicMock):
    """Override the get_db dependency for the duration of a single test."""
    db = _make_db(conv)

    def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    try:
        yield db
    finally:
        app.dependency_overrides.pop(get_db, None)


def _post(client, text: str, *, phone: str = PHONE):
    return client.post(
        "/api/v1/channels/sms/inbound",
        data=_form(text, phone=phone),
    )


# ── RESET command ─────────────────────────────────────────────────────────────

def test_reset_command_clears_state_and_replies(client):
    """RESET clears slot_offered stage without calling the AI."""
    conv = _make_conv(
        state={"stage": "slot_offered", "service_key": "1",
               "slot_label": "Mon 14 Jul, 09:00 AM WAT"},
    )
    with (
        _inject_db(conv),
        patch("app.services.africastalking.send_sms") as mock_sms,
        patch("app.services.ai_service.interpret") as mock_ai,
    ):
        resp = _post(client, "RESET")

    assert resp.status_code == 200
    mock_ai.assert_not_called()
    sent_text = mock_sms.call_args[0][0]
    assert any(kw in sent_text.lower() for kw in ("fresh", "start", "wahala", "bẹ̀rẹ̀", "kò burú"))


@pytest.mark.parametrize("text", ["reset", "RESET", "start over", "restart"])
def test_reset_variants_skip_ai(client, text):
    conv = _make_conv()
    with (
        _inject_db(conv),
        patch("app.services.africastalking.send_sms"),
        patch("app.services.ai_service.interpret") as mock_ai,
    ):
        resp = _post(client, text)

    assert resp.status_code == 200
    mock_ai.assert_not_called()


# ── HELP command ──────────────────────────────────────────────────────────────

def test_help_command_returns_clinic_info(client):
    conv = _make_conv()
    with (
        _inject_db(conv),
        patch("app.services.africastalking.send_sms") as mock_sms,
        patch("app.services.ai_service.interpret") as mock_ai,
    ):
        resp = _post(client, "help")

    assert resp.status_code == 200
    mock_ai.assert_not_called()
    sent_text = mock_sms.call_args[0][0]
    assert "0800" in sent_text


def test_help_does_not_change_conversation_stage(client):
    conv = _make_conv(state={"stage": "slot_offered", "service_key": "1"})
    with (
        _inject_db(conv),
        patch("app.services.africastalking.send_sms"),
        patch("app.services.ai_service.interpret") as mock_ai,
    ):
        _post(client, "info")

    mock_ai.assert_not_called()
    # HELP never clears the slot_offered state — patient can still reply YES
    assert conv.state.get("stage") == "slot_offered"


# ── Slot-offered fast path ────────────────────────────────────────────────────

def test_slot_offered_yes_confirms_booking(client):
    conv = _make_conv(
        state={"stage": "slot_offered", "service_key": "1",
               "slot_label": "Mon 14 Jul, 09:00 AM WAT"},
    )
    with (
        _inject_db(conv),
        patch("app.services.africastalking.send_sms") as mock_sms,
        patch("app.services.sms_booking.confirm_from_sms",
              return_value="Booking confirmed! Check your SMS for payment details."),
        patch("app.services.ai_service.interpret") as mock_ai,
    ):
        resp = _post(client, "yes")

    assert resp.status_code == 200
    mock_ai.assert_not_called()
    sent_text = mock_sms.call_args[0][0]
    assert "Booking confirmed" in sent_text


def test_slot_offered_no_sends_decline(client):
    conv = _make_conv(
        state={"stage": "slot_offered", "service_key": "1",
               "slot_label": "Mon 14 Jul, 09:00 AM WAT"},
    )
    with (
        _inject_db(conv),
        patch("app.services.africastalking.send_sms") as mock_sms,
        patch("app.services.ai_service.interpret") as mock_ai,
    ):
        resp = _post(client, "no")

    assert resp.status_code == 200
    mock_ai.assert_not_called()
    sent_text = mock_sms.call_args[0][0]
    assert any(kw in sent_text.lower()
               for kw in ("no problem", "wahala", "kò burú", "problem"))


def test_slot_offered_unclear_re_asks_same_slot(client):
    slot_label = "Mon 14 Jul, 09:00 AM WAT"
    conv = _make_conv(
        state={"stage": "slot_offered", "service_key": "1", "slot_label": slot_label},
    )
    ai_resp = _ai_response(intent=Intent.UNKNOWN, reply="Sorry, what did you mean?")
    with (
        _inject_db(conv),
        patch("app.services.africastalking.send_sms") as mock_sms,
        patch("app.services.ai_service.interpret", return_value=ai_resp),
    ):
        resp = _post(client, "huh?")

    assert resp.status_code == 200
    sent_text = mock_sms.call_args[0][0]
    assert slot_label in sent_text


# ── AI show_slots path ────────────────────────────────────────────────────────

def test_ai_show_slots_offers_real_slot(client):
    conv = _make_conv()
    ai_resp = _ai_response(
        intent=Intent.BOOK,
        service_type="consultation",
        suggested_action=SuggestedAction.SHOW_SLOTS,
    )
    with (
        _inject_db(conv),
        patch("app.services.africastalking.send_sms") as mock_sms,
        patch("app.services.ai_service.interpret", return_value=ai_resp),
        patch("app.services.ussd_booking.next_slot_label",
              return_value="Mon 14 Jul, 09:00 AM WAT"),
    ):
        resp = _post(client, "I want to see a doctor")

    assert resp.status_code == 200
    sent_text = mock_sms.call_args[0][0]
    assert "09:00" in sent_text
    assert "YES" in sent_text
    assert conv.state.get("stage") == "slot_offered"


# ── Human handoff ─────────────────────────────────────────────────────────────

def test_ai_human_handoff_sends_clinic_contact(client):
    conv = _make_conv()
    ai_resp = _ai_response(
        suggested_action=SuggestedAction.HUMAN_HANDOFF,
        reply="Let me get a human for you.",
    )
    with (
        _inject_db(conv),
        patch("app.services.africastalking.send_sms") as mock_sms,
        patch("app.services.ai_service.interpret", return_value=ai_resp),
    ):
        resp = _post(client, "some weird message")

    assert resp.status_code == 200
    sent_text = mock_sms.call_args[0][0]
    assert "0800" in sent_text


def test_three_unclear_turns_triggers_handoff(client):
    """After 3 consecutive UNKNOWN turns with no service extracted, escalate."""
    conv = _make_conv(state={"misunderstood_count": 2})
    ai_resp = _ai_response(intent=Intent.UNKNOWN, reply="I'm not sure what you need.")
    with (
        _inject_db(conv),
        patch("app.services.africastalking.send_sms") as mock_sms,
        patch("app.services.ai_service.interpret", return_value=ai_resp),
    ):
        resp = _post(client, "blah blah blah")

    assert resp.status_code == 200
    sent_text = mock_sms.call_args[0][0]
    assert "0800" in sent_text  # handoff message includes phone number


def test_one_unclear_turn_does_not_escalate(client):
    """A single unclear turn passes the AI reply through normally."""
    conv = _make_conv(state={"misunderstood_count": 0})
    ai_resp = _ai_response(
        intent=Intent.UNKNOWN,
        reply="Could you clarify what service you need?",
    )
    with (
        _inject_db(conv),
        patch("app.services.africastalking.send_sms") as mock_sms,
        patch("app.services.ai_service.interpret", return_value=ai_resp),
    ):
        resp = _post(client, "hmm")

    assert resp.status_code == 200
    sent_text = mock_sms.call_args[0][0]
    assert "0800" not in sent_text          # no handoff yet
    assert "clarify" in sent_text.lower()   # AI reply passed through
    assert conv.state.get("misunderstood_count") == 1


def test_successful_booking_resets_misunderstood_count(client):
    """A clear SHOW_SLOTS response resets the misunderstood counter."""
    conv = _make_conv(state={"misunderstood_count": 2})
    ai_resp = _ai_response(
        intent=Intent.BOOK,
        service_type="consultation",
        suggested_action=SuggestedAction.SHOW_SLOTS,
    )
    with (
        _inject_db(conv),
        patch("app.services.africastalking.send_sms"),
        patch("app.services.ai_service.interpret", return_value=ai_resp),
        patch("app.services.ussd_booking.next_slot_label",
              return_value="Mon 14 Jul, 09:00 AM WAT"),
    ):
        resp = _post(client, "I need to book a consultation")

    assert resp.status_code == 200
    assert conv.state.get("misunderstood_count", 0) == 0


# ── AT send failure is non-fatal ──────────────────────────────────────────────

def test_sms_send_failure_does_not_crash_endpoint(client):
    """An AT SMS send failure must be logged but must not surface as an HTTP error."""
    conv = _make_conv()
    ai_resp = _ai_response(reply="Hello! How can I help you today?")
    with (
        _inject_db(conv),
        patch("app.services.africastalking.send_sms",
              side_effect=Exception("AT timeout")),
        patch("app.services.ai_service.interpret", return_value=ai_resp),
    ):
        resp = _post(client, "hi")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ── Pidgin / Yoruba end-to-end ────────────────────────────────────────────────

def test_pidgin_help_skips_ai(client):
    conv = _make_conv(language="pidgin")
    with (
        _inject_db(conv),
        patch("app.services.africastalking.send_sms") as mock_sms,
        patch("app.services.ai_service.interpret") as mock_ai,
    ):
        resp = _post(client, "help")

    assert resp.status_code == 200
    mock_ai.assert_not_called()
    assert "0800" in mock_sms.call_args[0][0]


def test_yoruba_reset_skips_ai(client):
    conv = _make_conv(language="yo")
    with (
        _inject_db(conv),
        patch("app.services.africastalking.send_sms") as mock_sms,
        patch("app.services.ai_service.interpret") as mock_ai,
    ):
        resp = _post(client, "bẹrẹ")

    assert resp.status_code == 200
    mock_ai.assert_not_called()


def test_yoruba_handoff_includes_phone(client):
    conv = _make_conv(language="yo", state={"misunderstood_count": 2})
    ai_resp = _ai_response(
        intent=Intent.UNKNOWN,
        language=Language.YO,
        reply="Báwo ni mo ṣe lè ràn ọ́ lọ́wọ́?",
    )
    with (
        _inject_db(conv),
        patch("app.services.africastalking.send_sms") as mock_sms,
        patch("app.services.ai_service.interpret", return_value=ai_resp),
    ):
        resp = _post(client, "huh")

    assert resp.status_code == 200
    sent_text = mock_sms.call_args[0][0]
    assert "0800" in sent_text


# ── Confirm booking via AI ────────────────────────────────────────────────────

def test_ai_confirm_booking_with_existing_service_key(client):
    """AI returns CONFIRM_BOOKING and we already have a service_key in state."""
    conv = _make_conv(
        state={"stage": "slot_offered", "service_key": "1",
               "slot_label": "Mon 14 Jul, 09:00 AM WAT"},
    )
    ai_resp = _ai_response(
        intent=Intent.BOOK,
        suggested_action=SuggestedAction.CONFIRM_BOOKING,
        reply="Great, confirming now!",
    )
    with (
        _inject_db(conv),
        patch("app.services.africastalking.send_sms") as mock_sms,
        patch("app.services.ai_service.interpret", return_value=ai_resp),
        patch("app.services.sms_booking.confirm_from_sms",
              return_value="Booking confirmed! Check SMS."),
    ):
        resp = _post(client, "yes please go ahead")

    assert resp.status_code == 200
    sent_text = mock_sms.call_args[0][0]
    assert "Booking confirmed" in sent_text
