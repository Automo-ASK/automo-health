class DomainError(Exception):
    """Base class for domain/business-rule errors, mapped to HTTP in main.py."""

    status_code = 400

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class NotFoundError(DomainError):
    status_code = 404


class ConflictError(DomainError):
    status_code = 409


class SlotUnavailableError(ConflictError):
    """Raised when a slot cannot be held/booked (already held or booked)."""


class PaymentError(DomainError):
    status_code = 502
