from datetime import datetime, timedelta

from app import db
from app.models import (
    Appointment,
    Doctor,
    DoctorAvailability,
    Notification,
    Patient,
    User,
    WaitlistEntry,
)
from app.scheduling import available_slots_for_doctor
from app.waitlist import (
    claim_waitlist_offer,
    expire_waitlist_offers,
    is_waitlistable_day,
    offer_released_slot,
)
from tests.conftest import login


TARGET = datetime(2030, 2, 10, 10, 0, 0)


def _fully_booked_slot(app):
    with app.app_context():
        doctor = Doctor.query.first()
        patient = Patient.query.filter_by(name='Patient One').first()
        db.session.add(DoctorAvailability(
            doctor_id=doctor.id,
            date=TARGET.date(),
            start_time='10:00',
            end_time='10:30',
            is_available=True,
        ))
        appointment = Appointment(
            patient_id=patient.id,
            doctor_id=doctor.id,
            date=TARGET,
            time='10:00',
            reason='Booked slot',
            status='Confirmed',
        )
        db.session.add(appointment)
        db.session.commit()
        return doctor.id, patient.id, appointment.id


def test_fully_booked_published_day_can_be_waitlisted(client, app):
    doctor_id, _, _ = _fully_booked_slot(app)
    login(client, 'other', 'Other1234')

    response = client.post('/patient/waitlist/join', data={
        'doctor_id': doctor_id,
        'target_date': TARGET.date().isoformat(),
        'reason': 'Need the released slot',
    }, follow_redirects=False)
    assert response.status_code in (302, 303)

    # Rejoining the same active queue must not create a duplicate.
    client.post('/patient/waitlist/join', data={
        'doctor_id': doctor_id,
        'target_date': TARGET.date().isoformat(),
        'reason': 'Duplicate attempt',
    }, follow_redirects=False)

    with app.app_context():
        other = User.query.filter_by(username='other').first()
        entries = WaitlistEntry.query.filter_by(
            patient_id=other.id,
            doctor_id=doctor_id,
            target_date=TARGET.date(),
        ).all()
        assert len(entries) == 1
        assert entries[0].status == 'Waiting'
        assert is_waitlistable_day(doctor_id, TARGET.date()) is True


def test_patient_cancellation_offers_slot_and_temporarily_reserves_it(client, app):
    doctor_id, patient_id, appointment_id = _fully_booked_slot(app)
    with app.app_context():
        other = User.query.filter_by(username='other').first()
        db.session.add(WaitlistEntry(
            patient_id=other.id,
            doctor_id=doctor_id,
            target_date=TARGET.date(),
            reason='Waitlisted visit',
            status='Waiting',
        ))
        db.session.commit()

    login(client, 'patient', 'Patient1234')
    response = client.post(f'/patient/appointment/{appointment_id}/cancel', follow_redirects=False)
    assert response.status_code in (302, 303)

    with app.app_context():
        entry = WaitlistEntry.query.filter_by(doctor_id=doctor_id).first()
        assert entry.status == 'Offered'
        assert entry.offered_slot == TARGET
        assert entry.offer_expires_at is not None
        assert Notification.query.filter_by(user_id=entry.patient_id, title='Waitlist slot available').count() == 1

        # The 15-minute offer behaves like a temporary hold and disappears
        # from everybody else's normal booking choices.
        slots = available_slots_for_doctor(doctor_id, start_date=TARGET.date(), days=1)
        assert '10:00' not in slots.get(TARGET.date().isoformat(), [])


def test_waitlist_offer_can_be_claimed_as_pending_appointment(app):
    doctor_id, _, appointment_id = _fully_booked_slot(app)
    with app.app_context():
        other = User.query.filter_by(username='other').first()
        entry = WaitlistEntry(
            patient_id=other.id,
            doctor_id=doctor_id,
            target_date=TARGET.date(),
            reason='Claim me',
            status='Waiting',
        )
        db.session.add(entry)
        occupied = db.session.get(Appointment, appointment_id)
        occupied.status = 'Cancelled'
        db.session.flush()
        offer = offer_released_slot(doctor_id, TARGET)
        assert offer and offer.id == entry.id

        appointment, error = claim_waitlist_offer(entry)
        assert error is None
        assert appointment is not None
        assert appointment.status == 'Pending'
        assert appointment.date == TARGET
        assert entry.status == 'Booked'
        assert entry.booked_appointment_id == appointment.id
        db.session.commit()


def test_expired_offer_promotes_next_waiting_patient(app):
    doctor_id, _, appointment_id = _fully_booked_slot(app)
    with app.app_context():
        first_user = User.query.filter_by(username='other').first()
        third = User(username='third', email='third@example.com', email_verified=True, role='Patient')
        third.set_password('Third1234')
        db.session.add(third)
        db.session.flush()
        db.session.add(Patient(id=third.id, name='Patient Three'))
        first = WaitlistEntry(
            patient_id=first_user.id, doctor_id=doctor_id,
            target_date=TARGET.date(), reason='First', status='Waiting')
        second = WaitlistEntry(
            patient_id=third.id, doctor_id=doctor_id,
            target_date=TARGET.date(), reason='Second', status='Waiting')
        db.session.add_all([first, second])
        occupied = db.session.get(Appointment, appointment_id)
        occupied.status = 'Cancelled'
        db.session.flush()

        offered = offer_released_slot(doctor_id, TARGET)
        assert offered.id == first.id
        first.offer_expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()

        result = expire_waitlist_offers(now_utc=datetime.utcnow())
        db.session.commit()
        assert result['expired'] == 1
        assert result['promoted'] == 1
        assert db.session.get(WaitlistEntry, first.id).status == 'Expired'
        promoted = db.session.get(WaitlistEntry, second.id)
        assert promoted.status == 'Offered'
        assert promoted.offered_slot == TARGET
