import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.enums import LabOrderStatus
from app.schemas.lab import LabOrderCreate, LabOrderRead, LabResultSubmit
from app.services import labs as labs_service

router = APIRouter(prefix="/labs", tags=["labs"])


@router.post(
    "/orders",
    response_model=LabOrderRead,
    status_code=status.HTTP_201_CREATED,
    summary="Order a lab test",
)
def order_test(payload: LabOrderCreate, db: Session = Depends(get_db)) -> LabOrderRead:
    return labs_service.order_test(
        db,
        appointment_id=payload.appointment_id,
        test_name=payload.test_name,
        price_amount=payload.price_amount,
        currency=payload.currency,
    )


@router.get("/orders", response_model=list[LabOrderRead], summary="List lab orders")
def list_orders(
    appointment_id: uuid.UUID | None = None,
    patient_id: uuid.UUID | None = None,
    status: LabOrderStatus | None = None,
    db: Session = Depends(get_db),
) -> list[LabOrderRead]:
    return labs_service.list_orders(
        db, appointment_id=appointment_id, patient_id=patient_id, status=status
    )


@router.get("/orders/{order_id}", response_model=LabOrderRead, summary="Get a lab order")
def get_order(order_id: uuid.UUID, db: Session = Depends(get_db)) -> LabOrderRead:
    return labs_service.get_order(db, order_id)


@router.post(
    "/orders/{order_id}/collect",
    response_model=LabOrderRead,
    summary="Mark a sample collected",
)
def collect(order_id: uuid.UUID, db: Session = Depends(get_db)) -> LabOrderRead:
    return labs_service.mark_collected(db, order_id)


@router.post(
    "/orders/{order_id}/result",
    response_model=LabOrderRead,
    summary="Submit a lab result",
)
def submit_result(
    order_id: uuid.UUID, payload: LabResultSubmit, db: Session = Depends(get_db)
) -> LabOrderRead:
    return labs_service.submit_result(db, order_id, result=payload.result)


@router.post(
    "/orders/{order_id}/cancel",
    response_model=LabOrderRead,
    summary="Cancel a lab order",
)
def cancel(order_id: uuid.UUID, db: Session = Depends(get_db)) -> LabOrderRead:
    return labs_service.cancel_order(db, order_id)
