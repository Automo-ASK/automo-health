"""Day 6: cashier cash collection + lab order lifecycle."""

import pytest

from app.models.enums import (
    AppointmentStatus,
    BookingStatus,
    LabOrderStatus,
    PaymentProvider,
    SlotStatus,
)
from app.services import bookings as bookings_service
from app.services import cashier as cashier_service
from app.services import labs as labs_service
from app.services import reconciliation
from app.services.exceptions import ConflictError
from tests.conftest import Scenario


def _book(db, sc: Scenario):
    return bookings_service.create_booking(
        db, patient_id=sc.patient.id, slot_id=sc.slot.id, service_id=sc.service.id
    )


def test_cashier_exact_cash_confirms(db, scenario):
    booking, _ = _book(db, scenario)

    result = cashier_service.collect_cash(db, booking.id, amount=booking.amount)
    assert result.status == "confirmed"
    assert result.appointment is not None
    assert result.appointment.status == AppointmentStatus.SCHEDULED

    db.refresh(booking)
    db.refresh(scenario.slot)
    assert booking.status == BookingStatus.CONFIRMED
    assert scenario.slot.status == SlotStatus.BOOKED
    assert booking.payment.provider == PaymentProvider.CASH


def test_cashier_wrong_amount_rejected(db, scenario):
    booking, _ = _book(db, scenario)
    with pytest.raises(ConflictError):
        cashier_service.collect_cash(db, booking.id, amount=booking.amount - 100)

    db.refresh(booking)
    assert booking.status == BookingStatus.PENDING_PAYMENT


def test_cashier_double_collect_rejected(db, scenario):
    booking, _ = _book(db, scenario)
    cashier_service.collect_cash(db, booking.id, amount=booking.amount)
    with pytest.raises(ConflictError):
        cashier_service.collect_cash(db, booking.id, amount=booking.amount)


def test_outstanding_queue_includes_pending(db, scenario):
    booking, _ = _book(db, scenario)
    outstanding_ids = {b.id for b in cashier_service.list_outstanding(db)}
    assert booking.id in outstanding_ids

    cashier_service.collect_cash(db, booking.id, amount=booking.amount)
    outstanding_ids = {b.id for b in cashier_service.list_outstanding(db)}
    assert booking.id not in outstanding_ids


def test_lab_order_lifecycle(db, scenario):
    booking, payment = _book(db, scenario)
    appt = reconciliation.confirm_payment(
        db, payment_id=payment.id, amount_paid=booking.amount,
        charge_status="success", gateway_response={"amount": booking.amount},
    ).appointment

    order = labs_service.order_test(
        db, appointment_id=appt.id, test_name="Full Blood Count", price_amount=300_000
    )
    assert order.status == LabOrderStatus.ORDERED

    order = labs_service.mark_collected(db, order.id)
    assert order.status == LabOrderStatus.COLLECTED

    order = labs_service.submit_result(db, order.id, result="Normal ranges")
    assert order.status == LabOrderStatus.RESULTED
    assert order.result == "Normal ranges"
    assert order.resulted_at is not None

    orders = labs_service.list_orders(db, appointment_id=appt.id)
    assert len(orders) == 1


def test_lab_cannot_cancel_resulted(db, scenario):
    booking, payment = _book(db, scenario)
    appt = reconciliation.confirm_payment(
        db, payment_id=payment.id, amount_paid=booking.amount,
        charge_status="success", gateway_response={"amount": booking.amount},
    ).appointment
    order = labs_service.order_test(db, appointment_id=appt.id, test_name="Malaria RDT")
    labs_service.submit_result(db, order.id, result="Negative")
    with pytest.raises(ConflictError):
        labs_service.cancel_order(db, order.id)
