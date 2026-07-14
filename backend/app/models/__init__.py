"""ORM models. Importing this package registers every model on ``Base.metadata``
so that Alembic autogeneration and ``create_all`` can see them."""

from app.models.appointment import Appointment
from app.models.base import Base
from app.models.booking import Booking
from app.models.conversation import Conversation
from app.models.enums import (
    AppointmentStatus,
    BookingStatus,
    LabOrderStatus,
    NotificationEvent,
    PaymentProvider,
    PaymentStatus,
    SlotStatus,
    VirtualAccountStatus,
)
from app.models.lab_order import LabOrder
from app.models.patient import Patient
from app.models.payment import Payment
from app.models.provider import Provider
from app.models.service import Service
from app.models.slot import Slot
from app.models.virtual_account import VirtualAccount

__all__ = [
    "Base",
    "Patient",
    "Provider",
    "Service",
    "Slot",
    "Booking",
    "Appointment",
    "Payment",
    "VirtualAccount",
    "LabOrder",
    "SlotStatus",
    "BookingStatus",
    "AppointmentStatus",
    "PaymentStatus",
    "PaymentProvider",
    "VirtualAccountStatus",
    "LabOrderStatus",
    "NotificationEvent",
]
