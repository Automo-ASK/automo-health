"""Africa's Talking inbound SMS webhook.

Africa's Talking POSTs to this endpoint when a patient replies to our
shortcode number.  The handler:
  1. Looks up or creates the patient's Conversation record.
  2. Calls the AI service to interpret the message (stub on Day 1, real on Day 2).
  3. Sends the AI-generated reply back via Africa's Talking SMS.
  4. Persists the updated conversation state.

Webhook URL to register in the AT dashboard:
  POST /api/v1/channels/sms/inbound

Africa's Talking expects an HTTP 200 response; it does not use the body.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.conversation import Conversation
from app.models.enums import ChannelType
from app.schemas.ai_service import AIInterpretRequest, ConversationTurn
from app.services import africastalking as at
from app.services import ai_service

router = APIRouter(prefix="/channels", tags=["channels"])


def _get_or_create_conversation(db: Session, phone: str) -> Conversation:
    conv = db.execute(
        select(Conversation).where(
            Conversation.phone == phone,
            Conversation.channel == ChannelType.SMS,
        )
    ).scalar_one_or_none()
    if conv is None:
        conv = Conversation(phone=phone, channel=ChannelType.SMS)
        db.add(conv)
        db.flush()
    return conv


@router.post(
    "/sms/inbound",
    status_code=200,
    summary="Africa's Talking inbound SMS webhook",
)
def sms_inbound(
    from_: str = Form(..., alias="from"),
    to: str = Form(...),
    text: str = Form(...),
    date: str = Form(...),
    db: Session = Depends(get_db),
) -> dict:
    """Receive an inbound SMS, interpret it with the AI service, and reply.

    Africa's Talking sends form-encoded data (not JSON).
    """
    conv = _get_or_create_conversation(db, from_)

    history: list[ConversationTurn] = [
        ConversationTurn(**turn) for turn in (conv.history or [])
    ]
    trimmed_history = history[-settings.ai_max_history_turns:]

    result = ai_service.interpret(
        AIInterpretRequest(
            message=text,
            channel=ChannelType.SMS,
            conversation_id=str(conv.id),
            history=trimmed_history,
        )
    )

    history.append(ConversationTurn(role="user", content=text))
    history.append(ConversationTurn(role="assistant", content=result.reply))
    conv.history = [t.model_dump() for t in history[-settings.ai_max_history_turns:]]
    conv.language = result.language.value
    conv.last_message_at = datetime.now(timezone.utc)
    conv.last_reply = result.reply

    db.commit()

    at.send_sms(result.reply, [from_])

    return {"status": "ok"}
