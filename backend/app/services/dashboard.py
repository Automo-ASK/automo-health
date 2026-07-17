"""Staff-dashboard read/close model — the features previously served by the
throwaway ``backend-stub``, now folded into the real backend against the DB.

The doctor/lab/cashier screens consume three shapes:
  * ``provider_queue`` — today's live queue for a provider (doctor board, lab board)
  * ``day_summary``   — every appointment on the day + still-owing holds (cashier)
  * ``cleared_payments`` — the day's settled payments (cashier ledger)

plus ``close_visit`` (the doctor/lab "Done / Follow-up / Admitted" action) and the
``resolve_provider`` / ``resolve_service`` helpers that accept a stable slug
(``prov_ade``, ``svc_consult``) *or* a UUID, so the frontend's fixed identifiers
keep working across re-seeds.
"""

import uuid
from datetime import date as date_cls
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.booking import Booking
from app.models.enums import (
    AppointmentStatus,
    BookingStatus,
    NotificationEvent,
    PaymentStatus,
)
from app.models.patient import Patient
from app.models.payment import Payment
from app.models.provider import Provider
from app.models.service import Service
from app.models.slot import Slot
from app.services import messaging, notifications
from app.services.exceptions import ConflictError, NotFoundError

# Clinic-local timezone (WAT, UTC+1). Slot times are authored in WAT; "today"
# for the dashboards means the WAT calendar day.
WAT = timezone(timedelta(hours=1))

# Appointments a patient is still expected for — the live queue.
_ACTIVE = (AppointmentStatus.SCHEDULED,)

# Frontend/stub status vocabulary (kept identical so the CSS chips still match).
_STATUS_OUT = {
    AppointmentStatus.SCHEDULED: "confirmed",
    AppointmentStatus.COMPLETED: "done",
    AppointmentStatus.ADMITTED: "admitted",
    AppointmentStatus.NO_SHOW: "no_show",
    AppointmentStatus.CANCELLED: "cancelled",
}


def _uuid_or_none(ref: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(ref))
    except (ValueError, AttributeError, TypeError):
        return None


def resolve_provider(db: Session, ref: str) -> Provider:
    """Look up a provider by UUID or by stable slug (e.g. ``prov_ade``)."""
    pid = _uuid_or_none(ref)
    stmt = select(Provider).where(Provider.id == pid) if pid else select(Provider).where(Provider.slug == ref)
    provider = db.execute(stmt).scalar_one_or_none()
    if provider is None:
        raise NotFoundError(f"Provider {ref} not found")
    return provider


def resolve_service(db: Session, ref: str) -> Service:
    """Look up a service by UUID or by stable slug (e.g. ``svc_consult``)."""
    sid = _uuid_or_none(ref)
    stmt = select(Service).where(Service.id == sid) if sid else select(Service).where(Service.slug == ref)
    service = db.execute(stmt).scalar_one_or_none()
    if service is None:
        raise NotFoundError(f"Service {ref} not found")
    return service


def _wat_day_bounds(day: date_cls | None) -> tuple[datetime, datetime]:
    """Half-open [start, end) UTC interval covering a WAT calendar day."""
    day = day or datetime.now(WAT).date()
    start = datetime.combine(day, time.min, tzinfo=WAT)
    return start, start + timedelta(days=1)


def service_visit_type(service: Service | None) -> str:
    """Map a service to the dashboard visit type: physical / virtual / lab."""
    if service is None:
        return "physical"
    hay = f"{service.slug or ''} {service.name}".lower()
    if any(w in hay for w in ("lab", "test", "blood", "sample", "malaria")):
        return "lab"
    if any(w in hay for w in ("virtual", "followup", "follow-up", "online", "tele", "video", "chronic")):
        return "virtual"
    return "physical"


def _services_by_id(db: Session) -> dict[uuid.UUID, Service]:
    return {s.id: s for s in db.execute(select(Service)).scalars().all()}


# --------------------------------------------------------------------------- #
# Doctor / lab queue                                                          #
# --------------------------------------------------------------------------- #

def provider_queue(db: Session, provider_ref: str, day: date_cls | None = None) -> list[dict]:
    """Today's live queue for a provider, ordered by slot time.

    Each row is enriched for the board: position, is_next, patient, service,
    visit type, and any home reading / test details attached to the visit.
    """
    provider = resolve_provider(db, provider_ref)
    start, end = _wat_day_bounds(day)
    services = _services_by_id(db)

    rows = db.execute(
        select(Appointment)
        .where(
            Appointment.provider_id == provider.id,
            Appointment.status.in_(_ACTIVE),
            Appointment.scheduled_start >= start,
            Appointment.scheduled_start < end,
        )
        .order_by(Appointment.scheduled_start)
    ).scalars().all()

    out: list[dict] = []
    for i, appt in enumerate(rows):
        service = services.get(appt.booking.service_id) if appt.booking else None
        out.append(
            {
                "id": str(appt.id),
                "position": i + 1,
                "is_next": i == 0,
                "patient_name": appt.patient.full_name if appt.patient else "Patient",
                "patient_phone": appt.patient.phone if appt.patient else None,
                "type": service_visit_type(service),
                "channel": "whatsapp",
                "service_name": service.name if service else "Consultation",
                "slot_time": appt.scheduled_start.isoformat(),
                "status": _STATUS_OUT.get(appt.status, appt.status.value),
                "home_reading": appt.home_reading,
                "test_details": appt.test_details,
                "collection_date": appt.collection_date.isoformat() if appt.collection_date else None,
            }
        )
    return out


# --------------------------------------------------------------------------- #
# Cashier day view                                                            #
# --------------------------------------------------------------------------- #

