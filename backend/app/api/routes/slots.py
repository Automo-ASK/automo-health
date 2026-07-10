import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.slot import (
    SlotCreate,
    SlotGenerateRequest,
    SlotHoldRequest,
    SlotHoldResponse,
    SlotRead,
)
from app.services import slots as slots_service

router = APIRouter(prefix="/slots", tags=["slots"])


@router.get("", response_model=list[SlotRead], summary="List / search availability")
def list_slots(
    provider_id: uuid.UUID | None = None,
    service_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    only_open: bool = True,
    db: Session = Depends(get_db),
) -> list[SlotRead]:
    """Return slots, optionally filtered by provider/service/date and open-only."""
    return slots_service.list_slots(
        db,
        provider_id=provider_id,
        service_id=service_id,
        date_from=date_from,
        date_to=date_to,
        only_open=only_open,
    )


@router.post("", response_model=SlotRead, status_code=status.HTTP_201_CREATED, summary="Create a slot")
def create_slot(payload: SlotCreate, db: Session = Depends(get_db)) -> SlotRead:
    return slots_service.create_slot(
        db,
        provider_id=payload.provider_id,
        service_id=payload.service_id,
        start_time=payload.start_time,
        end_time=payload.end_time,
    )


@router.post("/generate", response_model=list[SlotRead], summary="Generate slots for a window")
def generate_slots(payload: SlotGenerateRequest, db: Session = Depends(get_db)) -> list[SlotRead]:
    """Bulk-create open slots across a time range for a provider."""
    return slots_service.generate_slots(
        db,
        provider_id=payload.provider_id,
        service_id=payload.service_id,
        range_start=payload.range_start,
        range_end=payload.range_end,
        slot_minutes=payload.slot_minutes,
    )


@router.get("/{slot_id}", response_model=SlotRead, summary="Get a slot")
def get_slot(slot_id: uuid.UUID, db: Session = Depends(get_db)) -> SlotRead:
    return slots_service.get_slot(db, slot_id)


@router.post("/{slot_id}/hold", response_model=SlotHoldResponse, summary="Hold a slot")
def hold_slot(
    slot_id: uuid.UUID, payload: SlotHoldRequest, db: Session = Depends(get_db)
) -> SlotHoldResponse:
    """Reserve an OPEN slot with a short-lived hold (Celery-backed expiry)."""
    return slots_service.hold_slot(db, slot_id=slot_id)


@router.post("/{slot_id}/release", response_model=SlotRead, summary="Release a held slot")
def release_slot(slot_id: uuid.UUID, db: Session = Depends(get_db)) -> SlotRead:
    return slots_service.release_slot(db, slot_id=slot_id)
