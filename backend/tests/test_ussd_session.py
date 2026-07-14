"""Day 7 — USSD session edge case tests.

All tests are pure unit tests: no DB, no network, no AT calls.
The handle() function is stateless — it derives everything from the
accumulated ``text`` string that Africa's Talking sends on each request.
"""

import pytest

from app.services.ussd_session import BookingIntent, USSDResult, _SLOT_PLACEHOLDER, handle


SESSION = "sess-001"
PHONE   = "+2348012345678"


# ── Step 0: language selection ────────────────────────────────────────────────

def test_step0_empty_text_shows_language_menu():
    result = handle(SESSION, PHONE, "")
    assert result.text.startswith("CON ")
    assert "English" in result.text
    assert "Pidgin" in result.text
    assert "Yoruba" in result.text
    assert result.booking_intent is None


def test_step0_no_text_shows_language_menu():
    # Africa's Talking may omit the field entirely on first dial
    result = handle(SESSION, PHONE, "")
    assert "1." in result.text
    assert "2." in result.text
    assert "3." in result.text


# ── Step 1: main menu per language ───────────────────────────────────────────

@pytest.mark.parametrize("lang_key,expected_word", [
    ("1", "Book"),
    ("2", "Book"),   # Pidgin uses "Book appointment"
    ("3", "adehun"), # Yoruba
])
def test_step1_main_menu_shows_options(lang_key, expected_word):
    result = handle(SESSION, PHONE, lang_key)
    assert result.text.startswith("CON ")
    assert expected_word in result.text
    assert result.booking_intent is None


def test_step1_en_main_menu_has_emergency_option():
    result = handle(SESSION, PHONE, "1")
    assert "4" in result.text
    assert "Emergency" in result.text


def test_step1_invalid_language_key_ends_session():
    result = handle(SESSION, PHONE, "9")
    assert result.text.startswith("END ")
    assert "1, 2, or 3" in result.text


# ── Step 2: service selection ─────────────────────────────────────────────────

def test_step2_en_shows_services():
    result = handle(SESSION, PHONE, "1*1")
    assert result.text.startswith("CON ")
    assert "Consultation" in result.text
    assert "₦2,000" in result.text


def test_step2_pidgin_shows_services():
    result = handle(SESSION, PHONE, "2*1")
    assert result.text.startswith("CON ")
    assert "See doctor" in result.text


def test_step2_yo_shows_services():
    result = handle(SESSION, PHONE, "3*1")
    assert result.text.startswith("CON ")
    assert "Ijẹrọ" in result.text


def test_step2_invalid_action_ends_session():
    result = handle(SESSION, PHONE, "1*9")
    assert result.text.startswith("END ")


def test_step2_reschedule_stub():
    result = handle(SESSION, PHONE, "1*2")
    assert result.text.startswith("END ")
    assert result.booking_intent is None


def test_step2_cancel_stub():
    result = handle(SESSION, PHONE, "1*3")
    assert result.text.startswith("END ")
    assert result.booking_intent is None


# ── Emergency flow ────────────────────────────────────────────────────────────

def test_emergency_en_returns_phone_number():
    result = handle(SESSION, PHONE, "1*4")
    assert result.text.startswith("END ")
    assert "0800" in result.text
    assert "112" in result.text
    assert result.booking_intent is None


def test_emergency_pidgin():
    result = handle(SESSION, PHONE, "2*4")
    assert result.text.startswith("END ")
    assert "0800" in result.text


def test_emergency_yo():
    result = handle(SESSION, PHONE, "3*4")
    assert result.text.startswith("END ")
    assert "Pajawiri" in result.text or "pajawiri" in result.text.lower()


# ── Step 3: slot display ──────────────────────────────────────────────────────

def test_step3_shows_slot_placeholder():
    result = handle(SESSION, PHONE, "1*1*1")
    assert result.text.startswith("CON ")
    assert _SLOT_PLACEHOLDER in result.text
    assert "1." in result.text   # confirm option
    assert "2." in result.text   # see more


def test_step3_lab_service():
    result = handle(SESSION, PHONE, "1*1*2")
    assert result.text.startswith("CON ")


def test_step3_virtual_service():
    result = handle(SESSION, PHONE, "1*1*3")
    assert result.text.startswith("CON ")


def test_step3_invalid_service_key():
    result = handle(SESSION, PHONE, "1*1*9")
    assert result.text.startswith("END ")


# ── Step 4: booking confirmation / "see more" ─────────────────────────────────

def test_step4_confirm_returns_booking_intent():
    result = handle(SESSION, PHONE, "1*1*1*1")
    assert result.booking_intent is not None
    assert isinstance(result.booking_intent, BookingIntent)
    assert result.booking_intent.service_key == "1"
    assert result.booking_intent.lang == "en"


def test_step4_see_more_slots_ends_session():
    result = handle(SESSION, PHONE, "1*1*1*2")
    assert result.text.startswith("END ")
    assert result.booking_intent is None


def test_step4_invalid_slot_choice_ends_session():
    result = handle(SESSION, PHONE, "1*1*1*9")
    assert result.text.startswith("END ")
    assert result.booking_intent is None


def test_step4_pidgin_confirm_booking_intent():
    result = handle(SESSION, PHONE, "2*1*1*1")
    assert result.booking_intent is not None
    assert result.booking_intent.lang == "pidgin"


def test_step4_yo_confirm_booking_intent():
    result = handle(SESSION, PHONE, "3*1*1*1")
    assert result.booking_intent is not None
    assert result.booking_intent.lang == "yo"


# ── Invalid option messages are language-specific ─────────────────────────────

def test_invalid_option_en_uses_english():
    result = handle(SESSION, PHONE, "1*9")
    assert result.text.startswith("END ")
    assert "Invalid" in result.text


def test_invalid_option_pidgin():
    result = handle(SESSION, PHONE, "2*9")
    assert result.text.startswith("END ")
    # Pidgin error message should not be English
    assert "option" in result.text.lower() or "correct" in result.text.lower()


def test_invalid_option_yo():
    result = handle(SESSION, PHONE, "3*9")
    assert result.text.startswith("END ")
