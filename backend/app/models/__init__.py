"""ORM models. Importing this package registers every model on ``Base.metadata``
so that Alembic autogeneration and ``create_all`` can see them."""

from app.models.appointment import Appointment
from app.models.base import Base
from app.models.booking import Booking
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

__all__ = [
    "Base",
    "Patient",
    "Provider",
    "Service",
    "Slot",
    "Booking",
    "Appointment",
    "Payment",
    "SlotStatus",
    "BookingStatus",
    "AppointmentStatus",
    "PaymentStatus",
    "PaymentProvider",
]
