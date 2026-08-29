from datetime import datetime, timedelta, time

from app.models import Appointment, DoctorAvailability

SLOT_MINUTES = 30


def _parse_time(value):
    return datetime.strptime(value, '%H:%M').time()


def _minutes(value):
    return value.hour * 60 + value.minute


def _slot_times(start_time, end_time):
    """Return 30-minute slot start times fully contained in a window."""
    start = datetime.combine(datetime.today(), _parse_time(start_time))
    end = datetime.combine(datetime.today(), _parse_time(end_time))
    step = timedelta(minutes=SLOT_MINUTES)
    slots = []
    while start + step <= end:
        slots.append(start.strftime('%H:%M'))
        start += step
    return slots


def available_slots_for_doctor(doctor_id, start_date=None, days=8):
    """Build free booking slots from the doctor's availability windows.

    Available windows create slots. Unavailable windows remove overlapping slots.
    Existing non-cancelled appointments remove their slot as well.
    """
    start_date = start_date or datetime.now().date()
    end_date = start_date + timedelta(days=days - 1)

    windows = DoctorAvailability.query.filter(
        DoctorAvailability.doctor_id == doctor_id,
        DoctorAvailability.date >= start_date,
        DoctorAvailability.date <= end_date,
    ).order_by(DoctorAvailability.date, DoctorAvailability.start_time).all()

    appointments = Appointment.query.filter(
        Appointment.doctor_id == doctor_id,
        Appointment.date >= datetime.combine(start_date, time.min),
        Appointment.date < datetime.combine(end_date + timedelta(days=1), time.min),
        Appointment.status != 'Cancelled',
    ).all()

    booked = {}
    for appointment in appointments:
        if appointment.date:
            key = appointment.date.date().isoformat()
            booked.setdefault(key, set()).add(appointment.date.strftime('%H:%M'))

    by_date = {}
    for window in windows:
        key = window.date.isoformat()
        entry = by_date.setdefault(key, {'available': [], 'blocked': []})
        target = 'available' if window.is_available else 'blocked'
        entry[target].append((window.start_time, window.end_time))

    now = datetime.now()
    result = {}
    for key, entry in by_date.items():
        date_obj = datetime.strptime(key, '%Y-%m-%d').date()
        free = set()
        for start_time, end_time in entry['available']:
            free.update(_slot_times(start_time, end_time))

        for blocked_start, blocked_end in entry['blocked']:
            b_start = _minutes(_parse_time(blocked_start))
            b_end = _minutes(_parse_time(blocked_end))
            free = {
                slot for slot in free
                if not (
                    _minutes(_parse_time(slot)) < b_end and
                    _minutes(_parse_time(slot)) + SLOT_MINUTES > b_start
                )
            }

        free -= booked.get(key, set())

        if date_obj == now.date():
            free = {
                slot for slot in free
                if datetime.combine(date_obj, _parse_time(slot)) > now
            }

        if free:
            result[key] = sorted(free)

    return result


def is_valid_booking_slot(doctor_id, appointment_dt):
    slots = available_slots_for_doctor(doctor_id, start_date=appointment_dt.date(), days=1)
    return appointment_dt.strftime('%H:%M') in slots.get(appointment_dt.date().isoformat(), [])
