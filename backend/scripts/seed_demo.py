"""Seed demo data for Automo Health (Day 7).

Idempotent: keyed on provider/patient email and (provider, slot start), so it can be
re-run safely. Creates a couple of providers with services, a week of future open
slots, and a handful of patients.

Run from the backend/ directory:

    python -m scripts.seed_demo
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.patient import Patient
from app.models.provider import Provider
from app.models.service import Service
from app.services import slots as slots_service

# (name, email, specialty, [ (service_name, duration_min, price_kobo) ])
PROVIDERS = [
    (
        "Dr. Amina Bello",
        "amina.bello@automo.health",
        "General Practice",
        [
            ("General Consultation", 30, 500_000),   # ₦5,000.00
            ("Follow-up Review", 15, 250_000),        # ₦2,500.00
        ],
    ),
    (
        "Dr. Chidi Okafor",
        "chidi.okafor@automo.health",
        "Paediatrics",
        [
            ("Child Wellness Check", 30, 700_000),    # ₦7,000.00
        ],
    ),
]

PATIENTS = [
    ("Ngozi Eze", "ngozi.eze@example.com", "+2348030000001"),
    ("Tunde Adeyemi", "tunde.adeyemi@example.com", "+2348030000002"),
    ("Fatima Sani", "fatima.sani@example.com", "+2348030000003"),
]


def _get_or_create_provider(db: Session, name: str, email: str, specialty: str) -> Provider:
    provider = db.execute(
        select(Provider).where(Provider.email == email)
    ).scalar_one_or_none()
    if provider is None:
        provider = Provider(full_name=name, email=email, specialty=specialty)
        db.add(provider)
        db.flush()
    return provider


def _get_or_create_service(
    db: Session, provider: Provider, name: str, duration: int, price: int
) -> Service:
    service = db.execute(
        select(Service).where(
            Service.provider_id == provider.id, Service.name == name
        )
    ).scalar_one_or_none()
    if service is None:
        service = Service(
            provider_id=provider.id,
            name=name,
            duration_minutes=duration,
            price_amount=price,
            currency="NGN",
        )
        db.add(service)
        db.flush()
    return service


def _get_or_create_patient(db: Session, name: str, email: str, phone: str) -> Patient:
    patient = db.execute(
        select(Patient).where(Patient.email == email)
    ).scalar_one_or_none()
    if patient is None:
        patient = Patient(full_name=name, email=email, phone=phone)
        db.add(patient)
        db.flush()
    return patient


def seed() -> dict[str, int]:
    db = SessionLocal()
    counts = {"providers": 0, "services": 0, "patients": 0, "slots": 0}
    try:
        for name, email, specialty, services in PROVIDERS:
            provider = _get_or_create_provider(db, name, email, specialty)
            counts["providers"] += 1
            first_service: Service | None = None
            for s_name, dur, price in services:
                service = _get_or_create_service(db, provider, s_name, dur, price)
                first_service = first_service or service
                counts["services"] += 1
            db.commit()

            # Generate weekday 09:00–13:00 slots for the next 5 days (idempotent).
            today = datetime.now(timezone.utc).date()
            for day_offset in range(1, 6):
                day = today + timedelta(days=day_offset)
                start = datetime.combine(day, time(9, 0), tzinfo=timezone.utc)
                end = datetime.combine(day, time(13, 0), tzinfo=timezone.utc)
                created = slots_service.generate_slots(
                    db,
                    provider_id=provider.id,
                    service_id=first_service.id if first_service else None,
                    range_start=start,
                    range_end=end,
                    slot_minutes=30,
                )
                counts["slots"] += len(created)

        for name, email, phone in PATIENTS:
            _get_or_create_patient(db, name, email, phone)
            counts["patients"] += 1
        db.commit()
    finally:
        db.close()
    return counts


if __name__ == "__main__":
    result = seed()
    print("Seeded demo data:")
    for k, v in result.items():
        print(f"  {k}: {v}")
