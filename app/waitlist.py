"""Phase 5C waitlist and released-slot offer workflow."""
from datetime import datetime, timedelta, time

from app import db
from app.activity import log_activity, notify_user
from app.models import Appointment, DoctorAvailability, Patient, WaitlistEntry
from app.scheduling import (
    has_active_doctor_conflict,
    has_active_patient_conflict,
    is_valid_booking_slot,
)

WAITLIST_OFFER_MINUTES = 15
ACTIVE_WAITLIST_STATUSES = ('Waiting', 'Offered')


def is_waitlistable_day(doctor_id, target_date):
    """True when the doctor published hours for the day but no free slots remain."""
    published = DoctorAvailability.query.filter(
        DoctorAvailability.doctor_id == doctor_id,
        DoctorAvailability.date == target_date,
        DoctorAvailability.is_available.is_(True),
    ).first() is not None
    if not published:
        return False

    from app.scheduling import available_slots_for_doctor
    free_slots = available_slots_for_doctor(doctor_id, start_date=target_date, days=1).get(target_date.isoformat(), [])
    if free_slots:
        return False

    day_start = datetime.combine(target_date, time.min)
    day_end = day_start + timedelta(days=1)
    active_count = Appointment.query.filter(
        Appointment.doctor_id == doctor_id,
        Appointment.status.in_(('Pending', 'Confirmed')),
        Appointment.date >= day_start,
        Appointment.date < day_end,
    ).count()
    active_holds = WaitlistEntry.query.filter(
        WaitlistEntry.doctor_id == doctor_id,
        WaitlistEntry.status == 'Offered',
        WaitlistEntry.offered_slot >= day_start,
        WaitlistEntry.offered_slot < day_end,
        WaitlistEntry.offer_expires_at > datetime.utcnow(),
    ).count()
    return (active_count + active_holds) > 0


def active_waitlist_entry(patient_id, doctor_id, target_date):
    return WaitlistEntry.query.filter(
        WaitlistEntry.patient_id == patient_id,
        WaitlistEntry.doctor_id == doctor_id,
        WaitlistEntry.target_date == target_date,
        WaitlistEntry.status.in_(ACTIVE_WAITLIST_STATUSES),
    ).order_by(WaitlistEntry.created_at.asc(), WaitlistEntry.id.asc()).first()


def offer_released_slot(doctor_id, released_slot, *, now=None, offer_minutes=WAITLIST_OFFER_MINUTES):
    """Offer a newly free slot to the oldest eligible waiting patient.

    The function does not commit. It is designed to participate in the same
    transaction as the cancellation/reschedule that released the slot.
    """
    now = now or datetime.now()
    if not released_slot or released_slot <= now:
        return None

    # The appointment that occupied this slot must already be cancelled or
    # moved before this helper is called. SQLAlchemy autoflush makes that
    # state visible to these conflict checks.
    if not is_valid_booking_slot(doctor_id, released_slot):
        return None
    if has_active_doctor_conflict(doctor_id, released_slot):
        return None

    candidates = WaitlistEntry.query.filter_by(
        doctor_id=doctor_id,
        target_date=released_slot.date(),
        status='Waiting',
    ).order_by(WaitlistEntry.created_at.asc(), WaitlistEntry.id.asc()).all()

    for entry in candidates:
        patient = db.session.get(Patient, entry.patient_id)
        if not patient or patient.is_blacklisted:
            entry.status = 'Cancelled'
            entry.updated_at = datetime.utcnow()
            continue
        if has_active_patient_conflict(entry.patient_id, released_slot):
            # Keep the patient in the queue for a different slot that day.
            continue

        entry.status = 'Offered'
        entry.offered_slot = released_slot
        entry.offered_at = datetime.utcnow()
        entry.offer_expires_at = datetime.utcnow() + timedelta(minutes=offer_minutes)
        entry.updated_at = datetime.utcnow()
        notify_user(
            entry.patient_id,
            'Waitlist slot available',
            f'A slot with Dr. {entry.doctor.name if entry.doctor else "Doctor"} opened on '
            f'{released_slot.strftime("%d %b %Y at %I:%M %p")}. Claim it within {offer_minutes} minutes.',
            'success',
            f'/patient/waitlist/{entry.id}',
        )
        log_activity(
            'waitlist_slot_offered',
            f'Waitlist #{entry.id} offered {released_slot.strftime("%d %b %Y %I:%M %p")}.',
            'WaitlistEntry',
            entry.id,
        )
        return entry

    return None


