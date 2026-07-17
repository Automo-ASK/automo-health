import enum


class ChannelType(str, enum.Enum):
    WHATSAPP = "whatsapp"
    SMS = "sms"
    USSD = "ussd"


class Language(str, enum.Enum):
    EN = "en"
    PIDGIN = "pidgin"
    YO = "yo"


class Intent(str, enum.Enum):
    BOOK = "book"
    RESCHEDULE = "reschedule"
    CANCEL = "cancel"
    QUERY = "query"
    UNKNOWN = "unknown"


class SuggestedAction(str, enum.Enum):
    SHOW_SERVICES = "show_services"
    SHOW_SLOTS = "show_slots"
    CONFIRM_BOOKING = "confirm_booking"
    AWAITING_PAYMENT = "awaiting_payment"
    RESCHEDULE = "reschedule"
    CANCEL_BOOKING = "cancel_booking"
    HUMAN_HANDOFF = "human_handoff"


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
    ADMITTED = "admitted"      # closed as admitted / sent for a procedure (dashboard)
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
    CASH = "cash"          # collected at the desk by a cashier (Day 6)


class LabOrderStatus(str, enum.Enum):
    """Lifecycle of a lab test ordered off the back of an appointment."""

    ORDERED = "ordered"        # requested by the clinician
    COLLECTED = "collected"    # sample taken
    RESULTED = "resulted"      # result entered
    CANCELLED = "cancelled"


class EmergencyStatus(str, enum.Enum):
    """Lifecycle of an emergency alert raised over a channel (PRD §8.6)."""

    OPEN = "open"                  # awaiting the doctor's attention
    ACKNOWLEDGED = "acknowledged"  # seen / handled (seated, or handled outside)


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
    APPOINTMENT_COMPLETED = "appointment.completed"
    APPOINTMENT_CANCELLED = "appointment.cancelled"
    APPOINTMENT_RESCHEDULED = "appointment.rescheduled"
    APPOINTMENT_NO_SHOW = "appointment.no_show"
    APPOINTMENT_FOLLOW_UP = "appointment.follow_up"
    PAYMENT_SUCCEEDED = "payment.succeeded"
    PAYMENT_MISMATCH = "payment.mismatch"
    PAYMENT_OVERPAID = "payment.overpaid"
    LAB_ORDERED = "lab.ordered"
    LAB_RESULTED = "lab.resulted"
