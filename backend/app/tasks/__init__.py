"""Celery task modules. Imported so the worker registers the tasks."""

from app.tasks import bookings, notifications, slots  # noqa: F401
