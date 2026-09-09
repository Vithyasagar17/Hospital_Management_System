"""Laboratory workflow helpers for Phase 6C.

Doctors create orders for patients under their care. Admin currently represents
lab operations staff and advances specimen/result workflow. Helpers intentionally
do not commit so route handlers can persist the clinical change, audit log and
notifications in one transaction.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app import db
from app.models import Admission, Appointment, Doctor, LabOrder, LabOrderItem, LabTest, Patient


LAB_ORDER_STATUSES = ('Ordered', 'Sample Collected', 'Processing', 'Completed', 'Cancelled')
LAB_PRIORITIES = ('Routine', 'Urgent', 'STAT')
LAB_INTERPRETATIONS = ('Normal', 'Low', 'High', 'Abnormal', 'Critical')
LAB_TRANSITIONS = {
    'Ordered': ('Sample Collected', 'Cancelled'),
    'Sample Collected': ('Processing', 'Cancelled'),
    'Processing': ('Cancelled',),
    'Completed': (),
    'Cancelled': (),
}


def doctor_has_patient_relationship(doctor_id, patient_id):
    """Return whether the doctor has an appointment/admission relationship."""
    appointment = Appointment.query.filter_by(doctor_id=doctor_id, patient_id=patient_id).first()
    if appointment:
        return True
    admission = Admission.query.filter_by(doctor_id=doctor_id, patient_id=patient_id).first()
    return admission is not None


def doctor_patient_ids(doctor_id):
    ids = {
        row[0] for row in db.session.query(Appointment.patient_id)
        .filter(Appointment.doctor_id == doctor_id).distinct().all()
    }
    ids.update(
        row[0] for row in db.session.query(Admission.patient_id)
        .filter(Admission.doctor_id == doctor_id).distinct().all()
    )
    return ids


def active_lab_tests():
    return LabTest.query.filter_by(is_active=True).order_by(LabTest.category, LabTest.name).all()


def parse_price(value):
    value = (value or '').strip()
    if not value:
        return None
    try:
        price = Decimal(value)
    except (InvalidOperation, ValueError):
        raise ValueError('Price must be a valid non-negative number.')
    if price < 0:
        raise ValueError('Price cannot be negative.')
    return price.quantize(Decimal('0.01'))


def create_lab_order(*, patient_id, doctor_id, test_ids, priority='Routine', clinical_notes=None,
                     appointment_id=None, admission_id=None):
    patient = db.session.get(Patient, patient_id)
    doctor = db.session.get(Doctor, doctor_id)
    if not patient or patient.is_blacklisted:
        raise ValueError('Choose an active patient.')
    if not doctor or doctor.is_blacklisted:
        raise ValueError('Choose an active doctor.')
    if not doctor_has_patient_relationship(doctor.id, patient.id):
        raise PermissionError('Lab orders can only be created for patients under this doctor’s care.')
    if priority not in LAB_PRIORITIES:
        raise ValueError('Choose a valid lab priority.')

    appointment = None
    if appointment_id:
        appointment = db.session.get(Appointment, appointment_id)
        if not appointment or appointment.patient_id != patient.id or appointment.doctor_id != doctor.id:
            raise ValueError('The selected appointment does not belong to this doctor and patient.')

    admission = None
    if admission_id:
        admission = db.session.get(Admission, admission_id)
        if not admission or admission.patient_id != patient.id or admission.doctor_id != doctor.id:
            raise ValueError('The selected admission does not belong to this doctor and patient.')

    unique_ids = []
    for raw_id in test_ids or []:
        try:
            test_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if test_id not in unique_ids:
            unique_ids.append(test_id)
    if not unique_ids:
        raise ValueError('Select at least one laboratory test.')

    tests = LabTest.query.filter(LabTest.id.in_(unique_ids), LabTest.is_active.is_(True)).all()
    tests_by_id = {test.id: test for test in tests}
    if len(tests_by_id) != len(unique_ids):
        raise ValueError('One or more selected tests are unavailable.')

    order = LabOrder(
        patient_id=patient.id,
        doctor_id=doctor.id,
        appointment_id=appointment.id if appointment else None,
        admission_id=admission.id if admission else None,
        priority=priority,
        status='Ordered',
        clinical_notes=(clinical_notes or '').strip() or None,
        ordered_at=datetime.utcnow(),
    )
    db.session.add(order)
    db.session.flush()

    for test_id in unique_ids:
        test = tests_by_id[test_id]
        db.session.add(LabOrderItem(
            lab_order_id=order.id,
            lab_test_id=test.id,
            test_code_snapshot=test.code,
            test_name_snapshot=test.name,
            unit_snapshot=test.default_unit,
            reference_range_snapshot=test.reference_range,
            price_snapshot=test.base_price,
        ))
    db.session.flush()
    return order


def transition_lab_order(order, new_status, *, cancelled_reason=None, specimen_id=None, sample_notes=None):
    if not order:
        raise ValueError('Laboratory order not found.')
    if new_status not in LAB_ORDER_STATUSES:
        raise ValueError('Choose a valid laboratory status.')
    if new_status not in LAB_TRANSITIONS.get(order.status, ()):
        raise ValueError(f'Cannot move a laboratory order from {order.status} to {new_status}.')

    now = datetime.utcnow()
    if new_status == 'Sample Collected':
        specimen_id = (specimen_id or '').strip().upper()
        if not specimen_id:
            raise ValueError('A specimen ID / barcode is required when collecting the sample.')
        duplicate = LabOrder.query.filter(LabOrder.specimen_id == specimen_id, LabOrder.id != order.id).first()
        if duplicate:
            raise ValueError('That specimen ID is already assigned to another laboratory order.')
        order.specimen_id = specimen_id
        order.sample_notes = (sample_notes or '').strip() or None
        order.sample_collected_at = now
    elif new_status == 'Processing':
        order.processing_started_at = now
    elif new_status == 'Cancelled':
        reason = (cancelled_reason or '').strip()
        if not reason:
            raise ValueError('A cancellation reason is required.')
        order.cancelled_at = now
        order.cancelled_reason = reason

    order.status = new_status
    order.updated_at = now
    db.session.flush()
    return order


def complete_lab_order(order, result_payload):
    """Persist item results and complete an order currently in Processing."""
    if not order or order.status != 'Processing':
        raise ValueError('Results can only be finalized for an order in Processing status.')
    if not order.items:
        raise ValueError('This laboratory order has no tests.')

    now = datetime.utcnow()
    prepared = []
    for item in order.items:
        payload = result_payload.get(item.id, {})
        value = (payload.get('value') or '').strip()
        interpretation = (payload.get('interpretation') or '').strip()
        notes = (payload.get('notes') or '').strip()
        if not value:
            raise ValueError(f'Enter a result for {item.test_name_snapshot}.')
        if interpretation and interpretation not in LAB_INTERPRETATIONS:
            raise ValueError(f'Choose a valid interpretation for {item.test_name_snapshot}.')
        prepared.append((item, value, interpretation or None, notes or None))

    for item, value, interpretation, notes in prepared:
        item.result_value = value
        item.interpretation = interpretation
        item.result_notes = notes
        item.resulted_at = now

    order.status = 'Completed'
    order.completed_at = now
    order.updated_at = now
    db.session.flush()
    return order


def lab_order_summary(query=None):
    if query is None:
        query = LabOrder.query
    rows = query.all()
    return {
        'total': len(rows),
        'ordered': sum(1 for row in rows if row.status == 'Ordered'),
        'sample_collected': sum(1 for row in rows if row.status == 'Sample Collected'),
        'processing': sum(1 for row in rows if row.status == 'Processing'),
        'completed': sum(1 for row in rows if row.status == 'Completed'),
        'cancelled': sum(1 for row in rows if row.status == 'Cancelled'),
        'open': sum(1 for row in rows if row.status in ('Ordered', 'Sample Collected', 'Processing')),
    }
