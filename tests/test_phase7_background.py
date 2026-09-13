from datetime import datetime, timedelta

from app import db
from app.background import make_celery
from app.models import Appointment, AppointmentReminder
import app.background_tasks as background_tasks


def _eager_celery(app, monkeypatch):
    monkeypatch.setenv('CELERY_BROKER_URL', 'memory://')
    monkeypatch.setenv('CELERY_RESULT_BACKEND', 'cache+memory://')
    monkeypatch.setenv('CELERY_REMINDER_INTERVAL_SECONDS', '300')
    monkeypatch.setenv('CELERY_WAITLIST_INTERVAL_SECONDS', '60')
    celery = make_celery(app)
    celery.conf.update(task_always_eager=True, task_eager_propagates=True)
    return celery


def test_celery_registers_periodic_jobs(app, monkeypatch):
    celery = _eager_celery(app, monkeypatch)

    reminder_job = celery.conf.beat_schedule['medora-appointment-reminders']
    waitlist_job = celery.conf.beat_schedule['medora-waitlist-maintenance']

    assert reminder_job['task'] == 'medora.appointment_reminders'
    assert reminder_job['schedule'] == 300
    assert waitlist_job['task'] == 'medora.waitlist_maintenance'
    assert waitlist_job['schedule'] == 60
    assert 'medora.send_email' in celery.tasks


def test_reminder_task_runs_inside_flask_context(app, monkeypatch):
    monkeypatch.setenv('HMS_BACKGROUND_REMIND_DOCTORS', '0')
    monkeypatch.setenv('HMS_BACKGROUND_SEND_REMINDER_EMAILS', '0')
    celery = _eager_celery(app, monkeypatch)

    with app.app_context():
        appointment = Appointment.query.first()
        appointment.date = datetime.now() + timedelta(hours=1)
        appointment.time = appointment.date.strftime('%H:%M')
        appointment.status = 'Confirmed'
        appointment_id = appointment.id
        db.session.commit()

    result = celery.tasks['medora.appointment_reminders'].apply().get()

    with app.app_context():
        assert result['sent'] == 1
        assert AppointmentReminder.query.filter_by(appointment_id=appointment_id).count() == 1


def test_waitlist_task_commits_domain_result(app, monkeypatch):
    monkeypatch.setattr(
        background_tasks,
        'expire_waitlist_offers',
        lambda: {'expired': 2, 'promoted': 1},
    )
    celery = _eager_celery(app, monkeypatch)
    result = celery.tasks['medora.waitlist_maintenance'].apply().get()
    assert result == {'expired': 2, 'promoted': 1}


def test_generic_email_task_uses_existing_mailer(app, monkeypatch):
    monkeypatch.setattr(background_tasks, 'send_app_email', lambda recipient, subject, body: True)
    celery = _eager_celery(app, monkeypatch)
    result = celery.tasks['medora.send_email'].apply(
        args=('patient@example.com', 'Subject', 'Body')
    ).get()
    assert result == {'sent': True}
