"""AI service endpoint — the shared contract for WhatsApp and SMS channels.

POST /api/v1/ai/interpret

Interprets a patient's raw message and returns:
  - detected intent (book / reschedule / cancel / query / unknown)
  - detected language (en / pidgin / yo)
  - extracted entities (service type, provider, day/time preference, etc.)
  - a natural-language reply to send back to the patient
  - a suggested_action hint for the calling channel

GUARDRAILS (enforced in the service layer):
  - Never invents slots, fees, or payment confirmations.
  - Falls back to a safe error reply if the model call fails.
"""

from fastapi import APIRouter

from app.schemas.ai_service import AIInterpretRequest, AIInterpretResponse
from app.services import ai_service

router = APIRouter(prefix="/ai", tags=["ai-service"])


@router.post(
    "/interpret",
    response_model=AIInterpretResponse,
    summary="Interpret a patient message (language, intent, entities, reply)",
)
def interpret(payload: AIInterpretRequest) -> AIInterpretResponse:
    """Interpret a patient message using Gemini 2.5 Pro.

    Safe to call from WhatsApp and SMS handlers.  Never raises — returns a
    human_handoff fallback response if the model is unavailable.
    """
    return ai_service.interpret(payload)
