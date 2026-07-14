"""SMS booking helpers for the Day 4 conversational flow.

Provides:
- Multilingual slot offer / decline / re-ask message builders
- Affirmation detector (fast keyword check, no AI call needed)
- confirm_from_sms() — thin wrapper around ussd_booking.confirm() that strips
  the "END " prefix (USSD needs it; SMS does not)

The affirmation detector intentionally covers common misspellings and
Pidgin/Yoruba affirmatives so the patient doesn't need perfect spelling.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services import ussd_booking

# Maps AI-extracted service_type strings → USSD service key
_TYPE_TO_KEY: dict[str, str] = {
    "consultation": "1",
    "lab_test": "2",
    "virtual": "3",
}

_SERVICE_DISPLAY: dict[str, dict[str, str]] = {
    "en": {
        "consultation": "General Consultation",
        "lab_test": "Lab Test",
        "virtual": "Virtual Consultation",
    },
    "pidgin": {
        "consultation": "General Check-Up",
        "lab_test": "Lab Test",
        "virtual": "Virtual Check-Up",
    },
    "yo": {
        "consultation": "Ayẹwo Gbogbogbo",
        "lab_test": "Idanwò Yàrá",
        "virtual": "Ayẹwo Fóònu",
    },
}

_SLOT_OFFER: dict[str, str] = {
    "en": (
        "Great! The next available {service} slot is:\n"
        "{slot}\n\n"
        "Reply YES to confirm or NO to cancel."
    ),
    "pidgin": (
        "Sharp! Next {service} slot na:\n"
        "{slot}\n\n"
        "Reply YES to confirm or NO to cancel."
    ),
    "yo": (
        "Dára! Àkókò {service} tí ó wà báyìí ni:\n"
        "{slot}\n\n"
        "Fèsì YES láti jẹrisi, tàbí NO láti fagilé."
    ),
}

_DECLINE: dict[str, str] = {
    "en": "No problem! Let me know if you'd like to book something else or need help with anything.",
    "pidgin": "No wahala! Tell me if you wan book another thing or need anything.",
    "yo": "Kò burú! Jẹ́ kí n mọ bí o bá fẹ́ ṣe adehun iṣẹ́ mìíràn.",
}

_REASK: dict[str, str] = {
    "en": (
        "Sorry, I didn't catch that. The slot is:\n"
        "{slot}\n\n"
        "Please reply YES to confirm or NO to cancel."
    ),
    "pidgin": (
        "E no clear. The slot na:\n"
        "{slot}\n\n"
        "Reply YES to confirm or NO to cancel."
    ),
    "yo": (
        "Pẹ̀lẹ́, mi ò gbọ́. Àkókò náà ni:\n"
        "{slot}\n\n"
        "Jọwọ fèsì YES tàbí NO."
    ),
}

# Keyword sets for affirmation / negation detection.
# Intentionally broad — covers abbreviations, Pidgin, common Yoruba.
_YES_WORDS = frozenset({
    "yes", "yeah", "yep", "yh", "y",
    "ok", "okay", "k", "sure", "confirm",
    "go", "proceed", "book", "fine", "alright", "aight",
    # pidgin
    "oya", "abeg",
    # yoruba
    "bẹẹni", "bẹeni",
})

_NO_WORDS = frozenset({
    "no", "nope", "nah", "na", "n",
    "cancel", "stop", "later",
    "nevermind", "never", "mind",
    "dont", "don't",
    # pidgin
    "nor",
    # yoruba
    "rara",
})


def service_type_to_key(service_type: str) -> str:
    """Map an AI-extracted service_type string to the USSD service key (1/2/3)."""
    return _TYPE_TO_KEY.get(service_type.lower().strip(), "1")


def _service_display_name(service_type: str, lang: str) -> str:
    names = _SERVICE_DISPLAY.get(lang, _SERVICE_DISPLAY["en"])
    return names.get(service_type.lower().strip(), service_type.replace("_", " ").title())


def build_slot_offer(service_type: str, slot_label: str, lang: str) -> str:
    """Build the message shown when offering a specific slot for confirmation."""
    tmpl = _SLOT_OFFER.get(lang, _SLOT_OFFER["en"])
    return tmpl.format(service=_service_display_name(service_type, lang), slot=slot_label)


def build_reask(slot_label: str, lang: str) -> str:
    """Build the re-prompt when a patient's response to a slot offer was unclear."""
    tmpl = _REASK.get(lang, _REASK["en"])
    return tmpl.format(slot=slot_label)


def decline_reply(lang: str) -> str:
    return _DECLINE.get(lang, _DECLINE["en"])


def is_affirmative(text: str) -> bool | None:
    """Classify a short patient reply as affirmative (True), negative (False), or unclear (None).

    Checks single-character replies and emoji before the word-set scan so
    patients can reply with just "y" or "✅".
    """
    stripped = text.strip().lower()

    if stripped in {"y", "1", "✓", "✅"}:
        return True
    if stripped in {"n", "0", "x", "❌"}:
        return False

    words = frozenset(stripped.split())
    if words & _YES_WORDS:
        return True
    if words & _NO_WORDS:
        return False
    return None


def confirm_from_sms(db: Session, *, phone: str, service_key: str, lang: str) -> str:
    """Create booking, send payment SMS, and return an SMS-ready confirmation.

    Delegates to ussd_booking.confirm() which handles slot locking, patient
    creation, Booking + Payment row creation, and payment SMS dispatch.
    Strips the "END " prefix that USSD responses require but SMS does not.
    """
    result = ussd_booking.confirm(db, phone=phone, service_key=service_key, lang=lang)
    return result.removeprefix("END ")
