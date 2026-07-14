import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import LabOrderStatus
from app.schemas.common import ORMModel


class LabOrderCreate(BaseModel):
    appointment_id: uuid.UUID
    test_name: str
    price_amount: int = 0
    currency: str = "NGN"


class LabResultSubmit(BaseModel):
    result: str


class LabOrderRead(ORMModel):
    id: uuid.UUID
    appointment_id: uuid.UUID
    patient_id: uuid.UUID
    test_name: str
    status: LabOrderStatus
    price_amount: int
    currency: str
    result: str | None = None
    resulted_at: datetime | None = None
    created_at: datetime
