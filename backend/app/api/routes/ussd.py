"""Africa's Talking USSD webhook.

Africa's Talking POSTs to this endpoint on every keypress in the USSD session.
The response must be plain text starting with ``CON `` (continue) or ``END ``
(terminate the session).

Webhook URL to register in the AT dashboard:
  POST /api/v1/channels/ussd
"""

from fastapi import APIRouter, Depends, Form
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services import ussd_booking, ussd_session
from app.services.ussd_session import _SLOT_PLACEHOLDER  # sentinel for slot-lookup step

router = APIRouter(prefix="/channels", tags=["channels"])


@router.post(
    "/ussd",
    response_class=PlainTextResponse,
    summary="Africa's Talking USSD webhook",
)
def ussd_webhook(
    sessionId: str = Form(...),
    serviceCode: str = Form(...),
    phoneNumber: str = Form(...),
    text: str = Form(default=""),
    db: Session = Depends(get_db),
) -> str:
    """Handle an inbound USSD request from Africa's Talking.

    Steps 0–2 are pure menu strings.
    Step 3 shows the next available slot time (DB lookup inlined here).
    Step 4 calls the real booking engine and returns a terminal END message.
    """
    result = ussd_session.handle(sessionId, phoneNumber, text)

    # Step 4 — booking confirmation
    if result.booking_intent is not None:
        intent = result.booking_intent
        return ussd_booking.confirm(
            db,
            phone=phoneNumber,
            service_key=intent.service_key,
            lang=intent.lang,
        )

    # Step 3 — replace the placeholder with the real next-available slot time
    if _SLOT_PLACEHOLDER in result.text:
        steps = text.split("*") if text else []
        service_key = steps[2] if len(steps) >= 3 else "1"
        slot_label = ussd_booking.next_slot_label(db, service_key)
        result.text = result.text.replace(_SLOT_PLACEHOLDER, slot_label)

    return result.text
