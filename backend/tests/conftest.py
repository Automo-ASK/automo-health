"""Test harness (Day 7).

Each test runs inside an outer transaction that is rolled back on teardown, so tests
leave no residue in the (Neon) database. The session is opened with
``join_transaction_mode="create_savepoint"`` so the service layer's ``commit()`` calls
land as SAVEPOINT releases inside that outer transaction instead of persisting.

Payments run in Paystack mock mode (placeholder key), so no network is needed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models.patient import Patient
from app.models.provider import Provider
from app.models.service import Service
from app.models.slot import Slot


@pytest.fixture
def db():
    connection = engine.connect()
    trans = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


def _uid() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Scenario:
    provider: Provider
    service: Service
    patient: Patient
    slot: Slot


@pytest.fixture
def scenario(db: Session) -> Scenario:
    """A fresh provider + service + open future slot + patient, with unique keys."""
    uid = _uid()
    provider = Provider(
        full_name=f"Dr Test {uid}", email=f"prov-{uid}@test.local", specialty="GP"
    )
    db.add(provider)
    db.flush()

    service = Service(
        provider_id=provider.id,
        name="Consultation",
        duration_minutes=30,
        price_amount=500_000,  # ₦5,000.00
        currency="NGN",
    )
    db.add(service)
    db.flush()

    start = datetime.now(timezone.utc) + timedelta(days=1)
    slot = Slot(
        provider_id=provider.id,
        service_id=service.id,
        start_time=start,
        end_time=start + timedelta(minutes=30),
    )
    db.add(slot)

    patient = Patient(
        full_name=f"Patient {uid}", email=f"pat-{uid}@test.local", phone="+2348030000000"
    )
    db.add(patient)
    db.commit()
    return Scenario(provider=provider, service=service, patient=patient, slot=slot)


def make_slot(db: Session, provider_id, service_id, *, days: int = 2) -> Slot:
    """Create an extra open slot (e.g. for reschedule/follow-up targets)."""
    start = datetime.now(timezone.utc) + timedelta(days=days)
    slot = Slot(
        provider_id=provider_id,
        service_id=service_id,
        start_time=start,
        end_time=start + timedelta(minutes=30),
    )
    db.add(slot)
    db.commit()
    return slot
