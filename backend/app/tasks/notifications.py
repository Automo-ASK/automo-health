"""Notification delivery task."""

from app.core.celery_app import celery_app
from app.services.notifications import _deliver


@celery_app.task(name="app.tasks.notifications.fire_notification")
def fire_notification(event: str, payload: dict) -> None:
    _deliver(event, payload)
