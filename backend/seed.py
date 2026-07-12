"""Demo seed script.

Creates one provider, three services, and 7 days of 30-minute slots
(Mon-Sat, 09:00-17:00 WAT) so the USSD and WhatsApp flows have real data
to book against.

Usage (from the backend/ directory with the virtualenv active):

    python seed.py

Running it twice is safe — the provider and services are looked up by
name before insert so duplicates won't be created.  Slots use the
(provider_id, start_time) unique constraint to skip any that already exist.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.provider import Provider
from app.models.service import Service
from app.models.slot import Slot
from app.models.enums import SlotStatus

WAT = ZoneInfo("Africa/Lagos")

PROVIDER_NAME = "Dr. Demo Adeyemi"
PROVIDER_EMAIL = "demo.adeyemi@automo.test"

SERVICES = [
    {"name": "General Consultation", "duration_minutes": 30, "price_kobo": 200_000},
    {"name": "Lab Test",             "duration_minutes": 30, "price_kobo": 150_000},
    {"name": "Virtual Follow-up",    "duration_minutes": 30, "price_kobo": 100_000},
]

# Each service gets a non-overlapping time window so the unique
# (provider_id, start_time) constraint is never violated.
SERVICE_WINDOWS = [
    {"name": "General Consultation", "start_hour": 9,  "end_hour": 13},
    {"name": "Lab Test",             "start_hour": 13, "end_hour": 15},
    {"name": "Virtual Follow-up",    "start_hour": 15, "end_hour": 17},
]
SLOT_MINUTES = 30
DAYS_AHEAD   = 7


def _get_or_create_provider(db) -> Provider:
    provider = db.execute(
        select(Provider).where(Provider.email == PROVIDER_EMAIL)
    ).scalar_one_or_none()
    if provider is None:
        provider = Provider(
            full_name=PROVIDER_NAME,
            email=PROVIDER_EMAIL,
            specialty="General Practice",
            timezone="Africa/Lagos",
        )
        db.add(provider)
        db.flush()
        print(f"  Created provider: {PROVIDER_NAME}")
    else:
        print(f"  Provider already exists: {PROVIDER_NAME}")
    return provider


def _get_or_create_services(db, provider_id) -> list[Service]:
    created = []
    for spec in SERVICES:
        svc = db.execute(
            select(Service).where(
                Service.provider_id == provider_id,
                Service.name == spec["name"],
            )
        ).scalar_one_or_none()
        if svc is None:
            svc = Service(
                provider_id=provider_id,
                name=spec["name"],
                duration_minutes=spec["duration_minutes"],
                price_amount=spec["price_kobo"],
                currency="NGN",
                is_active=True,
            )
            db.add(svc)
            db.flush()
            print(f"  Created service: {spec['name']} (₦{spec['price_kobo'] // 100:,})")
        else:
            print(f"  Service already exists: {spec['name']}")
        created.append(svc)
    return created


def _generate_slots(db, provider_id, services: list[Service]) -> int:
    """Create 30-min slots per service across the next 7 days.

    Each service occupies a non-overlapping time window (see SERVICE_WINDOWS)
    so the unique (provider_id, start_time) constraint is never violated.
    """
    service_map = {s.name: s for s in services}
    today = date.today()
    slot_count = 0

    for day_offset in range(1, DAYS_AHEAD + 1):
        target_date = today + timedelta(days=day_offset)
        if target_date.weekday() == 6:  # skip Sundays
            continue

        for window in SERVICE_WINDOWS:
            service = service_map.get(window["name"])
            if service is None:
                continue

            cursor = datetime(
                target_date.year, target_date.month, target_date.day,
                window["start_hour"], 0, 0,
                tzinfo=WAT,
            )
            window_end = cursor.replace(hour=window["end_hour"], minute=0, second=0)

            while cursor + timedelta(minutes=SLOT_MINUTES) <= window_end:
                start_utc = cursor.astimezone(ZoneInfo("UTC"))
                end_utc = (cursor + timedelta(minutes=SLOT_MINUTES)).astimezone(ZoneInfo("UTC"))

                existing = db.execute(
                    select(Slot).where(
                        Slot.provider_id == provider_id,
                        Slot.start_time == start_utc,
                    )
                ).scalar_one_or_none()

                if existing is None:
                    db.add(Slot(
                        provider_id=provider_id,
                        service_id=service.id,
                        start_time=start_utc,
                        end_time=end_utc,
                        status=SlotStatus.OPEN,
                    ))
                    slot_count += 1

                cursor += timedelta(minutes=SLOT_MINUTES)

    return slot_count


def main() -> None:
    print("Seeding demo data...")
    db = SessionLocal()
    try:
        provider = _get_or_create_provider(db)
        services = _get_or_create_services(db, provider.id)
        n = _generate_slots(db, provider.id, services)
        db.commit()
        print(f"  Created {n} new slots across next {DAYS_AHEAD} days.")
        print("Done.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
