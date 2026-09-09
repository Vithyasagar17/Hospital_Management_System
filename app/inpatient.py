"""Inpatient operations helpers for Phase 6B.

Phase 6B.1 introduced wards and beds. Phase 6B.2 adds admissions,
bed allocation, transfer history, discharge, and inpatient safety rules.
Helpers intentionally do not commit; route handlers commit the clinical change,
audit record, and notifications in one transaction.
"""
from collections import Counter
from datetime import datetime

from app import db
from app.models import Admission, Bed, BedTransfer, Department, Doctor, Patient, Ward


WARD_TYPES = ('General', 'ICU', 'Private', 'Emergency', 'Other')
BED_STATUSES = ('Available', 'Reserved', 'Occupied', 'Maintenance')
ADMIN_SETTABLE_BED_STATUSES = ('Available', 'Reserved', 'Maintenance')
ADMISSION_STATUSES = ('Active', 'Discharged')


def ward_snapshot(ward_id):
    """Return bed-capacity and availability metrics for one ward."""
    ward = db.session.get(Ward, ward_id)
    if not ward:
        return None

    beds = Bed.query.filter_by(ward_id=ward.id).order_by(Bed.bed_number).all()
    counts = Counter(bed.status for bed in beds)
    capacity = len(beds)
    occupied = counts.get('Occupied', 0)
    reserved = counts.get('Reserved', 0)
    available = counts.get('Available', 0)
    maintenance = counts.get('Maintenance', 0)
    usable = max(capacity - maintenance, 0)
    occupancy_rate = round((occupied / usable) * 100, 1) if usable else 0.0

    return {
        'ward': ward,
        'capacity': capacity,
        'available': available,
        'reserved': reserved,
        'occupied': occupied,
        'maintenance': maintenance,
        'usable': usable,
        'occupancy_rate': occupancy_rate,
    }


def hospital_bed_snapshot():
    """Return hospital-wide bed metrics used by the Admin dashboard."""
    wards = Ward.query.all()
    beds = Bed.query.all()
    counts = Counter(bed.status for bed in beds)
    maintenance = counts.get('Maintenance', 0)
    occupied = counts.get('Occupied', 0)
    usable = max(len(beds) - maintenance, 0)

    return {
        'total_wards': len(wards),
        'active_wards': sum(1 for ward in wards if ward.is_active),
        'total_beds': len(beds),
        'available': counts.get('Available', 0),
        'reserved': counts.get('Reserved', 0),
        'occupied': occupied,
        'maintenance': maintenance,
        'occupancy_rate': round((occupied / usable) * 100, 1) if usable else 0.0,
    }


def department_bed_snapshot(department_id):
    """Aggregate ward and bed capacity for a department."""
    wards = Ward.query.filter_by(department_id=department_id).order_by(Ward.name).all()
    snapshots = [ward_snapshot(ward.id) for ward in wards]
    return {
        'wards': snapshots,
        'ward_count': len(wards),
        'active_wards': sum(1 for ward in wards if ward.is_active),
        'total_beds': sum(row['capacity'] for row in snapshots),
        'available_beds': sum(row['available'] for row in snapshots),
        'reserved_beds': sum(row['reserved'] for row in snapshots),
        'occupied_beds': sum(row['occupied'] for row in snapshots),
        'maintenance_beds': sum(row['maintenance'] for row in snapshots),
    }


def active_admission_for_patient(patient_id):
    return Admission.query.filter_by(patient_id=patient_id, status='Active').first()


def active_admission_for_bed(bed_id):
    return Admission.query.filter_by(bed_id=bed_id, status='Active').first()


def available_beds(department_id=None):
    """Return allocatable beds in active wards/departments."""
    query = Bed.query.join(Ward, Bed.ward_id == Ward.id).join(
        Department, Ward.department_id == Department.id
    ).filter(
        Bed.status == 'Available',
        Ward.is_active.is_(True),
        Department.is_active.is_(True),
    )
    if department_id is not None:
        query = query.filter(Ward.department_id == department_id)
    return query.order_by(Department.name, Ward.name, Bed.bed_number).all()


