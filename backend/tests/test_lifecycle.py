"""Day 5 appointment lifecycle: complete, no-show, cancel, reschedule, follow-up."""

import pytest

from app.models.booking import Booking
from app.models.enums import AppointmentStatus, BookingStatus, SlotStatus
from app.services import appointments as appt_service
from app.services import bookings as bookings_service
from app.services import reconciliation
from app.services.exceptions import ConflictError
from tests.conftest import Scenario, make_slot


def _confirmed_appointment(db, sc: Scenario):
    booking, payment = bookings_service.create_booking(
        db, patient_id=sc.patient.id, slot_id=sc.slot.id, service_id=sc.service.id
    )
    result = reconciliation.confirm_payment(
        db, payment_id=payment.id, amount_paid=booking.amount,
        charge_status="success", gateway_response={"amount": booking.amount},
    )
    return result.appointment


def test_complete_appointment(db, scenario):
    appt = _confirmed_appointment(db, scenario)
    done = appt_service.complete_appointment(db, appt.id, notes="Patient stable.")
    assert done.status == AppointmentStatus.COMPLETED
    assert done.completed_at is not None
    assert done.notes == "Patient stable."

    # Completing again is a no-op (idempotent), and cancel is then blocked.
    again = appt_service.complete_appointment(db, appt.id)
    assert again.status == AppointmentStatus.COMPLETED
    with pytest.raises(ConflictError):
        appt_service.cancel_appointment(db, appt.id)


def test_no_show(db, scenario):
    appt = _confirmed_appointment(db, scenario)
    ns = appt_service.mark_no_show(db, appt.id)
    assert ns.status == AppointmentStatus.NO_SHOW


def test_cancel_releases_slot(db, scenario):
    appt = _confirmed_appointment(db, scenario)
    db.refresh(scenario.slot)
    assert scenario.slot.status == SlotStatus.BOOKED

    cancelled = appt_service.cancel_appointment(db, appt.id)
    assert cancelled.status == AppointmentStatus.CANCELLED
    db.refresh(scenario.slot)
    assert scenario.slot.status == SlotStatus.OPEN


def test_reschedule_moves_slot(db, scenario):
    appt = _confirmed_appointment(db, scenario)
    old_slot_id = appt.slot_id
    new_slot = make_slot(db, scenario.provider.id, scenario.service.id, days=3)

    moved = appt_service.reschedule_appointment(db, appt.id, new_slot_id=new_slot.id)
    assert moved.slot_id == new_slot.id
    assert moved.scheduled_start == new_slot.start_time

    db.refresh(new_slot)
    assert new_slot.status == SlotStatus.BOOKED
    old = db.get(type(scenario.slot), old_slot_id)
    assert old.status == SlotStatus.OPEN


def test_follow_up_links_parent(db, scenario):
    parent = _confirmed_appointment(db, scenario)
    fu_slot = make_slot(db, scenario.provider.id, scenario.service.id, days=7)

    follow = appt_service.create_follow_up(
        db, parent.id, new_slot_id=fu_slot.id, notes="Review in 1 week"
    )
    assert follow.parent_appointment_id == parent.id
    assert follow.status == AppointmentStatus.SCHEDULED
    assert follow.notes == "Review in 1 week"

    db.refresh(fu_slot)
    assert fu_slot.status == SlotStatus.BOOKED

    booking = db.get(Booking, follow.booking_id)
    assert booking.status == BookingStatus.CONFIRMED
