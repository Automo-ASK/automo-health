"""Schemas for the Africa's Talking USSD webhook."""

from pydantic import BaseModel, Field


class USSDRequest(BaseModel):
    """Payload Africa's Talking POSTs to our USSD webhook on every keypress.

    ``text`` is the full accumulated input, pipe-separated between steps, e.g.
    ``"1*2*3"`` means the user pressed 1 on step 0, 2 on step 1, 3 on step 2.
    Empty string means the first dial.
    """

    sessionId: str = Field(..., alias="sessionId")
    serviceCode: str = Field(..., alias="serviceCode")
    phoneNumber: str = Field(..., alias="phoneNumber")
    text: str = Field(default="")

    model_config = {"populate_by_name": True}
