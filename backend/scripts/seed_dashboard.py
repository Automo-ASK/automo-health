"""Seed the staff dashboards with slug'd providers/services, a few days of slots,
and today's demo queue — the DB equivalent of the old backend-stub seed.

Idempotent: providers/services are keyed on slug, slots on (provider, start), and
today's queue is only seeded once (guarded on a marker patient). Re-running adds
future slots but never duplicates today's queue.

Run from the backend/ directory:

    python -m scripts.seed_dashboard
"""

from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.appointment import Appointment
from app.models.booking import Booking
from app.models.emergency import Emergency
from app.models.enums import (
    AppointmentStatus,
    BookingStatus,
    PaymentProvider,
    PaymentStatus,
    SlotStatus,
)
from app.models.patient import Patient
from app.models.payment import Payment
from app.models.provider import Provider
from app.models.service import Service
from app.models.slot import Slot

WAT = timezone(timedelta(hours=1))

# (slug, name, specialty)
PROVIDERS = [
    ("prov_ade", "Dr. Adeyemi", "General Practice"),
    ("prov_ola", "Dr. Olamide", "General Practice"),
    ("prov_lab", "Lab Desk", None),
]

# (slug, name, price_kobo, duration_min, owner_slug)
SERVICES = [
    ("svc_consult", "General Consultation", 500_000, 20, "prov_ade"),
    ("svc_followup", "Chronic Care Follow-up (Virtual)", 350_000, 15, "prov_ola"),
    ("svc_lab_malaria", "Malaria Test", 300_000, 15, "prov_lab"),
]

# Slot templates: (provider_slug, service_slug, start_hour, end_hour, step_min)
SLOT_PLAN = [
    ("prov_ade", "svc_consult", 9, 13, 20),
    ("prov_ola", "svc_consult", 9, 13, 20),
    ("prov_lab", "svc_lab_malaria", 9, 13, 15),
    ("prov_ola", "svc_followup", 14, 16, 15),
]


def _get_or_create_provider(db: Session, slug: str, name: str, specialty: str | None) -> Provider:
    p = db.execute(select(Provider).where(Provider.slug == slug)).scalar_one_or_none()
    if p is None:
        p = Provider(
            full_name=name, email=f"{slug}@automo.health", slug=slug, specialty=specialty
        )
        db.add(p)
        db.flush()
    return p


def _get_or_create_service(
    db: Session, slug: str, name: str, price: int, dur: int, provider: Provider
) -> Service:
    s = db.execute(select(Service).where(Service.slug == slug)).scalar_one_or_none()
    if s is None:
        s = Service(
            provider_id=provider.id, slug=slug, name=name,
            price_amount=price, duration_minutes=dur, currency="NGN",
        )
        db.add(s)
        db.flush()
    return s


def _get_or_create_patient(db: Session, name: str, email: str, phone: str) -> Patient:
    p = db.execute(select(Patient).where(Patient.email == email)).scalar_one_or_none()
    if p is None:
        p = Patient(full_name=name, email=email, phone=phone)
        db.add(p)
        db.flush()
    return p


