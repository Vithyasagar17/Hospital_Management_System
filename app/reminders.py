"""Phase 5B appointment reminder processing.

The processor is intentionally framework-light so it can be called from a
manual CLI command today and from a scheduler/background worker later. A
logical reminder is unique per appointment schedule snapshot, recipient, and
reminder window, which makes repeated runs idempotent and safe after
rescheduling.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import click
from flask import current_app
from sqlalchemy.exc import IntegrityError

from app import db
from app.activity import notify_user
from app.models import Appointment, AppointmentReminder, User
from app.security import send_app_email

REMINDER_24H = '24h'
REMINDER_2H = '2h'


def _utc_now_naive() -> datetime:
    """Return a UTC timestamp compatible with the project's naive SQLite columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _reminder_type_for(remaining: timedelta) -> str | None:
    """Return the single reminder window that owns the remaining duration."""
    if remaining <= timedelta(0):
        return None
    if remaining <= timedelta(hours=2):
        return REMINDER_2H
    if remaining <= timedelta(hours=24):
        return REMINDER_24H
    return None


def _label(reminder_type: str) -> str:
    return '2-hour' if reminder_type == REMINDER_2H else '24-hour'


def _target_url(role: str, appointment_id: int) -> str:
    if role == 'Doctor':
        return f'/doctor/appointment/{appointment_id}'
    return f'/patient/appointment/{appointment_id}'


def _message_for(appointment: Appointment, user: User, reminder_type: str) -> tuple[str, str]:
    schedule = appointment.date.strftime('%d %b %Y at %I:%M %p')
    patient_name = appointment.patient.name if appointment.patient and appointment.patient.name else 'Patient'
    doctor_name = appointment.doctor.name if appointment.doctor and appointment.doctor.name else 'Doctor'
    lead = _label(reminder_type)

    if user.role == 'Doctor':
        title = f'{lead} appointment reminder'
        message = f'{patient_name} is scheduled with you on {schedule}.'
    else:
        title = f'{lead} appointment reminder'
        message = f'Your appointment with Dr. {doctor_name} is scheduled for {schedule}.'
    return title, message


def _email_body(appointment: Appointment, user: User, reminder_type: str) -> tuple[str, str]:
    title, message = _message_for(appointment, user, reminder_type)
    subject = f'Medora HMS — {title}'
    body = (
        f'Hello {user.username},\n\n'
        f'{message}\n\n'
        'Sign in to Medora HMS to view the appointment details or manage the visit.\n\n'
        'This is an automated appointment reminder.'
    )
    return subject, body


def _current_recipients(appointment: Appointment, include_doctors: bool) -> list[User]:
    recipients = []
    patient_user = db.session.get(User, appointment.patient_id)
    if patient_user:
        recipients.append(patient_user)
    if include_doctors:
        doctor_user = db.session.get(User, appointment.doctor_id)
        if doctor_user:
            recipients.append(doctor_user)
    return recipients


def process_appointment_reminders(
    *,
    now: datetime | None = None,
    include_doctors: bool = False,
    send_email: bool = False,
) -> dict[str, int]:
    """Create due reminders for confirmed future appointments.

    Appointment ``date`` values are hospital-local naive datetimes in the
    current project, so ``now`` is intentionally local/naive as well.

    Reminder windows are mutually exclusive:
    - >2h and <=24h: 24-hour reminder
    - >0 and <=2h: 2-hour reminder

    The reminder row stores the appointment's schedule snapshot. If an
    appointment is later rescheduled, the same reminder type may be sent for
    the new schedule while the old delivery remains in the audit history.
    """
    now = now or datetime.now()
    horizon = now + timedelta(hours=24)

    appointments = Appointment.query.filter(
        Appointment.status == 'Confirmed',
        Appointment.date > now,
        Appointment.date <= horizon,
    ).order_by(Appointment.date.asc()).all()

    stats = {
        'appointments_checked': len(appointments),
        'sent': 0,
        'duplicates_skipped': 0,
        'emails_attempted': 0,
        'emails_sent': 0,
    }

    for appointment in appointments:
        reminder_type = _reminder_type_for(appointment.date - now)
        if not reminder_type:
            continue

        for user in _current_recipients(appointment, include_doctors):
            exists = AppointmentReminder.query.filter_by(
                appointment_id=appointment.id,
                user_id=user.id,
                reminder_type=reminder_type,
                scheduled_for=appointment.date,
            ).first()
            if exists:
                stats['duplicates_skipped'] += 1
                continue

            title, message = _message_for(appointment, user, reminder_type)
            reminder = AppointmentReminder(
                appointment_id=appointment.id,
                user_id=user.id,
                reminder_type=reminder_type,
                scheduled_for=appointment.date,
                sent_at=_utc_now_naive(),
            )
            db.session.add(reminder)
            notify_user(
                user.id,
                title,
                message,
                'warning' if reminder_type == REMINDER_2H else 'info',
                _target_url(user.role, appointment.id),
            )

            # Commit the logical reminder and in-app notification together.
            # The unique constraint is the final concurrency guard if two
            # reminder workers race on the same appointment.
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                stats['duplicates_skipped'] += 1
                continue

            stats['sent'] += 1

            if send_email and user.email and user.email_verified:
                stats['emails_attempted'] += 1
                subject, body = _email_body(appointment, user, reminder_type)
                reminder.email_attempted_at = _utc_now_naive()
                reminder.email_sent = bool(send_app_email(user.email, subject, body))
                if reminder.email_sent:
                    stats['emails_sent'] += 1
                db.session.commit()

    return stats


def register_reminder_commands(app):
    """Attach Phase 5B CLI commands to a Flask app instance."""

    @app.cli.command('send-appointment-reminders')
    @click.option(
        '--include-doctors/--patients-only',
        default=False,
        help='Also create reminder notifications for doctors.',
    )
    @click.option(
        '--email/--no-email',
        default=False,
        help='Attempt email delivery for verified recipients. Console mode stays simulated.',
    )
    def send_appointment_reminders(include_doctors: bool, email: bool):
        """Process due 24-hour and 2-hour appointment reminders."""
        with app.app_context():
            stats = process_appointment_reminders(
                include_doctors=include_doctors,
                send_email=email,
            )
        click.echo(
            'Reminder run complete: '
            f"{stats['sent']} sent, "
            f"{stats['duplicates_skipped']} duplicates skipped, "
            f"{stats['emails_sent']}/{stats['emails_attempted']} emails sent."
        )
