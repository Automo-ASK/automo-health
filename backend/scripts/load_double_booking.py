"""Concurrency load test: hammer one slot with N simultaneous bookings (Day 7).

Spins up N threads, each with its own DB session, all racing to book the *same* slot.
The slot row-lock (``SELECT ... FOR UPDATE``) plus the unique bookings.slot_id
constraint must guarantee exactly one winner; everyone else is cleanly rejected.

Creates its own throwaway provider/service/slot/patients and deletes them afterwards,
so it's safe to run repeatedly against a shared database.

    python -m scripts.load_double_booking [N]
"""

from __future__ import annotations

import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from app.core.database import SessionLocal
from app.models.appointment import Appointment
from app.models.booking import Booking
from app.models.patient import Patient
from app.models.payment import Payment
from app.models.provider import Provider
from app.models.service import Service
from app.models.slot import Slot
from app.services import bookings as bookings_service
from app.services.exceptions import DomainError


def _setup(n: int):
    uid = uuid.uuid4().hex[:10]
    db = SessionLocal()
    try:
        provider = Provider(full_name=f"Load {uid}", email=f"load-{uid}@test.local")
        db.add(provider)
        db.flush()
        service = Service(
            provider_id=provider.id, name="Load Consult", price_amount=500_000, currency="NGN"
        )
        db.add(service)
        db.flush()
        start = datetime.now(timezone.utc) + timedelta(days=1)
        slot = Slot(
            provider_id=provider.id, service_id=service.id,
            start_time=start, end_time=start + timedelta(minutes=30),
        )
        db.add(slot)
        patients = [
            Patient(full_name=f"P{i}-{uid}", email=f"p{i}-{uid}@test.local", phone="+2348030000000")
            for i in range(n)
        ]
        db.add_all(patients)
        db.commit()
        return (
            provider.id, service.id, slot.id, [p.id for p in patients]
        )
    finally:
        db.close()


def _teardown(provider_id, slot_id, patient_ids):
    db = SessionLocal()
    try:
        booking_ids = [
            b.id for b in db.query(Booking).filter(Booking.slot_id == slot_id).all()
        ]
        if booking_ids:
            db.execute(delete(Appointment).where(Appointment.booking_id.in_(booking_ids)))
            db.execute(delete(Payment).where(Payment.booking_id.in_(booking_ids)))
            db.execute(delete(Booking).where(Booking.id.in_(booking_ids)))
        db.execute(delete(Slot).where(Slot.id == slot_id))
        db.execute(delete(Patient).where(Patient.id.in_(patient_ids)))
        db.execute(delete(Service).where(Service.provider_id == provider_id))
        db.execute(delete(Provider).where(Provider.id == provider_id))
        db.commit()
    finally:
        db.close()


def run(n: int = 10) -> int:
    provider_id, service_id, slot_id, patient_ids = _setup(n)
    results = {"success": 0, "rejected": 0, "error": 0}
    lock = threading.Lock()
    barrier = threading.Barrier(n)

    def attempt(patient_id):
        barrier.wait()  # release all threads at once for maximum contention
        db = SessionLocal()
        try:
            bookings_service.create_booking(
                db, patient_id=patient_id, slot_id=slot_id, service_id=service_id
            )
            with lock:
                results["success"] += 1
        except DomainError:
            with lock:
                results["rejected"] += 1
        except Exception:  # noqa: BLE001 — e.g. unique-constraint race surfaced as IntegrityError
            with lock:
                results["rejected"] += 1
        finally:
            db.close()

    try:
        threads = [threading.Thread(target=attempt, args=(pid,)) for pid in patient_ids]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        _teardown(provider_id, slot_id, patient_ids)

    print(f"Concurrent bookings on 1 slot (N={n}): {results}")
    ok = results["success"] == 1
    print("PASS — exactly one winner" if ok else "FAIL — expected exactly 1 success")
    return 0 if ok else 1


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    raise SystemExit(run(count))
