"""Phase 5D scheduling intelligence.

Analytics are intentionally read-only and derived from existing scheduling,
reminder, and waitlist records. No new database schema is required.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, time

from app.models import (
    Appointment,
    AppointmentReminder,
    Doctor,
    DoctorAvailability,
    WaitlistEntry,
)

ANALYTICS_WINDOWS = {7, 30, 90, 365}
DEFAULT_ANALYTICS_WINDOW = 30
SLOT_MINUTES = 30


def normalize_window(value, default=DEFAULT_ANALYTICS_WINDOW):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return value if value in ANALYTICS_WINDOWS else default


def _pct(numerator, denominator):
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, 1)


def _period(days, now):
    end_date = now.date()
    start_date = end_date - timedelta(days=days - 1)
    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date + timedelta(days=1), time.min)
    return start_date, end_date, start_dt, end_dt


def _parse_hhmm(value):
    return datetime.strptime(value, '%H:%M').time()


def _minutes(value):
    return value.hour * 60 + value.minute


def _slot_times(start_time, end_time):
    start = datetime.combine(datetime.today(), _parse_hhmm(start_time))
    end = datetime.combine(datetime.today(), _parse_hhmm(end_time))
    step = timedelta(minutes=SLOT_MINUTES)
    slots = []
    while start + step <= end:
        slots.append(start.strftime('%H:%M'))
        start += step
    return slots


def _published_capacity(doctor_id, start_date, end_date):
    """Return unique published 30-minute slots after blocked windows are removed."""
    windows = DoctorAvailability.query.filter(
        DoctorAvailability.doctor_id == doctor_id,
        DoctorAvailability.date >= start_date,
        DoctorAvailability.date <= end_date,
    ).all()

    by_day = defaultdict(lambda: {'available': [], 'blocked': []})
    for window in windows:
        bucket = 'available' if window.is_available else 'blocked'
        by_day[window.date][bucket].append((window.start_time, window.end_time))

    total = 0
    slots_by_day = {}
    for day, windows_for_day in by_day.items():
        slots = set()
        for start_time, end_time in windows_for_day['available']:
            slots.update(_slot_times(start_time, end_time))
        for blocked_start, blocked_end in windows_for_day['blocked']:
            b_start = _minutes(_parse_hhmm(blocked_start))
            b_end = _minutes(_parse_hhmm(blocked_end))
            slots = {
                slot for slot in slots
                if not (
                    _minutes(_parse_hhmm(slot)) < b_end
                    and _minutes(_parse_hhmm(slot)) + SLOT_MINUTES > b_start
                )
            }
        slots_by_day[day] = slots
        total += len(slots)
    return total, slots_by_day


def _doctor_utilization(doctor_id, appointments, start_date, end_date):
    capacity, slots_by_day = _published_capacity(doctor_id, start_date, end_date)
    used_keys = set()
    outside_capacity = 0
    for appointment in appointments:
        if appointment.doctor_id != doctor_id or appointment.status == 'Cancelled' or not appointment.date:
            continue
        key = (appointment.date.date(), appointment.date.strftime('%H:%M'))
        if key in used_keys:
            continue
        used_keys.add(key)
        if key[1] not in slots_by_day.get(key[0], set()):
            outside_capacity += 1

    used = len(used_keys)
    observed_capacity = max(capacity, used)
    return {
        'published_slots': capacity,
        'used_slots': used,
        'utilization_rate': _pct(used, observed_capacity),
        'outside_published_capacity': outside_capacity,
    }


def build_scheduling_analytics(*, doctor_id=None, days=DEFAULT_ANALYTICS_WINDOW, now=None):
    """Build scheduling KPIs for an admin view or one doctor's panel.

    Appointment volume is grouped by scheduled date. Reminder comparisons only
    count patient reminders for the appointment's *current* schedule snapshot,
    so an old reminder sent before a reschedule does not inflate coverage.
    """
    now = now or datetime.now()
    days = normalize_window(days)
    start_date, end_date, start_dt, end_dt = _period(days, now)

    appointment_query = Appointment.query.filter(
        Appointment.date >= start_dt,
        Appointment.date < end_dt,
    )
    if doctor_id is not None:
        appointment_query = appointment_query.filter(Appointment.doctor_id == doctor_id)
    appointments = appointment_query.order_by(Appointment.date.asc()).all()

    appointment_ids = [a.id for a in appointments]
    reminders = []
    if appointment_ids:
        reminders = AppointmentReminder.query.filter(
            AppointmentReminder.appointment_id.in_(appointment_ids)
        ).all()

    appointment_by_id = {a.id: a for a in appointments}
    current_patient_reminders = []
    for reminder in reminders:
        appointment = appointment_by_id.get(reminder.appointment_id)
        if not appointment:
            continue
        if reminder.user_id != appointment.patient_id:
            continue
        if reminder.scheduled_for != appointment.date:
            continue
        current_patient_reminders.append(reminder)

    reminded_ids = {r.appointment_id for r in current_patient_reminders}
    terminal = [a for a in appointments if a.status in ('Completed', 'No Show')]
    reminded_terminal = [a for a in terminal if a.id in reminded_ids]
    unreminded_terminal = [a for a in terminal if a.id not in reminded_ids]

    status_order = ['Pending', 'Confirmed', 'Completed', 'Cancelled', 'No Show']
    status_counts = {status: 0 for status in status_order}
    for appointment in appointments:
        status_counts.setdefault(appointment.status, 0)
        status_counts[appointment.status] += 1

    completed = status_counts.get('Completed', 0)
    no_show = status_counts.get('No Show', 0)
    cancelled = status_counts.get('Cancelled', 0)
    terminal_count = completed + no_show
    rescheduled_count = sum(1 for a in appointments if (a.reschedule_count or 0) > 0)
    total_reschedules = sum(a.reschedule_count or 0 for a in appointments)

    reminded_no_show = sum(1 for a in reminded_terminal if a.status == 'No Show')
    unreminded_no_show = sum(1 for a in unreminded_terminal if a.status == 'No Show')

    daily_counts = Counter(a.date.date() for a in appointments if a.date and a.status != 'Cancelled')
    daily_labels = []
    daily_values = []
    for offset in range(days):
        day = start_date + timedelta(days=offset)
        daily_labels.append(day.strftime('%d %b'))
        daily_values.append(daily_counts.get(day, 0))

    workload_appointments = [a for a in appointments if a.status != 'Cancelled' and a.date]
    weekday_counts = Counter(a.date.strftime('%A') for a in workload_appointments)
    hour_counts = Counter(a.date.strftime('%I %p').lstrip('0') for a in workload_appointments)
    weekday_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    busiest_weekday = max(weekday_order, key=lambda day: weekday_counts.get(day, 0)) if workload_appointments else '—'
    busiest_hour = max(hour_counts, key=hour_counts.get) if hour_counts else '—'

    waitlist_query = WaitlistEntry.query.filter(
        WaitlistEntry.target_date >= start_date,
        WaitlistEntry.target_date <= end_date,
    )
    if doctor_id is not None:
        waitlist_query = waitlist_query.filter(WaitlistEntry.doctor_id == doctor_id)
    waitlist_entries = waitlist_query.all()
    waitlist_status_order = ['Waiting', 'Offered', 'Booked', 'Expired', 'Cancelled']
    waitlist_status_counts = {status: 0 for status in waitlist_status_order}
    for entry in waitlist_entries:
        waitlist_status_counts.setdefault(entry.status, 0)
        waitlist_status_counts[entry.status] += 1
    waitlist_booked = waitlist_status_counts.get('Booked', 0)

    reminder_type_counts = Counter(r.reminder_type for r in current_patient_reminders)
    email_sent = sum(1 for r in current_patient_reminders if r.email_sent)

    if doctor_id is not None:
        utilization = _doctor_utilization(doctor_id, appointments, start_date, end_date)
    else:
        utilization = None

    doctor_rows = []
    if doctor_id is None:
        doctors = Doctor.query.filter_by(is_blacklisted=False).order_by(Doctor.name).all()
        by_doctor = defaultdict(list)
        for appointment in appointments:
            by_doctor[appointment.doctor_id].append(appointment)
        for doctor in doctors:
            doctor_appointments = by_doctor.get(doctor.id, [])
            doctor_terminal = [a for a in doctor_appointments if a.status in ('Completed', 'No Show')]
            doctor_no_show = sum(1 for a in doctor_terminal if a.status == 'No Show')
            util = _doctor_utilization(doctor.id, doctor_appointments, start_date, end_date)
            doctor_rows.append({
                'id': doctor.id,
                'name': doctor.name or f'Doctor #{doctor.id}',
                'appointments': len(doctor_appointments),
                'completed': sum(1 for a in doctor_appointments if a.status == 'Completed'),
                'no_show_rate': _pct(doctor_no_show, len(doctor_terminal)),
                'utilization_rate': util['utilization_rate'],
                'published_slots': util['published_slots'],
                'used_slots': util['used_slots'],
            })
        doctor_rows.sort(key=lambda row: (row['appointments'], row['utilization_rate']), reverse=True)

    return {
        'days': days,
        'start_date': start_date,
        'end_date': end_date,
        'total_appointments': len(appointments),
        'status_counts': status_counts,
        'completion_rate': _pct(completed, terminal_count),
        'no_show_rate': _pct(no_show, terminal_count),
        'cancellation_rate': _pct(cancelled, len(appointments)),
        'rescheduled_appointments': rescheduled_count,
        'reschedule_rate': _pct(rescheduled_count, len(appointments)),
        'average_reschedules_when_rescheduled': round(total_reschedules / rescheduled_count, 1) if rescheduled_count else 0.0,
        'patient_reminder_deliveries': len(current_patient_reminders),
        'reminder_24h_count': reminder_type_counts.get('24h', 0),
        'reminder_2h_count': reminder_type_counts.get('2h', 0),
        'reminder_email_sent': email_sent,
        'outcome_visits_reminded': len(reminded_terminal),
        'reminder_outcome_coverage': _pct(len(reminded_terminal), terminal_count),
        'reminded_no_show_rate': _pct(reminded_no_show, len(reminded_terminal)),
        'unreminded_no_show_rate': _pct(unreminded_no_show, len(unreminded_terminal)),
        'waitlist_total': len(waitlist_entries),
        'waitlist_status_counts': waitlist_status_counts,
        'waitlist_booked': waitlist_booked,
        'waitlist_conversion_rate': _pct(waitlist_booked, len(waitlist_entries)),
        'busiest_weekday': busiest_weekday,
        'busiest_hour': busiest_hour,
        'daily_labels': daily_labels,
        'daily_values': daily_values,
        'weekday_labels': weekday_order,
        'weekday_values': [weekday_counts.get(day, 0) for day in weekday_order],
        'status_labels': status_order,
        'status_values': [status_counts.get(status, 0) for status in status_order],
        'utilization': utilization,
        'doctor_rows': doctor_rows,
    }
