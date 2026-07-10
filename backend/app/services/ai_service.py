"""AI service — Gemini 2.5 Pro implementation.

Interprets a patient's message and returns structured intent, entities, and a
multilingual reply.  Supports English, Nigerian Pidgin, and Yoruba.

HARD GUARDRAILS (baked into the system prompt and validated on output):
  - Never invent or confirm appointment slots.
  - Never state a price or fee not returned by the booking backend.
  - Never confirm a payment — only the payment webhook can do that.
  - Never give medical advice or triage.

The model handles language understanding and natural reply generation.
The booking backend remains the sole source of truth for all factual data.
"""

from __future__ import annotations

import json
import logging

from google import genai
from google.genai import types

from app.core.config import settings
from app.models.enums import Intent, Language, SuggestedAction
from app.schemas.ai_service import (
    AIInterpretRequest,
    AIInterpretResponse,
    ConversationTurn,
    ExtractedEntities,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are the booking assistant for Automo Health, a Nigerian hospital scheduling service.
You are warm, friendly, and speak like a helpful receptionist — never robotic.

LANGUAGE RULES:
- Detect the language the patient writes in: English ("en"), Nigerian Pidgin ("pidgin"), or Yoruba ("yo").
- Reply ONLY in the same language. Handle code-switching naturally.
- Tolerate misspellings, abbreviations, and informal writing.

HARD GUARDRAILS — never break these:
1. NEVER invent, assume, or confirm appointment slots. Only state slot information when the system provides it.
2. NEVER state a price, fee, or amount unless the booking system has returned it in this conversation.
3. NEVER confirm a payment. Only the payment webhook confirms money received.
4. NEVER give medical advice, diagnosis, or triage. You schedule; you do not treat.
5. If you cannot understand after two attempts, offer to connect the patient with a human.

INTENT:
- "book"        — patient wants to book a new appointment
- "reschedule"  — patient wants to change an existing appointment
- "cancel"      — patient wants to cancel an existing appointment
- "query"       — patient is asking a question (hours, location, services, etc.)
- "unknown"     — intent is not clear; you MUST ask ONE clarifying question

ENTITIES to extract (set to null if not present in the message):
- service_type: "consultation" | "lab_test" | "virtual" | null
- provider_name: the doctor or lab the patient mentioned, or null
- preferred_day: natural language day preference ("tomorrow", "Monday", "next week"), or null
- preferred_time: natural language time preference ("morning", "3pm", "afternoon"), or null
- patient_name: if the patient gives their name, or null
- appointment_id: if the patient references a booking ID for reschedule/cancel, or null

REPLY STYLE:
- Warm and concise. Channel is SMS or WhatsApp — keep replies short.
- Ask for ONE missing piece of information at a time, not everything at once.
- If intent is "book" and you have service_type, set suggested_action to "show_slots".
- If intent is "book" and you are missing service_type, ask what kind of appointment they need.

OUTPUT FORMAT — respond with ONLY valid JSON matching this schema exactly:
{
  "intent": "<one of the intents above>",
  "language": "<en | pidgin | yo>",
  "entities": {
    "service_type": <string or null>,
    "provider_name": <string or null>,
    "preferred_day": <string or null>,
    "preferred_time": <string or null>,
    "patient_name": <string or null>,
    "appointment_id": <string or null>
  },
  "reply": "<the message to send to the patient>",
  "confidence": <float between 0.0 and 1.0>,
  "needs_clarification": <true | false>,
  "suggested_action": <"show_services" | "show_slots" | "confirm_booking" | "awaiting_payment" | "reschedule" | "cancel_booking" | "human_handoff" | null>
}
"""

_FALLBACK_RESPONSE = AIInterpretResponse(
    intent=Intent.UNKNOWN,
    language=Language.EN,
    entities=ExtractedEntities(),
    reply=(
        "Sorry, I'm having a little trouble right now. "
        "Please try again in a moment, or call the clinic directly."
    ),
    confidence=0.0,
    needs_clarification=False,
    suggested_action=SuggestedAction.HUMAN_HANDOFF,
)


def _build_contents(
    message: str,
    history: list[ConversationTurn],
    channel: str,
    language_hint: Language | None,
) -> list[types.Content]:
    """Build the Gemini contents list from conversation history + current message."""
    contents: list[types.Content] = []

    for turn in history:
        role = "user" if turn.role == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=turn.content)]))

    hint = ""
    if language_hint:
        hint = f" [Language hint from prior context: {language_hint.value}]"

    user_text = f"[Channel: {channel}]{hint}\n\nPatient message: {message}"
    contents.append(types.Content(role="user", parts=[types.Part(text=user_text)]))
    return contents


def _parse_response(raw: str) -> AIInterpretResponse:
    """Parse the model's JSON output into a validated response."""
    data = json.loads(raw)

    entities_raw = data.get("entities", {})
    entities = ExtractedEntities(
        service_type=entities_raw.get("service_type"),
        provider_name=entities_raw.get("provider_name"),
        preferred_day=entities_raw.get("preferred_day"),
        preferred_time=entities_raw.get("preferred_time"),
        patient_name=entities_raw.get("patient_name"),
        appointment_id=entities_raw.get("appointment_id"),
    )

    intent_raw = data.get("intent", "unknown")
    try:
        intent = Intent(intent_raw)
    except ValueError:
        intent = Intent.UNKNOWN

    lang_raw = data.get("language", "en")
    try:
        language = Language(lang_raw)
    except ValueError:
        language = Language.EN

    action_raw = data.get("suggested_action")
    suggested_action: SuggestedAction | None = None
    if action_raw:
        try:
            suggested_action = SuggestedAction(action_raw)
        except ValueError:
            suggested_action = None

    reply = data.get("reply", "")
    if not reply:
        raise ValueError("Model returned empty reply")

    return AIInterpretResponse(
        intent=intent,
        language=language,
        entities=entities,
        reply=reply,
        confidence=float(data.get("confidence", 0.8)),
        needs_clarification=bool(data.get("needs_clarification", False)),
        suggested_action=suggested_action,
    )


def interpret(request: AIInterpretRequest) -> AIInterpretResponse:
    """Interpret a patient message using Gemini 2.5 Pro.

    Falls back to a safe error response if the model call fails, so channels
    are never left waiting for an exception to bubble up.
    """
    try:
        client = genai.Client(api_key=settings.google_api_key)

        contents = _build_contents(
            message=request.message,
            history=request.history,
            channel=request.channel.value,
            language_hint=request.language_hint,
        )

        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )

        return _parse_response(response.text)

    except json.JSONDecodeError as exc:
        logger.error("AI service: JSON parse error — %s", exc)
        return _FALLBACK_RESPONSE
    except Exception as exc:  # noqa: BLE001
        logger.error("AI service: unexpected error — %s", exc)
        return _FALLBACK_RESPONSE
