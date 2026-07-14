"""USSD session state machine for Africa's Talking.

Africa's Talking accumulates all user inputs into the ``text`` field, joined
by ``*``, so the full session history is available on every request — no
external state store needed for the menu tree itself.

``text`` parsing:
  ""          → step 0: language selection
  "1"         → step 1: en,     show main menu
  "2"         → step 1: pidgin, show main menu
  "3"         → step 1: yo,     show main menu
  "1*1"       → step 2: en + Book, show service types
  "1*1*1"     → step 3: en + Book + Consultation, show next slot label
  "1*1*1*1"   → step 4: en + Book + Consultation + Confirm → BookingIntent
  "1*4"       → emergency info (END, no DB call)

The state machine returns a ``USSDResult``.  When ``booking_intent`` is set
the route must call ``ussd_booking.confirm()`` to execute the real booking and
return the terminal END message.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_LANGUAGES: dict[str, str] = {"1": "en", "2": "pidgin", "3": "yo"}

_MAIN_MENU: dict[str, dict[str, str]] = {
    "en": {
        "1": "Book appointment",
        "2": "Reschedule",
        "3": "Cancel",
        "4": "Emergency contact",
    },
    "pidgin": {
        "1": "Book appointment",
        "2": "Change appointment",
        "3": "Cancel appointment",
        "4": "Emergency",
    },
    "yo": {
        "1": "Ṣe adehun",
        "2": "Yi adehun padà",
        "3": "Fagilé adehun",
        "4": "Pajawiri",
    },
}

# service_key → {name, fee} per language
_SERVICES: dict[str, dict[str, dict[str, str]]] = {
    "en": {
        "1": {"name": "Consultation", "fee": "₦2,000"},
        "2": {"name": "Lab test",     "fee": "₦1,500"},
        "3": {"name": "Virtual",      "fee": "₦1,000"},
    },
    "pidgin": {
        "1": {"name": "See doctor",      "fee": "₦2,000"},
        "2": {"name": "Lab test",        "fee": "₦1,500"},
        "3": {"name": "Virtual check-up","fee": "₦1,000"},
    },
    "yo": {
        "1": {"name": "Ijẹrọ dokita",       "fee": "₦2,000"},
        "2": {"name": "Idanwo ile-iwosan",   "fee": "₦1,500"},
        "3": {"name": "Abẹwo foju",          "fee": "₦1,000"},
    },
}

_NEXT_SLOT_LABEL: dict[str, str] = {
    "en":     "Next available slot",
    "pidgin": "Next slot wey dey",
    "yo":     "Àkókò tó wà",
}

_SLOT_CONFIRM_OPTIONS: dict[str, tuple[str, str]] = {
    "en":     ("1. Confirm this slot", "2. See more slots"),
    "pidgin": ("1. Confirm am",        "2. Show me more"),
    "yo":     ("1. Jẹrisi àkókò yìí", "2. Wo àwọn mìíràn"),
}

_NO_MORE_SLOTS: dict[str, str] = {
    "en":     "No other slots available right now. Please try again later.",
    "pidgin": "No more slots dey now. Try again later.",
    "yo":     "Kò sí àkókò mìíràn báyìí. Jọwọ gbìyànjú lẹhinna.",
}

_STUB_COMING_SOON: dict[str, str] = {
    "en":     "This feature is coming soon. Please call the clinic to reschedule or cancel.",
    "pidgin": "This feature dey come soon. Call clinic to change or cancel.",
    "yo":     "Ẹ̀yà yìí ń bọ̀ laipẹ̀. Jọwọ pe ilé-iwosan láti yí adehun rẹ padà tàbí fagilé.",
}

_EMERGENCY: dict[str, str] = {
    "en": (
        "Automo Health Emergency Line:\n"
        "📞 0800-AUTOMO (0800-288666)\n\n"
        "Address: 12 Health Way, Victoria Island, Lagos.\n\n"
        "For life-threatening emergencies call 112."
    ),
    "pidgin": (
        "Automo Health Emergency:\n"
        "📞 0800-AUTOMO (0800-288666)\n\n"
        "Address: 12 Health Way, VI, Lagos.\n\n"
        "If e dey life-threatening, call 112."
    ),
    "yo": (
        "Nọ́mbà Pajawiri Automo Health:\n"
        "📞 0800-AUTOMO (0800-288666)\n\n"
        "Àdírẹ́sì: 12 Health Way, Victoria Island, Lagos.\n\n"
        "Fún pajawiri tó lewu ẹ̀mí, pe 112."
    ),
}

_INVALID_OPTION: dict[str, str] = {
    "en":     "Invalid option. Please dial again.",
    "pidgin": "Option no correct. Please dial again.",
    "yo":     "Àṣàyàn kò tọ́. Jọwọ tẹ nọ́mbà lẹ́ẹ̀kan sí i.",
}

# Displayed while we fetch the real slot — the real time comes from the DB
_SLOT_PLACEHOLDER = "next available"


@dataclass
class BookingIntent:
    """Signals that the user has confirmed — the route must execute the booking."""
    service_key: str
    service_name: str
    lang: str


@dataclass
class USSDResult:
    """Return value from ``handle()``.

    ``text`` is the raw string to return to Africa's Talking (CON … or END …).
    If ``booking_intent`` is set, the route should call ``ussd_booking.confirm()``
    instead of returning ``text`` directly.
    """
    text: str
    booking_intent: BookingIntent | None = field(default=None)


def handle(_session_id: str, _phone: str, text: str) -> USSDResult:
    """Return a ``USSDResult`` for the current state of the USSD session."""
    steps = text.split("*") if text else []

    # ── Step 0: language selection ───────────────────────────────────────────
    if not steps or steps == [""]:
        return USSDResult(
            "CON Welcome to Automo Health\n"
            "Please choose your language:\n"
            "1. English\n"
            "2. Pidgin\n"
            "3. Yoruba"
        )

    lang_key = steps[0]
    lang = _LANGUAGES.get(lang_key)
    if lang is None:
        return USSDResult("END Invalid option. Please dial again and choose 1, 2, or 3.")

    # ── Step 1: main menu ────────────────────────────────────────────────────
    if len(steps) == 1:
        menu = _MAIN_MENU[lang]
        lines = "\n".join(f"{k}. {v}" for k, v in menu.items())
        greet = {
            "en":     "What would you like to do?",
            "pidgin": "Wetin you wan do?",
            "yo":     "Kíni o fẹ́ ṣe?",
        }
        return USSDResult(f"CON {greet[lang]}\n{lines}")

    action_key = steps[1]
    if action_key not in ("1", "2", "3", "4"):
        return USSDResult("END " + _INVALID_OPTION[lang])

    # Emergency — no DB call, immediate END
    if action_key == "4":
        return USSDResult("END " + _EMERGENCY[lang])

    # Reschedule / cancel — stub (clinic handles offline)
    if action_key in ("2", "3"):
        return USSDResult("END " + _STUB_COMING_SOON[lang])

    # ── Step 2: service selection ────────────────────────────────────────────
    if len(steps) == 2:
        services = _SERVICES[lang]
        lines = "\n".join(f"{k}. {v['name']} ({v['fee']})" for k, v in services.items())
        prompts = {"en": "Which service?", "pidgin": "Which service you want?", "yo": "Iṣẹ wo ni o nilo?"}
        return USSDResult(f"CON {prompts[lang]}\n{lines}")

    service_key = steps[2]
    if service_key not in _SERVICES[lang]:
        return USSDResult("END " + _INVALID_OPTION[lang])

    service = _SERVICES[lang][service_key]

    # ── Step 3: show next available slot ─────────────────────────────────────
    if len(steps) == 3:
        opt1, opt2 = _SLOT_CONFIRM_OPTIONS[lang]
        label = _NEXT_SLOT_LABEL[lang]
        return USSDResult(
            f"CON {label} for {service['name']}:\n"
            f"{_SLOT_PLACEHOLDER}\n"
            f"{opt1}\n"
            f"{opt2}"
        )

    slot_choice = steps[3]

    if slot_choice == "2":
        return USSDResult("END " + _NO_MORE_SLOTS[lang])

    if slot_choice != "1":
        return USSDResult("END " + _INVALID_OPTION[lang])

    # ── Step 4: user confirmed — signal the route to execute real booking ────
    return USSDResult(
        text="",   # filled in by the route after calling ussd_booking.confirm()
        booking_intent=BookingIntent(
            service_key=service_key,
            service_name=service["name"],
            lang=lang,
        ),
    )
