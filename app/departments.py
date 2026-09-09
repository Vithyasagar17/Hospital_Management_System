"""Department-level operational metrics for Phase 6A."""
from datetime import datetime, timedelta

from sqlalchemy import distinct, func

from app import db
from app.models import Appointment, Department, Doctor


def department_snapshot(department_id, days=30):
    """Return a compact operational snapshot for one department."""
    department = db.session.get(Department, department_id)
    if not department:
        return None

    doctor_query = Doctor.query.filter(Doctor.department_id == department.id)
    doctor_ids = [row[0] for row in db.session.query(Doctor.id).filter(Doctor.department_id == department.id).all()]
    active_doctors = doctor_query.filter(Doctor.is_blacklisted.is_(False)).count()

    if not doctor_ids:
        return {
            'department': department,
            'doctor_count': 0,
            'active_doctors': 0,
            'appointment_count': 0,
            'appointments_30d': 0,
            'unique_patients': 0,
            'pending': 0,
            'confirmed': 0,
            'completed': 0,
            'cancelled': 0,
            'no_show': 0,
            'upcoming': 0,
        }

    base = Appointment.query.filter(Appointment.doctor_id.in_(doctor_ids))
    now = datetime.now()
    window_start = now - timedelta(days=days)

    status_counts = {
        status: base.filter(Appointment.status == status).count()
        for status in ['Pending', 'Confirmed', 'Completed', 'Cancelled', 'No Show']
    }
    unique_patients = db.session.query(func.count(distinct(Appointment.patient_id))).filter(
        Appointment.doctor_id.in_(doctor_ids)
    ).scalar() or 0

    return {
        'department': department,
        'doctor_count': len(doctor_ids),
        'active_doctors': active_doctors,
        'appointment_count': base.count(),
        'appointments_30d': base.filter(Appointment.date >= window_start, Appointment.date <= now).count(),
        'unique_patients': unique_patients,
        'pending': status_counts['Pending'],
        'confirmed': status_counts['Confirmed'],
        'completed': status_counts['Completed'],
        'cancelled': status_counts['Cancelled'],
        'no_show': status_counts['No Show'],
        'upcoming': base.filter(
            Appointment.date >= now,
            Appointment.status.in_(['Pending', 'Confirmed']),
        ).count(),
    }


def department_rows():
    rows = []
    for department in Department.query.order_by(Department.name).all():
        snapshot = department_snapshot(department.id)
        rows.append(snapshot)
    return rows
