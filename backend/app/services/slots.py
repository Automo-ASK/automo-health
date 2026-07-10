"""Slots & availability engine.

Concurrency: state transitions that must not race (hold / book) take a row lock
via ``SELECT ... FOR UPDATE`` on the slot, so two concurrent requests for the same
slot are serialized — the loser sees the updated status and is rejected. The
``version_id`` column additionally guards against lost updates across sessions.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import SlotStatus
from app.models.slot import Slot
from app.services.exceptions import NotFoundError, SlotUnavailableError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_slot(db: Session, slot_id: uuid.UUID) -> Slot:
    slot = db.get(Slot, slot_id)
    if slot is None:
        raise NotFoundError(f"Slot {slot_id} not found")
    return slot


def list_slots(
    db: Session,
    *,
    provider_id: uuid.UUID | None = None,
    service_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    only_open: bool = True,
) -> list[Slot]:
    stmt = select(Slot)
    if provider_id is not None:
        stmt = stmt.where(Slot.provider_id == provider_id)
    if service_id is not None:
        stmt = stmt.where(Slot.service_id == service_id)
    if date_from is not None:
        stmt = stmt.where(Slot.start_time >= date_from)
    if date_to is not None:
        stmt = stmt.where(Slot.start_time < date_to)
    if only_open:
        stmt = stmt.where(Slot.status == SlotStatus.OPEN)
    stmt = stmt.order_by(Slot.start_time)
    return list(db.execute(stmt).scalars().all())


def create_slot(
    db: Session,
    *,
    provider_id: uuid.UUID,
    service_id: uuid.UUID | None,
    start_time: datetime,
    end_time: datetime,
) -> Slot:
    slot = Slot(
        provider_id=provider_id,
        service_id=service_id,
        start_time=start_time,
        end_time=end_time,
        status=SlotStatus.OPEN,
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


def generate_slots(
    db: Session,
    *,
    provider_id: uuid.UUID,
    service_id: uuid.UUID | None,
    range_start: datetime,
    range_end: datetime,
    slot_minutes: int,
) -> list[Slot]:
    """Create back-to-back OPEN slots across [range_start, range_end).

    Existing slots for the same (provider, start_time) are skipped so the call is
    idempotent against the unique constraint.
    """
    existing = {
        s for s in db.execute(
            select(Slot.start_time).where(
                Slot.provider_id == provider_id,
                Slot.start_time >= range_start,
                Slot.start_time < range_end,
            )
        ).scalars().all()
    }

    step = timedelta(minutes=slot_minutes)
    created: list[Slot] = []
    cursor = range_start
    while cursor + step <= range_end:
        if cursor not in existing:
            slot = Slot(
                provider_id=provider_id,
                service_id=service_id,
                start_time=cursor,
                end_time=cursor + step,
                status=SlotStatus.OPEN,
            )
            db.add(slot)
            created.append(slot)
        cursor += step

    db.commit()
    for slot in created:
        db.refresh(slot)
    return created


def hold_slot(
    db: Session,
    *,
    slot_id: uuid.UUID,
    ttl_seconds: int | None = None,
) -> Slot:
    """Place a short-lived hold on an OPEN slot (or one whose hold has expired).

    Locks the slot row for the duration of the transaction so concurrent holds
    cannot both succeed.
    """
    ttl = ttl_seconds if ttl_seconds is not None else settings.slot_hold_ttl_seconds
    now = _utcnow()

    # Row lock: serialize concurrent hold attempts on this slot.
    slot = db.execute(
        select(Slot).where(Slot.id == slot_id).with_for_update()
    ).scalar_one_or_none()
    if slot is None:
        raise NotFoundError(f"Slot {slot_id} not found")

    if not _is_holdable(slot, now):
        db.rollback()
        raise SlotUnavailableError(f"Slot {slot_id} is not available (status={slot.status.value})")

    slot.status = SlotStatus.HELD
    slot.hold_expires_at = now + timedelta(seconds=ttl)
    db.commit()
    db.refresh(slot)
    return slot


def release_slot(db: Session, *, slot_id: uuid.UUID) -> Slot:
    """Return a HELD slot to OPEN. Locks the row while flipping status."""
    slot = db.execute(
        select(Slot).where(Slot.id == slot_id).with_for_update()
    ).scalar_one_or_none()
    if slot is None:
        raise NotFoundError(f"Slot {slot_id} not found")

    if slot.status == SlotStatus.HELD:
        slot.status = SlotStatus.OPEN
        slot.hold_expires_at = None
        db.commit()
        db.refresh(slot)
    return slot


def _is_holdable(slot: Slot, now: datetime) -> bool:
    """A slot can be held if it's OPEN, or HELD but its hold has already expired."""
    if slot.status == SlotStatus.OPEN:
        return True
    if slot.status == SlotStatus.HELD:
        return slot.hold_expires_at is None or slot.hold_expires_at <= now
    return False