def expire_waitlist_offers(*, now_utc=None):
    """Expire timed-out offers and promote each still-free slot to the next patient."""
    now_utc = now_utc or datetime.utcnow()
    expired = WaitlistEntry.query.filter(
        WaitlistEntry.status == 'Offered',
        WaitlistEntry.offer_expires_at.isnot(None),
        WaitlistEntry.offer_expires_at <= now_utc,
    ).order_by(WaitlistEntry.offer_expires_at.asc()).all()

    promoted = 0
    for entry in expired:
        slot = entry.offered_slot
        doctor_id = entry.doctor_id
        entry.status = 'Expired'
        entry.updated_at = now_utc
        notify_user(
            entry.patient_id,
            'Waitlist offer expired',
            'Your temporary waitlist slot offer expired. You can join the waitlist again if you still need this date.',
            'warning',
            '/patient/waitlist',
        )
        log_activity('waitlist_offer_expired', f'Waitlist offer #{entry.id} expired.', 'WaitlistEntry', entry.id)
        db.session.flush()
        if slot and offer_released_slot(doctor_id, slot, now=datetime.now()):
            promoted += 1

    return {'expired': len(expired), 'promoted': promoted}


def claim_waitlist_offer(entry, *, now_utc=None, now_local=None):
    """Convert a valid offer into a Pending appointment. Caller commits."""
    now_utc = now_utc or datetime.utcnow()
    now_local = now_local or datetime.now()

    if entry.status != 'Offered' or not entry.offered_slot:
        return None, 'This waitlist offer is no longer active.'
    if not entry.offer_expires_at or entry.offer_expires_at <= now_utc:
        entry.status = 'Expired'
        entry.updated_at = now_utc
        db.session.flush()
        offer_released_slot(entry.doctor_id, entry.offered_slot, now=now_local)
        return None, 'This waitlist offer has expired.'
    if entry.offered_slot <= now_local:
        entry.status = 'Expired'
        entry.updated_at = now_utc
        return None, 'This appointment time has already passed.'
    if not is_valid_booking_slot(entry.doctor_id, entry.offered_slot, exclude_waitlist_entry_id=entry.id):
        entry.status = 'Expired'
        entry.updated_at = now_utc
        return None, 'That slot is no longer available.'
    if has_active_doctor_conflict(entry.doctor_id, entry.offered_slot):
        entry.status = 'Expired'
        entry.updated_at = now_utc
        return None, 'That slot was taken before the offer could be claimed.'
    if has_active_patient_conflict(entry.patient_id, entry.offered_slot):
        return None, 'You already have another active appointment at that time.'

    appointment = Appointment(
        patient_id=entry.patient_id,
        doctor_id=entry.doctor_id,
        date=entry.offered_slot,
        time=entry.offered_slot.strftime('%H:%M'),
        reason=entry.reason,
        status='Pending',
    )
    db.session.add(appointment)
    db.session.flush()

    entry.status = 'Booked'
    entry.booked_appointment_id = appointment.id
    entry.updated_at = now_utc

    patient_name = entry.patient.name if entry.patient and entry.patient.name else 'Patient'
    notify_user(
        entry.doctor_id,
        'Waitlist slot claimed',
        f'{patient_name} claimed the released slot on {entry.offered_slot.strftime("%d %b %Y at %I:%M %p")}.',
        'info',
        f'/doctor/appointment/{appointment.id}',
    )
    log_activity(
        'waitlist_offer_claimed',
        f'Waitlist #{entry.id} converted to appointment #{appointment.id}.',
        'Appointment',
        appointment.id,
    )
    return appointment, None


def register_waitlist_commands(app):
    """Register CLI maintenance for expiring/promoting waitlist offers."""
    import click

    @app.cli.command('process-waitlist-offers')
    def process_waitlist_offers_command():
        result = expire_waitlist_offers()
        db.session.commit()
        click.echo(
            f"Waitlist run complete: {result['expired']} expired, "
            f"{result['promoted']} promoted."
        )
