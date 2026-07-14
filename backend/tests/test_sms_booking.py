"""Day 7 — SMS booking helper unit tests.

All pure unit tests — no DB, no network, no AT calls.
"""

import pytest

from app.services.sms_booking import (
    build_reask,
    build_slot_offer,
    decline_reply,
    help_reply,
    human_handoff_reply,
    is_affirmative,
    is_help_command,
    is_reset_command,
    reset_reply,
    service_type_to_key,
)


# ── is_affirmative ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "yes", "YES", "Yes", "y", "Y",
    "ok", "okay", "sure", "confirm",
    "oya", "abeg",                   # pidgin
    "bẹẹni",                         # yoruba
    "1", "✅", "✓",
])
def test_is_affirmative_yes(text):
    assert is_affirmative(text) is True


@pytest.mark.parametrize("text", [
    "no", "NO", "nope", "n", "N",
    "cancel", "stop", "later",
    "nor",                           # pidgin
    "rara",                          # yoruba
    "0", "❌", "x",
])
def test_is_affirmative_no(text):
    assert is_affirmative(text) is False


@pytest.mark.parametrize("text", [
    "maybe", "dunno", "what", "huh", "tomorrow", "2pm",
])
def test_is_affirmative_unclear(text):
    assert is_affirmative(text) is None


# ── service_type_to_key ───────────────────────────────────────────────────────

def test_service_type_to_key_consultation():
    assert service_type_to_key("consultation") == "1"


def test_service_type_to_key_lab_test():
    assert service_type_to_key("lab_test") == "2"


def test_service_type_to_key_virtual():
    assert service_type_to_key("virtual") == "3"


def test_service_type_to_key_unknown_defaults_to_consultation():
    assert service_type_to_key("xray") == "1"
    assert service_type_to_key("") == "1"


def test_service_type_to_key_case_insensitive():
    assert service_type_to_key("Consultation") == "1"
    assert service_type_to_key("LAB_TEST") == "2"


# ── build_slot_offer ──────────────────────────────────────────────────────────

def test_build_slot_offer_en_contains_slot_and_service():
    msg = build_slot_offer("consultation", "Mon 14 Jul, 09:00 AM WAT", "en")
    assert "09:00" in msg
    assert "Consultation" in msg
    assert "YES" in msg


def test_build_slot_offer_pidgin():
    msg = build_slot_offer("lab_test", "Tue 15 Jul, 10:00 AM WAT", "pidgin")
    assert "10:00" in msg
    assert "YES" in msg


def test_build_slot_offer_yo():
    msg = build_slot_offer("virtual", "Wed 16 Jul, 02:00 PM WAT", "yo")
    assert "02:00" in msg or "2:00" in msg
    assert "YES" in msg


def test_build_slot_offer_unknown_lang_falls_back_to_en():
    msg = build_slot_offer("consultation", "Mon 14 Jul, 09:00 AM WAT", "fr")
    assert "YES" in msg


# ── build_reask ───────────────────────────────────────────────────────────────

def test_build_reask_en_contains_slot():
    msg = build_reask("Mon 14 Jul, 09:00 AM WAT", "en")
    assert "09:00" in msg
    assert "YES" in msg or "yes" in msg.lower()


def test_build_reask_pidgin():
    msg = build_reask("Tue 15 Jul, 10:00 AM WAT", "pidgin")
    assert "10:00" in msg


def test_build_reask_yo():
    msg = build_reask("Wed 16 Jul, 02:00 PM WAT", "yo")
    assert "02:00" in msg or "2:00" in msg


# ── decline_reply ─────────────────────────────────────────────────────────────

def test_decline_reply_en():
    msg = decline_reply("en")
    assert "No problem" in msg or "no problem" in msg.lower()


def test_decline_reply_pidgin():
    msg = decline_reply("pidgin")
    assert "wahala" in msg


def test_decline_reply_yo():
    msg = decline_reply("yo")
    assert "burú" in msg or "bur" in msg.lower()


# ── is_reset_command ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "reset", "RESET", "Reset",
    "restart", "start over", "startover",
    "begin", "new", "back",
    "start again",
    "bẹrẹ",
])
def test_is_reset_command_true(text):
    assert is_reset_command(text) is True


@pytest.mark.parametrize("text", [
    "yes", "no", "help", "book", "consultation", "hi",
])
def test_is_reset_command_false(text):
    assert is_reset_command(text) is False


# ── is_help_command ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "help", "HELP", "Help",
    "info", "information", "contact",
    "phone", "address", "location", "hours",
    "iranlọwọ",
])
def test_is_help_command_true(text):
    assert is_help_command(text) is True


@pytest.mark.parametrize("text", [
    "yes", "no", "reset", "book", "consultation",
])
def test_is_help_command_false(text):
    assert is_help_command(text) is False


# ── human_handoff_reply ───────────────────────────────────────────────────────

def test_human_handoff_reply_en_contains_phone():
    msg = human_handoff_reply("en")
    assert "0800" in msg
    assert "RESET" in msg


def test_human_handoff_reply_pidgin():
    msg = human_handoff_reply("pidgin")
    assert "0800" in msg


def test_human_handoff_reply_yo():
    msg = human_handoff_reply("yo")
    assert "0800" in msg


def test_human_handoff_reply_unknown_lang_falls_back_to_en():
    msg = human_handoff_reply("fr")
    assert "0800" in msg


# ── reset_reply ───────────────────────────────────────────────────────────────

def test_reset_reply_en():
    msg = reset_reply("en")
    assert "Book" in msg or "1." in msg


def test_reset_reply_pidgin():
    msg = reset_reply("pidgin")
    assert "wahala" in msg or "No" in msg


def test_reset_reply_yo():
    msg = reset_reply("yo")
    assert "Kò burú" in msg or "bẹ̀rẹ̀" in msg


# ── help_reply ────────────────────────────────────────────────────────────────

def test_help_reply_en_contains_clinic_info():
    msg = help_reply("en")
    assert "0800" in msg
    assert "₦" in msg


def test_help_reply_pidgin():
    msg = help_reply("pidgin")
    assert "0800" in msg


def test_help_reply_yo():
    msg = help_reply("yo")
    assert "0800" in msg
