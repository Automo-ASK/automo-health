"""Patient lookup and creation helpers for channel flows.

USSD and SMS callers arrive by phone number only — no email, no name yet.
We upsert a Patient row using a synthetic email derived from the phone so
the NOT NULL constraint on ``email`` is satisfied without requiring the
patient to identify themselves before booking.

The synthetic email is internal and is never shown to the patient.  It can
be replaced by a real email later if the patient supplies one.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.patient import Patient


def _synthetic_email(phone: str) -> str:
    """Derive a deterministic internal email from an E.164 phone number.

    Uses a real TLD (``.health``) — Paystack's live transaction/initialize
    validates the email format and rejects made-up TLDs like ``.automo`` with
    "Invalid Email Address Passed", which only surfaces once Paystack is out
    of mock mode.
    """
    normalised = phone.lstrip("+").replace(" ", "")
    return f"{normalised}@patients.automo.health"


def get_or_create_by_phone(db: Session, phone: str) -> Patient:
    """Return the Patient for *phone*, creating one if none exists."""
    patient = db.execute(
        select(Patient).where(Patient.phone == phone)
    ).scalar_one_or_none()

    if patient is None:
        patient = Patient(
            full_name="",
            email=_synthetic_email(phone),
            phone=phone,
        )
        db.add(patient)
        db.flush()

    return patient
