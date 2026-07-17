import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.enums import EmergencyStatus
from app.schemas.dashboard import (
    EmergencyCreate,
    EmergencyRead,
    MakeRoomRequest,
    MakeRoomResult,
)
from app.services import emergencies as emergencies_service
from app.services.exceptions import ConflictError, NotFoundError

router = APIRouter(prefix="/emergencies", tags=["emergencies"])


@router.get("", response_model=list[EmergencyRead], summary="List emergency alerts")
def list_emergencies(
    status: EmergencyStatus | None = None, db: Session = Depends(get_db)
) -> list[EmergencyRead]:
    return [EmergencyRead(**e) for e in emergencies_service.list_emergencies(db, status=status)]


@router.post(
    "", response_model=EmergencyRead, status_code=status.HTTP_201_CREATED, summary="Raise an emergency alert"
)
def create_emergency(payload: EmergencyCreate, db: Session = Depends(get_db)) -> EmergencyRead:
    try:
        return EmergencyRead(
            **emergencies_service.create_emergency(
                db,
                patient_id=payload.patient_id,
                category=payload.category,
                description=payload.description,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{emergency_id}/ack", response_model=EmergencyRead, summary="Acknowledge an emergency")
def acknowledge(emergency_id: uuid.UUID, db: Session = Depends(get_db)) -> EmergencyRead:
    try:
        return EmergencyRead(**emergencies_service.acknowledge(db, emergency_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post(
    "/{emergency_id}/make-room",
    response_model=MakeRoomResult,
    summary="Seat the emergency patient now (shift the scheduled patient)",
)
def make_room(
    emergency_id: uuid.UUID, payload: MakeRoomRequest, db: Session = Depends(get_db)
) -> MakeRoomResult:
    try:
        result = emergencies_service.make_room(db, emergency_id, provider_ref=payload.provider_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return MakeRoomResult(bumped_to=result.get("bumped_to"))
