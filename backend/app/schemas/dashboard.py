"""Schemas for the staff dashboards (doctor / lab / cashier).

Field names and value vocabulary match ``docs/contracts/booking-api.md`` and the
frontend's ``api.ts`` exactly, so the screens consume the real backend unchanged.
"""

import uuid

from pydantic import BaseModel


class QueueItem(BaseModel):
    id: str
    position: int
    is_next: bool
    patient_name: str
    patient_phone: str | None = None
    type: str
    channel: str
    service_name: str
    slot_time: str
    status: str
    home_reading: str | None = None
    test_details: str | None = None
    collection_date: str | None = None


class DayRow(BaseModel):
    id: str
    patient_name: str
    service_name: str
    slot_time: str
    type: str
    channel: str
    status: str
    consultation_fee: int
    paid: bool


class PaymentRow(BaseModel):
    payment_id: str
    appointment_id: str | None = None
    patient_name: str
    service_name: str
    method: str
    amount: int
    consultation_fee: int
    platform_fee: int
    paid_at: str | None = None
    channel: str


class CloseVisitRequest(BaseModel):
    state: str = "done"  # done | follow_up | admitted
    collection_date: str | None = None


class DashboardFollowUpRequest(BaseModel):
    """Doctor follow-up from the board. The frontend sends ``slot_id``; older
    callers may send ``new_slot_id``. ``service_id`` accepts a slug or UUID."""

    slot_id: uuid.UUID | None = None
    new_slot_id: uuid.UUID | None = None
    service_id: str | None = None


class EmergencyRead(BaseModel):
    id: str
    patient_name: str
    patient_phone: str | None = None
    category: str
    description: str
    status: str
    created_at: str


class EmergencyCreate(BaseModel):
    patient_id: uuid.UUID
    category: str
    description: str


class MakeRoomRequest(BaseModel):
    provider_id: str


class BumpedTo(BaseModel):
    patient_name: str
    new_time: str


class MakeRoomResult(BaseModel):
    bumped_to: BumpedTo | None = None
