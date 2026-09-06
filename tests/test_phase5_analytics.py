from datetime import datetime, timedelta

from app import db
from app.analytics import build_scheduling_analytics
from app.models import (
    Appointment,
    AppointmentReminder,
    Doctor,
    DoctorAvailability,
    Patient,
    WaitlistEntry,
)
from tests.conftest import login


NOW = datetime(2030, 1, 10, 18, 0, 0)


def _seed_analytics_data(app):
    with app.app_context():
        AppointmentReminder.query.delete()
        WaitlistEntry.query.delete()
        Appointment.query.delete()
        DoctorAvailability.query.delete()
        db.session.commit()

        doctor = Doctor.query.first()
        patient_one = Patient.query.filter_by(name='Patient One').first()
        patient_two = Patient.query.filter_by(name='Patient Two').first()

        db.session.add(DoctorAvailability(
            doctor_id=doctor.id,
            date=NOW.date(),
            start_time='09:00',
            end_time='11:00',
            is_available=True,
        ))

        appointments = [
            Appointment(
                patient_id=patient_one.id, doctor_id=doctor.id,
                date=NOW.replace(hour=9, minute=0), time='09:00',
                reason='Completed rescheduled', status='Completed', reschedule_count=1,
            ),
            Appointment(
                patient_id=patient_two.id, doctor_id=doctor.id,
                date=NOW.replace(hour=9, minute=30), time='09:30',
                reason='No show', status='No Show',
            ),
            Appointment(
                patient_id=patient_one.id, doctor_id=doctor.id,
                date=NOW.replace(hour=10, minute=0), time='10:00',
                reason='Cancelled', status='Cancelled',
            ),
            Appointment(
                patient_id=patient_two.id, doctor_id=doctor.id,
                date=NOW.replace(hour=10, minute=30), time='10:30',
                reason='Completed unreminded', status='Completed',
            ),
        ]
        db.session.add_all(appointments)
        db.session.flush()

        db.session.add_all([
            AppointmentReminder(
                appointment_id=appointments[0].id,
                user_id=appointments[0].patient_id,
                reminder_type='24h',
                scheduled_for=appointments[0].date,
                sent_at=NOW - timedelta(days=1),
                email_sent=True,
            ),
            AppointmentReminder(
                appointment_id=appointments[1].id,
                user_id=appointments[1].patient_id,
                reminder_type='2h',
                scheduled_for=appointments[1].date,
                sent_at=NOW - timedelta(hours=2),
                email_sent=False,
            ),
            # Historical reminder from an older schedule snapshot. It must not
            # count as current coverage after a reschedule.
            AppointmentReminder(
                appointment_id=appointments[3].id,
                user_id=appointments[3].patient_id,
                reminder_type='24h',
                scheduled_for=appointments[3].date - timedelta(days=1),
                sent_at=NOW - timedelta(days=2),
                email_sent=False,
            ),
        ])

        db.session.add_all([
            WaitlistEntry(
                patient_id=patient_one.id, doctor_id=doctor.id,
                target_date=NOW.date(), reason='Booked waitlist', status='Booked',
            ),
            WaitlistEntry(
                patient_id=patient_two.id, doctor_id=doctor.id,
                target_date=NOW.date(), reason='Expired waitlist', status='Expired',
            ),
            WaitlistEntry(
                patient_id=patient_one.id, doctor_id=doctor.id,
                target_date=NOW.date(), reason='Waiting', status='Waiting',
            ),
        ])
        db.session.commit()
        return doctor.id


def test_scheduling_intelligence_rates_and_current_reminders(app):
    doctor_id = _seed_analytics_data(app)
    with app.app_context():
        analytics = build_scheduling_analytics(doctor_id=doctor_id, days=30, now=NOW)

        assert analytics['total_appointments'] == 4
        assert analytics['completion_rate'] == 66.7
        assert analytics['no_show_rate'] == 33.3
        assert analytics['cancellation_rate'] == 25.0
        assert analytics['reschedule_rate'] == 25.0
        assert analytics['patient_reminder_deliveries'] == 2
        assert analytics['reminder_24h_count'] == 1
        assert analytics['reminder_2h_count'] == 1
        assert analytics['reminder_email_sent'] == 1
        assert analytics['reminder_outcome_coverage'] == 66.7
        assert analytics['reminded_no_show_rate'] == 50.0
        assert analytics['unreminded_no_show_rate'] == 0.0
        assert analytics['busiest_hour'] == '9 AM'


def test_waitlist_conversion_and_published_slot_utilization(app):
    doctor_id = _seed_analytics_data(app)
    with app.app_context():
        analytics = build_scheduling_analytics(doctor_id=doctor_id, days=30, now=NOW)

        assert analytics['waitlist_total'] == 3
        assert analytics['waitlist_booked'] == 1
        assert analytics['waitlist_conversion_rate'] == 33.3
        assert analytics['utilization']['published_slots'] == 4
        assert analytics['utilization']['used_slots'] == 3
        assert analytics['utilization']['utilization_rate'] == 75.0
        assert analytics['utilization']['outside_published_capacity'] == 0


def test_admin_and_doctor_analytics_routes_are_role_scoped(client, app):
    _seed_analytics_data(app)

    login(client, 'admin', 'Admin1234')
    response = client.get('/admin/scheduling-analytics?days=30')
    assert response.status_code == 200
    assert b'Hospital scheduling performance' in response.data

    client.post('/logout', follow_redirects=False)
    login(client, 'doctor', 'Doctor1234')
    response = client.get('/doctor/scheduling-analytics?days=30')
    assert response.status_code == 200
    assert b'My scheduling performance' in response.data
