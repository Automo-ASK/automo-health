"""Schemas for Africa's Talking inbound SMS webhook."""

from pydantic import BaseModel, Field


class InboundSMSRequest(BaseModel):
    """Payload Africa's Talking POSTs when an SMS arrives on our shortcode.

    Field names match the AT webhook exactly (camelCase).
    """

    from_: str = Field(..., alias="from")
    to: str
    text: str
    date: str
    id: str | None = None
    linkId: str | None = Field(None, alias="linkId")

    model_config = {"populate_by_name": True}
