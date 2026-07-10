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