def _validate_allocation(patient_id, doctor_id, department_id, bed_id):
    patient = db.session.get(Patient, patient_id)
    doctor = db.session.get(Doctor, doctor_id)
    department = db.session.get(Department, department_id)
    bed = db.session.get(Bed, bed_id)

    if not patient or patient.is_blacklisted:
        raise ValueError('Choose an active patient.')
    if not doctor or doctor.is_blacklisted:
        raise ValueError('Choose an active admitting doctor.')
    if not department or not department.is_active:
        raise ValueError('Choose an active department.')
    if doctor.department_id != department.id:
        raise ValueError('The admitting doctor must belong to the selected department.')
    if not bed or not bed.ward or not bed.ward.is_active:
        raise ValueError('Choose a bed in an active ward.')
    if bed.ward.department_id != department.id:
        raise ValueError('The selected bed must belong to the admitting department.')
    if bed.status != 'Available':
        raise ValueError('That bed is no longer available.')
    if active_admission_for_patient(patient.id):
        raise ValueError('This patient already has an active inpatient admission.')
    if active_admission_for_bed(bed.id):
        raise ValueError('That bed is already assigned to an active admission.')
    return patient, doctor, department, bed


def admit_patient(*, patient_id, doctor_id, department_id, bed_id, reason,
                  diagnosis=None, appointment_id=None, created_by_id=None):
    """Create an active admission and atomically occupy its bed."""
    if not (reason or '').strip():
        raise ValueError('Admission reason is required.')

    patient, doctor, department, bed = _validate_allocation(
        patient_id, doctor_id, department_id, bed_id
    )

    admission = Admission(
        patient_id=patient.id,
        doctor_id=doctor.id,
        department_id=department.id,
        ward_id=bed.ward_id,
        bed_id=bed.id,
        appointment_id=appointment_id,
        admitted_at=datetime.utcnow(),
        reason=reason.strip(),
        diagnosis=(diagnosis or '').strip() or None,
        status='Active',
        room_rate_snapshot=bed.ward.daily_rate,
        created_by_id=created_by_id,
    )
    bed.status = 'Occupied'
    bed.updated_at = datetime.utcnow()
    db.session.add(admission)
    db.session.flush()
    return admission


def transfer_admission(admission, *, to_bed_id, transferred_by_id=None, reason=None):
    """Move an active inpatient to another available bed in the same department."""
    if not admission or admission.status != 'Active':
        raise ValueError('Only active admissions can be transferred.')

    target = db.session.get(Bed, to_bed_id)
    if not target or not target.ward or not target.ward.is_active:
        raise ValueError('Choose a bed in an active ward.')
    if target.ward.department_id != admission.department_id:
        raise ValueError('Transfers must remain within the current department.')
    if target.id == admission.bed_id:
        raise ValueError('Choose a different bed for the transfer.')
    if target.status != 'Available' or active_admission_for_bed(target.id):
        raise ValueError('That destination bed is no longer available.')

    old_bed = admission.bed
    old_ward = admission.ward
    transfer = BedTransfer(
        admission_id=admission.id,
        from_ward_id=old_ward.id,
        from_bed_id=old_bed.id,
        to_ward_id=target.ward_id,
        to_bed_id=target.id,
        reason=(reason or '').strip() or None,
        transferred_at=datetime.utcnow(),
        transferred_by_id=transferred_by_id,
        from_daily_rate_snapshot=old_ward.daily_rate,
        to_daily_rate_snapshot=target.ward.daily_rate,
    )

    old_bed.status = 'Available'
    old_bed.updated_at = datetime.utcnow()
    target.status = 'Occupied'
    target.updated_at = datetime.utcnow()
    admission.ward_id = target.ward_id
    admission.bed_id = target.id
    admission.updated_at = datetime.utcnow()
    db.session.add(transfer)
    db.session.flush()
    return transfer


def discharge_admission(admission, *, summary, discharged_by_id=None):
    """Close an admission and release the currently occupied bed."""
    if not admission or admission.status != 'Active':
        raise ValueError('Only active admissions can be discharged.')
    if not (summary or '').strip():
        raise ValueError('A discharge summary is required.')

    bed = admission.bed
    admission.status = 'Discharged'
    admission.discharged_at = datetime.utcnow()
    admission.discharge_summary = summary.strip()
    admission.discharged_by_id = discharged_by_id
    admission.updated_at = datetime.utcnow()
    if bed and bed.status == 'Occupied':
        bed.status = 'Available'
        bed.updated_at = datetime.utcnow()
    db.session.flush()
    return admission
