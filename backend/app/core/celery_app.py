from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "automo_health",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # Fail fast when the broker is unreachable instead of retrying for minutes, so
    # callers (e.g. notification dispatch) can fall back to inline delivery quickly.
    broker_connection_retry_on_startup=False,
    broker_connection_max_retries=0,
    broker_transport_options={"socket_connect_timeout": 2, "socket_timeout": 2},
    task_publish_retry=False,
)

# Day 2: periodic sweep that releases expired slot holds and expires unpaid
# bookings. Wired here so the beat schedule is ready; tasks land with the engine.
celery_app.conf.beat_schedule = {
    "release-expired-slot-holds": {
        "task": "app.tasks.slots.release_expired_holds",
        "schedule": 30.0,  # seconds
    },
    "expire-unpaid-bookings": {
        "task": "app.tasks.bookings.expire_unpaid_bookings",
        "schedule": 60.0,
    },
}

# Ensure task modules are imported when the worker boots (Day 2).
celery_app.autodiscover_tasks(["app.tasks"])
