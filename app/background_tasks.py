"""Task definitions for the Phase 7C Celery worker."""
from __future__ import annotations

import os

from flask import current_app
from sqlalchemy.exc import OperationalError

from app import db
from app.reminders import process_appointment_reminders
from app.security import send_app_email
from app.waitlist import expire_waitlist_offers


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def register_background_tasks(celery):
    """Register idempotent HMS maintenance jobs on a Celery instance."""

    @celery.task(
        name='medora.appointment_reminders',
        autoretry_for=(OperationalError,),
        retry_backoff=True,
        retry_jitter=True,
        max_retries=3,
    )
    def appointment_reminders_task():
        # The reminder processor already has a database uniqueness guard, so
        # repeated Beat runs and safe task retries do not duplicate reminders.
        stats = process_appointment_reminders(
            include_doctors=_env_flag('HMS_BACKGROUND_REMIND_DOCTORS', False),
            send_email=_env_flag('HMS_BACKGROUND_SEND_REMINDER_EMAILS', False),
        )
        current_app.logger.info('background appointment reminders: %s', stats)
        return stats

    @celery.task(
        name='medora.waitlist_maintenance',
        autoretry_for=(OperationalError,),
        retry_backoff=True,
        retry_jitter=True,
        max_retries=3,
    )
    def waitlist_maintenance_task():
        try:
            result = expire_waitlist_offers()
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        current_app.logger.info('background waitlist maintenance: %s', result)
        return result

    @celery.task(
        name='medora.send_email',
        autoretry_for=(OperationalError,),
        retry_backoff=True,
        retry_jitter=True,
        max_retries=2,
    )
    def send_email_task(recipient: str, subject: str, body: str):
        """Generic email task for flows that are migrated to async delivery later."""
        sent = bool(send_app_email(recipient, subject, body))
        current_app.logger.info('background email delivery recipient=%s sent=%s', recipient, sent)
        return {'sent': sent}

    return {
        'appointment_reminders': appointment_reminders_task,
        'waitlist_maintenance': waitlist_maintenance_task,
        'send_email': send_email_task,
    }