def _ensure_slot(db: Session, provider: Provider, service: Service, start: datetime, dur: int) -> Slot:
    existing = db.execute(
        select(Slot).where(Slot.provider_id == provider.id, Slot.start_time == start)
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    slot = Slot(
        provider_id=provider.id,
        service_id=service.id,
        start_time=start,
        end_time=start + timedelta(minutes=dur),
        status=SlotStatus.OPEN,
    )
    db.add(slot)
    db.flush()
    return slot


def seed() -> dict[str, int]:
    db = SessionLocal()
    counts = {"providers": 0, "services": 0, "slots": 0, "queue": 0, "emergencies": 0}
    try:
        providers: dict[str, Provider] = {}
        for slug, name, spec in PROVIDERS:
            providers[slug] = _get_or_create_provider(db, slug, name, spec)
            counts["providers"] += 1

        services: dict[str, Service] = {}
        for slug, name, price, dur, owner in SERVICES:
            services[slug] = _get_or_create_service(db, slug, name, price, dur, providers[owner])
            counts["services"] += 1
        db.commit()

        # Slots: today + next 3 days.
        today = datetime.now(WAT).date()
        for day_offset in range(0, 4):
            day = today + timedelta(days=day_offset)
            for prov_slug, svc_slug, h0, h1, step in SLOT_PLAN:
                provider, service = providers[prov_slug], services[svc_slug]
                t = datetime.combine(day, time(h0, 0), tzinfo=WAT)
                day_end = datetime.combine(day, time(h1, 0), tzinfo=WAT)
                while t < day_end:
                    _ensure_slot(db, provider, service, t, step)
                    t += timedelta(minutes=step)
        db.commit()
        counts["slots"] = len(
            db.execute(
                select(Slot.id).where(
                    Slot.start_time >= datetime.combine(today, time.min, tzinfo=WAT)
                )
            ).all()
        )

        # Today's demo queue — seed once (guard on a marker patient's appt today).
        marker = db.execute(
            select(Patient).where(Patient.email == "chidi.demo@automo.health")
        ).scalar_one_or_none()
        already = False
        if marker is not None:
            start_today = datetime.combine(today, time.min, tzinfo=WAT)
            already = db.execute(
                select(Appointment).where(
                    Appointment.patient_id == marker.id,
                    Appointment.scheduled_start >= start_today,
                )
            ).first() is not None

        if not already:
            counts["queue"] = _seed_today_queue(db, providers, services, today)
            counts["emergencies"] = _seed_emergency(db, today)
            db.commit()
        return counts
    finally:
        db.close()


# (name, email, phone, provider_slug, service_slug, status, paid, home_reading, test_details)
QUEUE_ROWS = [
    ("Chidi Okafor", "chidi.demo@automo.health", "+2348012345670", "prov_ade", "svc_consult", "done", True, None, None),
    ("Amina Bello", "amina.demo@automo.health", "+2348012345671", "prov_ade", "svc_consult", "scheduled", True, None, None),
    ("Tunde Balogun", "tunde.demo@automo.health", "+2348012345672", "prov_ade", "svc_consult", "scheduled", True, None, None),
    ("Mama Ronke Adesanya", "ronke.demo@automo.health", "+2348012345673", "prov_ade", "svc_followup", "scheduled", True,
     "BP 148/94, taken this morning", None),
    ("Kunle Afolayan", "kunle.demo@automo.health", "+2348012345674", "prov_lab", "svc_lab_malaria", "scheduled", True,
     None, "Malaria (RDT) — ordered by Dr. Adeyemi after yesterday's consult"),
    ("Ngozi Okonkwo", "ngozi.demo@automo.health", "+2348012345675", "prov_lab", "svc_lab_malaria", "scheduled", True,
     None, "Malaria (RDT) — repeat test, fever persisting after treatment"),
    ("Ibrahim Musa", "ibrahim.demo@automo.health", "+2348012345676", "prov_ade", "svc_consult", "pending_payment", False, None, None),
]


def _open_slots(db: Session, provider: Provider, today) -> list[Slot]:
    start = datetime.combine(today, time.min, tzinfo=WAT)
    end = start + timedelta(days=1)
    return list(
        db.execute(
            select(Slot)
            .where(
                Slot.provider_id == provider.id,
                Slot.status == SlotStatus.OPEN,
                Slot.start_time >= start,
                Slot.start_time < end,
            )
            .order_by(Slot.start_time)
        ).scalars().all()
    )


def _seed_today_queue(db, providers, services, today) -> int:
    now = datetime.now(timezone.utc)
    pools: dict[str, list[Slot]] = {}
    made = 0
    for name, email, phone, prov_slug, svc_slug, status_, paid, home_reading, test_details in QUEUE_ROWS:
        provider, service = providers[prov_slug], services[svc_slug]
        pool = pools.setdefault(prov_slug, _open_slots(db, provider, today))
        if not pool:
            continue
        slot = pool.pop(0)
        patient = _get_or_create_patient(db, name, email, phone)

        if status_ == "pending_payment":
            slot.status = SlotStatus.HELD
            slot.hold_expires_at = now + timedelta(minutes=15)
            booking = Booking(
                patient_id=patient.id, slot_id=slot.id, service_id=service.id,
                status=BookingStatus.PENDING_PAYMENT, amount=service.price_amount,
                currency="NGN", expires_at=now + timedelta(minutes=15),
            )
            db.add(booking)
            db.flush()
            db.add(Payment(
                booking_id=booking.id, provider=PaymentProvider.PAYSTACK,
                status=PaymentStatus.PENDING, amount=service.price_amount, currency="NGN",
                reference=f"SEED-{uuid.uuid4().hex[:16].upper()}",
            ))
            made += 1
            continue

        slot.status = SlotStatus.BOOKED
        slot.hold_expires_at = None
        booking = Booking(
            patient_id=patient.id, slot_id=slot.id, service_id=service.id,
            status=BookingStatus.CONFIRMED, amount=service.price_amount, currency="NGN",
        )
        db.add(booking)
        db.flush()
        if paid:
            db.add(Payment(
                booking_id=booking.id, provider=PaymentProvider.PAYSTACK,
                status=PaymentStatus.SUCCESS, amount=service.price_amount, currency="NGN",
                reference=f"SEED-{uuid.uuid4().hex[:16].upper()}", paid_at=now,
            ))
        appt_status = AppointmentStatus.COMPLETED if status_ == "done" else AppointmentStatus.SCHEDULED
        db.add(Appointment(
            booking_id=booking.id, patient_id=patient.id, provider_id=provider.id,
            slot_id=slot.id, scheduled_start=slot.start_time, scheduled_end=slot.end_time,
            status=appt_status, completed_at=now if appt_status == AppointmentStatus.COMPLETED else None,
            home_reading=home_reading, test_details=test_details,
        ))
        made += 1
    return made


def _seed_emergency(db, today) -> int:
    patient = _get_or_create_patient(
        db, "Baba Nurudeen", "nurudeen.demo@automo.health", "+2348012345699"
    )
    db.add(Emergency(
        patient_id=patient.id,
        category="Chest pain / breathing difficulty",
        description="My father is having chest pain and struggling to breathe.",
    ))
    return 1


if __name__ == "__main__":
    result = seed()
    print("Seeded dashboard data:")
    for k, v in result.items():
        print(f"  {k}: {v}")
