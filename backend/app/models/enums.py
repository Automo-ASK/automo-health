import enum


class SlotStatus(str, enum.Enum):
    """Lifecycle of a bookable slot."""

    OPEN = "open"          # available to be held/booked
    HELD = "held"          # temporarily reserved, pending payment (has hold_expires_at)
    BOOKED = "booked"      # confirmed against a paid booking
    BLOCKED = "blocked"    # unavailable (provider time-off, etc.)


class BookingStatus(str, enum.Enum):
    """Lifecycle of a booking."""

    PENDING_PAYMENT = "pending_payment"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class AppointmentStatus(str, enum.Enum):
    """Lifecycle of a confirmed appointment."""

    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class PaymentStatus(str, enum.Enum):
    """Lifecycle of a payment against a booking."""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    ABANDONED = "abandoned"
    REFUNDED = "refunded"


class PaymentProvider(str, enum.Enum):
    PAYSTACK = "paystack"
    SQUAD = "squad"


class VirtualAccountStatus(str, enum.Enum):
    """Lifecycle of a per-booking dedicated virtual account."""

    ACTIVE = "active"
    CLOSED = "closed"


class NotificationEvent(str, enum.Enum):
    """Domain events that fire notification hooks."""

    BOOKING_CREATED = "booking.created"
    BOOKING_CONFIRMED = "booking.confirmed"
    BOOKING_EXPIRED = "booking.expired"
    APPOINTMENT_SCHEDULED = "appointment.scheduled"
    PAYMENT_SUCCEEDED = "payment.succeeded"
    PAYMENT_MISMATCH = "payment.mismatch"
