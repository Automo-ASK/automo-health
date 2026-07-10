import uuid
from datetime import datetime

from app.models.enums import AppointmentStatus
from app.schemas.common import ORMModel


class AppointmentRead(ORMModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    patient_id: uuid.UUID
    provider_id: uuid.UUID
    slot_id: uuid.UUID
    scheduled_start: datetime
    scheduled_end: datetime
    status: AppointmentStatus
    created_at: datetime
