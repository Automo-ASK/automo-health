"""Africa's Talking inbound SMS webhook — Day 4: conversational booking flow.

Conversation state machine (persisted in Conversation.state JSONB):

  stage: "greeting" | "awaiting_service" | "slot_offered" | "booked"
  service_key: "1" | "2" | "3"        — set when service is identified
  service_type: str                    — AI-extracted type, for display
  slot_label: str                      — formatted WAT time last shown

Turn logic per inbound SMS:
  1. If stage == "slot_offered":
       YES → book immediately (no AI call), stage → "booked"
       NO  → reset state to greeting, send decline message
       ?   → fall through to AI (step 2), then re-ask if still unclear
  2. AI interprets every turn that didn't resolve in step 1.
       suggested_action == "show_slots" + service_type  → fetch real slot, send offer
       suggested_action == "confirm_booking" + service_key in state → book
       otherwise → pass AI reply through, track partial booking state
  3. Persist history + state, send reply via AT SMS.

Africa's Talking expects HTTP 200; we always return it.
Webhook URL: POST /api/v1/channels/sms/inbound
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.conversation import Conversation
from app.models.enums import ChannelType, Intent, Language, SuggestedAction
from app.schemas.ai_service import AIInterpretRequest, ConversationTurn
from app.services import africastalking as at
from app.services import ai_service, sms_booking, ussd_booking

logger = logging.getLogger(__name__)

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


def _persist_and_send(
    *,
    conv: Conversation,
    db: Session,
    phone: str,
    user_text: str,
    reply: str,
    history: list[ConversationTurn],
    state: dict,
    lang: str,
) -> None:
    history.append(ConversationTurn(role="user", content=user_text))
    history.append(ConversationTurn(role="assistant", content=reply))
    conv.history = [t.model_dump() for t in history[-settings.ai_max_history_turns:]]
    conv.state = state
    conv.language = lang
    conv.last_message_at = datetime.now(timezone.utc)
    conv.last_reply = reply
    db.commit()

    try:
        at.send_sms(reply, [phone])
    except Exception as exc:
        logger.error("SMS send failed for %s: %s", phone, exc)


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
    """Receive an inbound SMS, run the booking state machine, and reply."""
    conv = _get_or_create_conversation(db, from_)
    history: list[ConversationTurn] = [
        ConversationTurn(**t) for t in (conv.history or [])
    ]
    state: dict = dict(conv.state or {})
    stage: str = state.get("stage", "greeting")
    lang: str = conv.language or "en"
    reply: str | None = None

    # ── 1. Fast path: patient responded to a slot offer ───────────────────────
    if stage == "slot_offered":
        affirmative = sms_booking.is_affirmative(text)
        if affirmative is True:
            reply = sms_booking.confirm_from_sms(
                db, phone=from_, service_key=state["service_key"], lang=lang
            )
            state = {"stage": "booked"}
        elif affirmative is False:
            reply = sms_booking.decline_reply(lang)
            state = {"stage": "greeting"}
        # else: unclear → fall through to AI, then re-ask below

    # ── 2. AI interpretation ──────────────────────────────────────────────────
    if reply is None:
        try:
            lang_hint = Language(lang)
        except ValueError:
            lang_hint = None

        ai_result = ai_service.interpret(
            AIInterpretRequest(
                message=text,
                channel=ChannelType.SMS,
                conversation_id=str(conv.id),
                history=history[-settings.ai_max_history_turns:],
                language_hint=lang_hint,
            )
        )
        lang = ai_result.language.value

        if (
            ai_result.suggested_action == SuggestedAction.SHOW_SLOTS
            and ai_result.entities.service_type
        ):
            # AI has identified the service — inject a real slot time
            service_key = sms_booking.service_type_to_key(ai_result.entities.service_type)
            slot_label = ussd_booking.next_slot_label(db, service_key)
            reply = sms_booking.build_slot_offer(
                ai_result.entities.service_type, slot_label, lang
            )
            state.update(
                stage="slot_offered",
                service_key=service_key,
                service_type=ai_result.entities.service_type,
                slot_label=slot_label,
            )

        elif (
            ai_result.suggested_action == SuggestedAction.CONFIRM_BOOKING
            and state.get("service_key")
        ):
            # AI signals the patient wants to go ahead and we already have the service
            reply = sms_booking.confirm_from_sms(
                db, phone=from_, service_key=state["service_key"], lang=lang
            )
            state["stage"] = "booked"

        elif stage == "slot_offered":
            # Patient's response was unclear even after AI — re-show the slot offer
            reply = sms_booking.build_reask(state.get("slot_label", ""), lang)

        else:
            reply = ai_result.reply
            # Track partial booking state across turns
            if ai_result.intent == Intent.BOOK:
                if ai_result.entities.service_type:
                    state["service_type"] = ai_result.entities.service_type
                    state["service_key"] = sms_booking.service_type_to_key(
                        ai_result.entities.service_type
                    )
                state.setdefault("stage", "awaiting_service")

    _persist_and_send(
        conv=conv,
        db=db,
        phone=from_,
        user_text=text,
        reply=reply,
        history=history,
        state=state,
        lang=lang,
    )
    return {"status": "ok"}
