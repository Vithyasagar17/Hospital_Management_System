"""Celery integration for Medora HMS background processing.

The web application does not require a live broker to serve normal requests.
Workers call the same domain services used by the existing Flask CLI commands,
so reminder and waitlist behavior stays consistent across development and
containerized production workflows.
"""
from __future__ import annotations

import os
from typing import Any

from celery import Celery, Task


def _positive_int(name: str, default: int, *, minimum: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f'{name} must be an integer.') from exc
    return max(value, minimum)


def make_celery(app) -> Celery:
    """Create a Celery instance whose tasks execute inside a Flask app context."""

    class FlaskTask(Task):
        abstract = True

        def __call__(self, *args: Any, **kwargs: Any):
            with app.app_context():
                return self.run(*args, **kwargs)

    broker_url = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    result_backend = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1')
    reminder_interval = _positive_int('CELERY_REMINDER_INTERVAL_SECONDS', 300, minimum=60)
    waitlist_interval = _positive_int('CELERY_WAITLIST_INTERVAL_SECONDS', 60, minimum=15)

    celery = Celery(app.import_name, task_cls=FlaskTask)
    celery.conf.update(
        broker_url=broker_url,
        result_backend=result_backend,
        broker_connection_retry_on_startup=True,
        task_serializer='json',
        result_serializer='json',
        accept_content=['json'],
        result_expires=3600,
        task_track_started=True,
        worker_prefetch_multiplier=1,
        worker_hijack_root_logger=False,
        timezone=os.environ.get('HMS_TIMEZONE', 'Asia/Kolkata'),
        enable_utc=True,
        beat_schedule={
            'medora-appointment-reminders': {
                'task': 'medora.appointment_reminders',
                'schedule': reminder_interval,
            },
            'medora-waitlist-maintenance': {
                'task': 'medora.waitlist_maintenance',
                'schedule': waitlist_interval,
            },
        },
    )

    from app.background_tasks import register_background_tasks
    register_background_tasks(celery)
    app.extensions['celery'] = celery
    return celery
