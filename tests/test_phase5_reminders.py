from datetime import datetime, timedelta

from app import db
from app.models import Appointment, AppointmentReminder, Notification, User
from app.reminders import process_appointment_reminders


def _set_fixture_appointment(app, base, delta, status='Confirmed'):
    with app.app_context():
        appointment = Appointment.query.first()
        appointment.date = base + delta
        appointment.time = appointment.date.strftime('%H:%M')
        appointment.status = status
        db.session.commit()
        return appointment.id


def test_24h_reminder_is_idempotent(app):
    base = datetime(2030, 1, 10, 9, 0, 0)
    appointment_id = _set_fixture_appointment(app, base, timedelta(hours=10))

    with app.app_context():
        first = process_appointment_reminders(now=base, send_email=False)
        second = process_appointment_reminders(now=base, send_email=False)

        rows = AppointmentReminder.query.filter_by(appointment_id=appointment_id).all()
        assert first['sent'] == 1
        assert second['sent'] == 0
        assert second['duplicates_skipped'] == 1
        assert len(rows) == 1
        assert rows[0].reminder_type == '24h'
        assert Notification.query.filter_by(user_id=rows[0].user_id).count() == 1


def test_two_hour_window_does_not_also_send_24h(app):
    base = datetime(2030, 1, 10, 9, 0, 0)
    appointment_id = _set_fixture_appointment(app, base, timedelta(hours=1))

    with app.app_context():
        stats = process_appointment_reminders(now=base, send_email=False)
        rows = AppointmentReminder.query.filter_by(appointment_id=appointment_id).all()
        assert stats['sent'] == 1
        assert [r.reminder_type for r in rows] == ['2h']


def test_rescheduled_schedule_can_receive_same_reminder_type_again(app):
    base = datetime(2030, 1, 10, 9, 0, 0)
    appointment_id = _set_fixture_appointment(app, base, timedelta(hours=10))

    with app.app_context():
        process_appointment_reminders(now=base, send_email=False)
        appointment = db.session.get(Appointment, appointment_id)
        appointment.date = base + timedelta(hours=12)
        appointment.time = appointment.date.strftime('%H:%M')
        db.session.commit()

        second = process_appointment_reminders(now=base, send_email=False)
        rows = AppointmentReminder.query.filter_by(
            appointment_id=appointment_id,
            reminder_type='24h',
        ).order_by(AppointmentReminder.id.asc()).all()

        assert second['sent'] == 1
        assert len(rows) == 2
        assert rows[0].scheduled_for != rows[1].scheduled_for


def test_non_confirmed_appointments_are_not_reminded(app):
    base = datetime(2030, 1, 10, 9, 0, 0)
    appointment_id = _set_fixture_appointment(app, base, timedelta(hours=10), status='Pending')

    with app.app_context():
        stats = process_appointment_reminders(now=base, send_email=False)
        assert stats['sent'] == 0
        assert AppointmentReminder.query.filter_by(appointment_id=appointment_id).count() == 0


def test_doctor_reminders_are_optional(app):
    base = datetime(2030, 1, 10, 9, 0, 0)
    appointment_id = _set_fixture_appointment(app, base, timedelta(hours=10))

    with app.app_context():
        appointment = db.session.get(Appointment, appointment_id)
        doctor_user = db.session.get(User, appointment.doctor_id)

        stats = process_appointment_reminders(
            now=base,
            include_doctors=True,
            send_email=False,
        )

        assert stats['sent'] == 2
        assert AppointmentReminder.query.filter_by(
            appointment_id=appointment_id,
            user_id=doctor_user.id,
            reminder_type='24h',
        ).count() == 1


def test_24h_then_2h_reminders_both_send_over_time(app):
    base = datetime(2030, 1, 10, 9, 0, 0)
    appointment_id = _set_fixture_appointment(app, base, timedelta(hours=10))

    with app.app_context():
        first = process_appointment_reminders(now=base, send_email=False)
        appointment = db.session.get(Appointment, appointment_id)
        second_now = appointment.date - timedelta(hours=1)
        second = process_appointment_reminders(now=second_now, send_email=False)

        rows = AppointmentReminder.query.filter_by(appointment_id=appointment_id).all()
        assert first['sent'] == 1
        assert second['sent'] == 1
        assert {r.reminder_type for r in rows} == {'24h', '2h'}
