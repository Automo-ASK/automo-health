import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.service import Service as ServiceModel

router = APIRouter(prefix="/services", tags=["services"])


class ServiceRead(BaseModel):
    id: uuid.UUID
    type: str  # "consultation" | "lab_test" | "virtual"
    name: str
    fee: int  # price_amount in kobo
    currency: str
    duration_minutes: int


def _infer_type(name: str) -> str:
    lower = name.lower()
    if any(w in lower for w in ("lab", "test", "blood", "sample")):
        return "lab_test"
    if any(w in lower for w in ("virtual", "online", "tele", "video")):
        return "virtual"
    return "consultation"


@router.get("", response_model=list[ServiceRead], summary="List bookable services")
def list_services(db: Session = Depends(get_db)) -> list[ServiceRead]:
    services = db.execute(
        select(ServiceModel).where(ServiceModel.is_active.is_(True))
    ).scalars().all()
    return [
        ServiceRead(
            id=s.id,
            type=_infer_type(s.name),
            name=s.name,
            fee=s.price_amount,
            currency=s.currency,
            duration_minutes=s.duration_minutes,
        )
        for s in services
    ]