def day_summary(db: Session, day: date_cls | None = None) -> list[dict]:
    """Every appointment on the day (all providers) plus still-owing holds.

    Confirmed/seen appointments come from ``appointments``; the "still owing"
    rows are ``PENDING_PAYMENT`` bookings whose held slot is on the day.
    """
    start, end = _wat_day_bounds(day)
    services = _services_by_id(db)
    rows: list[dict] = []

    appts = db.execute(
        select(Appointment)
        .where(
            Appointment.status != AppointmentStatus.CANCELLED,
            Appointment.scheduled_start >= start,
            Appointment.scheduled_start < end,
        )
        .order_by(Appointment.scheduled_start)
    ).scalars().all()
    for appt in appts:
        booking = appt.booking
        service = services.get(booking.service_id) if booking else None
        paid = bool(booking and booking.payment and booking.payment.status == PaymentStatus.SUCCESS)
        rows.append(
            {
                "id": str(appt.id),
                "patient_name": appt.patient.full_name if appt.patient else "Patient",
                "service_name": service.name if service else "Consultation",
                "slot_time": appt.scheduled_start.isoformat(),
                "type": service_visit_type(service),
                "channel": "whatsapp",
                "status": _STATUS_OUT.get(appt.status, appt.status.value),
                "consultation_fee": booking.amount if booking else 0,
                "paid": paid,
            }
        )

    # Still-owing: held bookings awaiting payment, slot on the day.
    holds = db.execute(
        select(Booking, Slot)
        .join(Slot, Slot.id == Booking.slot_id)
        .where(
            Booking.status == BookingStatus.PENDING_PAYMENT,
            Slot.start_time >= start,
            Slot.start_time < end,
        )
        .order_by(Slot.start_time)
    ).all()
    for booking, slot in holds:
        service = services.get(booking.service_id)
        rows.append(
            {
                "id": str(booking.id),
                "patient_name": booking.patient.full_name if booking.patient else "Patient",
                "service_name": service.name if service else "Consultation",
                "slot_time": slot.start_time.isoformat(),
                "type": service_visit_type(service),
                "channel": "whatsapp",
                "status": "pending_payment",
                "consultation_fee": booking.amount,
                "paid": False,
            }
        )

    rows.sort(key=lambda r: r["slot_time"])
    return rows


def cleared_payments(db: Session, day: date_cls | None = None) -> list[dict]:
    """The day's settled payments — the cashier's cleared ledger."""
    start, end = _wat_day_bounds(day)
    services = _services_by_id(db)

    payments = db.execute(
        select(Payment)
        .where(
            Payment.status == PaymentStatus.SUCCESS,
            Payment.paid_at >= start,
            Payment.paid_at < end,
        )
        .order_by(Payment.paid_at)
    ).scalars().all()

    out: list[dict] = []
    for pay in payments:
        booking = pay.booking
        appt = booking.appointment if booking else None
        service = services.get(booking.service_id) if booking else None
        patient = booking.patient if booking else None
        out.append(
            {
                "payment_id": str(pay.id),
                "appointment_id": str(appt.id) if appt else None,
                "patient_name": patient.full_name if patient else "Patient",
                "service_name": service.name if service else "Consultation",
                "method": "link" if pay.provider.value == "paystack" else pay.provider.value,
                "amount": pay.amount,
                "consultation_fee": booking.amount if booking else pay.amount,
                "platform_fee": 0,
                "paid_at": pay.paid_at.isoformat() if pay.paid_at else None,
                "channel": "whatsapp",
            }
        )
    return out


# --------------------------------------------------------------------------- #
# Close a visit (doctor / lab)                                                #
# --------------------------------------------------------------------------- #

def close_visit(
    db: Session,
    appointment_id: uuid.UUID,
    *,
    state: str = "done",
    collection_date: str | None = None,
) -> dict:
    """Close a visit and advance the queue.

    ``state`` is ``done`` / ``follow_up`` (both COMPLETED) or ``admitted``.
    ``collection_date`` (yyyy-mm-dd) is the lab's results-ready date the patient
    is told to collect on. Idempotent on an already-closed visit.
    """
    appt = db.execute(
        select(Appointment).where(Appointment.id == appointment_id).with_for_update()
    ).scalar_one_or_none()
    if appt is None:
        raise NotFoundError(f"Appointment {appointment_id} not found")

    if collection_date:
        try:
            appt.collection_date = date_cls.fromisoformat(collection_date)
        except ValueError as exc:
            raise ConflictError(f"Invalid collection_date: {collection_date}") from exc

    already_closed = appt.status in (AppointmentStatus.COMPLETED, AppointmentStatus.ADMITTED)
    if not already_closed and appt.status != AppointmentStatus.SCHEDULED:
        raise ConflictError(f"Cannot close a {appt.status.value} appointment")

    target = AppointmentStatus.ADMITTED if state == "admitted" else AppointmentStatus.COMPLETED
    if not already_closed:
        appt.status = target
        if target == AppointmentStatus.COMPLETED:
            appt.completed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(appt)

    if not already_closed:
        notifications.dispatch(
            NotificationEvent.APPOINTMENT_COMPLETED,
            {"appointment_id": str(appt.id), "patient_id": str(appt.patient_id), "state": state},
        )
        if appt.collection_date:
            messaging.send_to_patient(
                appt.patient,
                f"Your results will be ready to collect on {appt.collection_date:%a %d %b}. 🧪",
            )
        else:
            messaging.send_to_patient(
                appt.patient, "Your visit is complete. Get well soon! 🙏"
            )

    return {
        "id": str(appt.id),
        "status": _STATUS_OUT.get(appt.status, appt.status.value),
        "collection_date": appt.collection_date.isoformat() if appt.collection_date else None,
    }
