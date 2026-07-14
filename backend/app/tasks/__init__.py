"""Celery task modules. Imported so the worker registers the tasks."""

from app.tasks import bookings, notifications, payments, slots  # noqa: F401
