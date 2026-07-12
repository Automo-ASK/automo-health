"""USSD session state machine for Africa's Talking.

Africa's Talking accumulates all user inputs into the ``text`` field, joined by
``*``, so the full interaction history is available on every request — no
external state store needed for the menu tree.

``text`` parsing:
  ""        → step 0: language selection
  "1"       → step 1: chose English, show main menu
  "2"       → step 1: chose Pidgin, show main menu
  "3"       → step 1: chose Yoruba, show main menu
  "1*1"     → step 2: en + Book, show service types
  "1*1*1"   → step 3: en + Book + Consultation, show next slot
  "1*1*1*1" → step 4: en + Book + Consultation + Confirm, END + queue SMS

Services and slots are stubbed here for Day 1.  On Day 3, replace the stub
helpers with real calls into the booking service.
"""

from __future__ import annotations

_LANGUAGES: dict[str, str] = {"1": "en", "2": "pidgin", "3": "yo"}

_MAIN_MENU: dict[str, dict[str, str]] = {
    "en": {
        "1": "Book appointment",
        "2": "Reschedule",
        "3": "Cancel",
    },
    "pidgin": {
        "1": "Book appointment",
        "2": "Change appointment",
        "3": "Cancel appointment",
    },
    "yo": {
        "1": "Ṣe adehun",
        "2": "Yi adehun pada",
        "3": "Fagilé adehun",
    },
}

_SERVICES: dict[str, dict[str, dict[str, str]]] = {
    "en": {
        "1": {"name": "Consultation", "fee": "₦2,000"},
        "2": {"name": "Lab test", "fee": "₦1,500"},
        "3": {"name": "Virtual follow-up", "fee": "₦1,000"},
    },
    "pidgin": {
        "1": {"name": "See doctor", "fee": "₦2,000"},
        "2": {"name": "Lab test", "fee": "₦1,500"},
        "3": {"name": "Virtual check-up", "fee": "₦1,000"},
    },
    "yo": {
        "1": {"name": "Ijẹrọ dokita", "fee": "₦2,000"},
        "2": {"name": "Idanwo ile-iwosan", "fee": "₦1,500"},
        "3": {"name": "Abẹwo foju", "fee": "₦1,000"},
    },
}

# TODO Day 3: replace with a real call to slots_service.get_next_open_slot()
_STUB_SLOT = "Mon 14 Jul, 9:00 AM"


def _render_main_menu(lang: str) -> str:
    menu = _MAIN_MENU[lang]
    lines = [f"{k}. {v}" for k, v in menu.items()]
    greetings = {
        "en": "What would you like to do?",
        "pidgin": "Wetin you wan do?",
        "yo": "Kini o fẹ ṣe?",
    }
    return greetings[lang] + "\n" + "\n".join(lines)


def _render_services(lang: str) -> str:
    services = _SERVICES[lang]
    lines = [f"{k}. {v['name']} ({v['fee']})" for k, v in services.items()]
    prompts = {
        "en": "Which service do you need?",
        "pidgin": "Which service you want?",
        "yo": "Iṣẹ wo ni o nilo?",
    }
    return prompts[lang] + "\n" + "\n".join(lines)


def _render_slot_confirmation(lang: str, slot: str, service_name: str) -> str:
    texts = {
        "en": (
            f"Next available slot for {service_name}:\n"
            f"{slot}\n"
            "1. Confirm this slot\n"
            "2. See more slots"
        ),
        "pidgin": (
            f"Next slot for {service_name}:\n"
            f"{slot}\n"
            "1. Confirm am\n"
            "2. Show me more"
        ),
        "yo": (
            f"Akoko ti o wa fun {service_name}:\n"
            f"{slot}\n"
            "1. Jẹrisi akoko yii\n"
            "2. Wo awọn akoko miiran"
        ),
    }
    return texts[lang]


def _render_booking_confirmed(lang: str) -> str:
    texts = {
        "en": (
            "Your slot has been held. "
            "You will receive an SMS shortly with payment details. "
            "Transfer the exact amount to complete your booking."
        ),
        "pidgin": (
            "We don hold your slot. "
            "You go receive SMS with payment details soon. "
            "Send the exact amount to confirm your booking."
        ),
        "yo": (
            "A ti pa akoko rẹ mọ. "
            "Iwọ yoo gba SMS pẹlu alaye isanwo laipẹ. "
            "Fi iye gangan ranṣẹ lati jẹrisi adehun rẹ."
        ),
    }
    return texts[lang]


def handle(session_id: str, phone: str, text: str) -> str:
    """Return the raw USSD response string (prefixed CON or END).

    Args:
        session_id: Africa's Talking session identifier.
        phone: E.164 phone number of the caller.
        text: Accumulated user inputs (``*``-separated).

    Returns:
        A string starting with ``CON `` (continue) or ``END `` (terminate).
    """
    steps = text.split("*") if text else []

    # ── Step 0: language selection ──────────────────────────────────────────
    if not steps or steps == [""]:
        return (
            "CON Welcome to Automo Health\n"
            "Please choose your language:\n"
            "1. English\n"
            "2. Pidgin\n"
            "3. Yoruba"
        )

    lang_key = steps[0]
    lang = _LANGUAGES.get(lang_key)
    if lang is None:
        return "END Invalid option. Please dial again and choose 1, 2, or 3."

    # ── Step 1: main menu ───────────────────────────────────────────────────
    if len(steps) == 1:
        return "CON " + _render_main_menu(lang)

    action_key = steps[1]

    if action_key not in ("1", "2", "3"):
        return "END Invalid option. Please dial again."

    # Reschedule and cancel — stub for Day 3
    if action_key in ("2", "3"):
        stub_msgs = {
            "en": "This feature is coming soon. Please call the clinic to reschedule or cancel.",
            "pidgin": "This feature dey come soon. Call the clinic to change or cancel.",
            "yo": "Ẹya yii n bọ laipẹ. Jọwọ pe ile-iwosan lati yi pada tabi fagilé.",
        }
        return "END " + stub_msgs[lang]

    # ── Step 2: service selection (book flow) ───────────────────────────────
    if len(steps) == 2:
        return "CON " + _render_services(lang)

    service_key = steps[2]
    services = _SERVICES[lang]
    if service_key not in services:
        return "END Invalid option. Please dial again."

    service = services[service_key]

    # ── Step 3: show next available slot ────────────────────────────────────
    if len(steps) == 3:
        return "CON " + _render_slot_confirmation(lang, _STUB_SLOT, service["name"])

    slot_choice = steps[3]

    # "See more slots" — stub
    if slot_choice == "2":
        return "END Sorry, no other slots available right now. Please try again later."

    if slot_choice != "1":
        return "END Invalid option. Please dial again."

    # ── Step 4: booking confirmed — send SMS with payment details ────────────
    # TODO Day 3: create a real booking here, then send payment SMS
    return "END " + _render_booking_confirmed(lang)
