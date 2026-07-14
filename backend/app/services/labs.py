"""Lab orders (Day 6).

Clinician orders a test off an appointment; a lab tech collects the sample and later
enters the result. Statuses: ORDERED -> COLLECTED -> RESULTED (or CANCELLED).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.enums import LabOrderStatus, NotificationEvent
from app.models.lab_order import LabOrder
from app.services import notifications
from app.services.exceptions import ConflictError, NotFoundError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_order(db: Session, order_id: uuid.UUID) -> LabOrder:
    order = db.get(LabOrder, order_id)
    if order is None:
        raise NotFoundError(f"Lab order {order_id} not found")
    return order


def list_orders(
    db: Session,
    *,
    appointment_id: uuid.UUID | None = None,
    patient_id: uuid.UUID | None = None,
    status: LabOrderStatus | None = None,
) -> list[LabOrder]:
    stmt = select(LabOrder)
    if appointment_id is not None:
        stmt = stmt.where(LabOrder.appointment_id == appointment_id)
    if patient_id is not None:
        stmt = stmt.where(LabOrder.patient_id == patient_id)
    if status is not None:
        stmt = stmt.where(LabOrder.status == status)
    stmt = stmt.order_by(LabOrder.created_at)
    return list(db.execute(stmt).scalars().all())


def order_test(
    db: Session,
    *,
    appointment_id: uuid.UUID,
    test_name: str,
    price_amount: int = 0,
    currency: str = "NGN",
) -> LabOrder:
    """Order a lab test against an appointment."""
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise NotFoundError(f"Appointment {appointment_id} not found")

    order = LabOrder(
        appointment_id=appointment.id,
        patient_id=appointment.patient_id,
        test_name=test_name,
        status=LabOrderStatus.ORDERED,
        price_amount=price_amount,
        currency=currency,
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    notifications.dispatch(
        NotificationEvent.LAB_ORDERED,
        {"lab_order_id": str(order.id), "appointment_id": str(appointment.id),
         "test_name": test_name},
    )
    return order


def mark_collected(db: Session, order_id: uuid.UUID) -> LabOrder:
    """Mark the sample as collected (ORDERED -> COLLECTED)."""
    order = get_order(db, order_id)
    if order.status == LabOrderStatus.COLLECTED:
        return order
    if order.status != LabOrderStatus.ORDERED:
        raise ConflictError(f"Cannot collect a {order.status.value} lab order")
    order.status = LabOrderStatus.COLLECTED
    db.commit()
    db.refresh(order)
    return order


def submit_result(db: Session, order_id: uuid.UUID, *, result: str) -> LabOrder:
    """Enter a result and mark the order RESULTED."""
    order = get_order(db, order_id)
    if order.status == LabOrderStatus.CANCELLED:
        raise ConflictError("Cannot result a cancelled lab order")

    order.result = result
    order.status = LabOrderStatus.RESULTED
    order.resulted_at = _utcnow()
    db.commit()
    db.refresh(order)

    notifications.dispatch(
        NotificationEvent.LAB_RESULTED,
        {"lab_order_id": str(order.id), "appointment_id": str(order.appointment_id),
         "test_name": order.test_name},
    )
    return order


def cancel_order(db: Session, order_id: uuid.UUID) -> LabOrder:
    order = get_order(db, order_id)
    if order.status == LabOrderStatus.RESULTED:
        raise ConflictError("Cannot cancel a resulted lab order")
    order.status = LabOrderStatus.CANCELLED
    db.commit()
    db.refresh(order)
    return order
