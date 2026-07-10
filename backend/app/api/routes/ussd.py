"""Africa's Talking USSD webhook.

Africa's Talking POSTs to this endpoint on every keypress in the USSD session.
The response must be plain text starting with ``CON `` (continue) or ``END ``
(terminate the session).

Webhook URL to register in the AT dashboard:
  POST /api/v1/channels/ussd
"""

from fastapi import APIRouter, Form
from fastapi.responses import PlainTextResponse

from app.services import ussd_session

router = APIRouter(prefix="/channels", tags=["channels"])


@router.post(
    "/ussd",
    response_class=PlainTextResponse,
    summary="Africa's Talking USSD webhook",
    include_in_schema=True,
)
def ussd_webhook(
    sessionId: str = Form(...),
    serviceCode: str = Form(...),
    phoneNumber: str = Form(...),
    text: str = Form(default=""),
) -> str:
    """Handle an inbound USSD request from Africa's Talking.

    Africa's Talking sends form-encoded data (not JSON), so we use ``Form``
    parameters.  The ``text`` field accumulates all user inputs joined by ``*``
    (e.g. ``"1*2*3"``), giving us the full session state on every call without
    needing an external store.
    """
    return ussd_session.handle(
        session_id=sessionId,
        phone=phoneNumber,
        text=text,
    )
