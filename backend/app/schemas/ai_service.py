"""AI service contract — published on Day 1.

This is the shared spec that WhatsApp (Quadri) and SMS (Adam) both call.
The AI layer handles language + intent + reply; the booking backend is the
single source of truth for slots, fees, and payment confirmation.

Endpoint: POST /api/v1/ai/interpret

HARD GUARDRAILS (enforced in the service implementation):
- Never invent or confirm appointment slots — only the booking API can do that.
- Never state a price or fee — only report what the booking system returns.
- Never confirm a payment — only the payment webhook confirms money received.
- Never give medical advice — schedule only, do not diagnose.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import ChannelType, Intent, Language, SuggestedAction


class ConversationTurn(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str


class AIInterpretRequest(BaseModel):
    """What a channel (WhatsApp, SMS) sends to the AI service."""

    message: str = Field(..., description="Raw inbound message from the patient.")
    channel: ChannelType
    conversation_id: str | None = Field(
        None, description="Existing conversation UUID for context continuation."
    )
    history: list[ConversationTurn] = Field(
        default_factory=list,
        description="Previous turns (most recent last), capped at ~10 turns by the caller.",
    )
    language_hint: Language | None = Field(
        None,
        description="Override from a prior language-detection step (e.g. USSD language choice).",
    )


class ExtractedEntities(BaseModel):
    """Entities the AI extracts from the patient's message.

    All fields are optional — the AI fills in only what the message contains.
    The caller must not assume absent fields are zero/empty; they are unknown.
    """

    service_type: str | None = Field(
        None, description="'consultation' | 'lab_test' | 'virtual'"
    )
    provider_name: str | None = None
    preferred_day: str | None = Field(
        None, description="Natural language, e.g. 'tomorrow', 'Monday', 'next week'."
    )
    preferred_time: str | None = Field(
        None, description="Natural language, e.g. 'morning', '3pm', 'afternoon'."
    )
    patient_name: str | None = None
    appointment_id: str | None = Field(
        None, description="Populated for reschedule / cancel intents when the patient quotes it."
    )
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Any other entities the model extracts that don't fit the above.",
    )


class AIInterpretResponse(BaseModel):
    """What the AI service returns to the calling channel."""

    intent: Intent
    language: Language
    entities: ExtractedEntities
    reply: str = Field(
        ...,
        description=(
            "The message to send back to the patient. "
            "Warm, concise, in the detected language. "
            "Never contains invented slot times, fees, or payment confirmations."
        ),
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    needs_clarification: bool = Field(
        ...,
        description="True when the reply asks the patient for more information before acting.",
    )
    suggested_action: SuggestedAction | None = Field(
        None,
        description="Hint to the channel about what to do next (e.g. call the slots API).",
    )
