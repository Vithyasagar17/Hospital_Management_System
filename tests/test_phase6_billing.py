from datetime import datetime, timedelta
from decimal import Decimal

from app import db
from app.billing import create_invoice
from app.models import (
    Admission, Appointment, Bed, Department, Doctor, Invoice, LabOrder, LabOrderItem,
    LabTest, Patient, User, Ward,
)
from tests.conftest import login


def _ids(app):
    with app.app_context():
        return {
            'admin': User.query.filter_by(username='admin').one().id,
            'doctor': User.query.filter_by(username='doctor').one().id,
            'patient': User.query.filter_by(username='patient').one().id,
            'other': User.query.filter_by(username='other').one().id,
            'appointment': Appointment.query.one().id,
        }


def test_completed_appointment_invoice_imports_consultation_and_lab_price_snapshot(app, client):
    ids = _ids(app)
    with app.app_context():
        doctor = db.session.get(Doctor, ids['doctor'])
        doctor.consultation_fee = Decimal('600.00')
        appointment = db.session.get(Appointment, ids['appointment'])
        appointment.status = 'Completed'
        test = LabTest(code='CBC', name='Complete Blood Count', base_price=Decimal('250.00'), is_active=True)
        db.session.add(test)
        db.session.flush()
        order = LabOrder(
            patient_id=ids['patient'], doctor_id=ids['doctor'], appointment_id=appointment.id,
            priority='Routine', status='Completed', completed_at=datetime.utcnow(),
        )
        db.session.add(order)
        db.session.flush()
        db.session.add(LabOrderItem(
            lab_order_id=order.id, lab_test_id=test.id,
            test_code_snapshot='CBC', test_name_snapshot='Complete Blood Count',
            price_snapshot=Decimal('250.00'),
        ))
        db.session.commit()

    login(client, 'admin', 'Admin1234')
    response = client.post('/admin/billing/new', data={
        'source': f'appointment:{ids["appointment"]}', 'patient_id': ids['patient'],
    }, follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        invoice = Invoice.query.one()
        assert invoice.status == 'Draft'
        assert invoice.invoice_number.startswith('INV-')
        assert invoice.total == Decimal('850.00')
        assert {item.source_type for item in invoice.items} == {'Appointment', 'LabOrderItem'}

        # Later catalog/rate edits do not rewrite the generated invoice.
        db.session.get(Doctor, ids['doctor']).consultation_fee = Decimal('900.00')
        db.session.get(LabTest, LabTest.query.one().id).base_price = Decimal('400.00')
        db.session.commit()
        assert db.session.get(Invoice, invoice.id).total == Decimal('850.00')


def test_invoice_payment_flow_moves_issued_to_partial_then_paid(app, client):
    ids = _ids(app)
    login(client, 'admin', 'Admin1234')
    client.post('/admin/billing/new', data={'source': 'manual', 'patient_id': ids['patient']})
    with app.app_context():
        invoice_id = Invoice.query.one().id

    client.post(f'/admin/billing/invoice/{invoice_id}/item/manual', data={
        'description': 'Emergency procedure', 'quantity': '1', 'unit_price': '1000.00',
    })
    client.post(f'/admin/billing/invoice/{invoice_id}/issue', data={})
    with app.app_context():
        invoice = db.session.get(Invoice, invoice_id)
        assert invoice.status == 'Issued'
        assert invoice.balance_due == Decimal('1000.00')

    client.post(f'/admin/billing/invoice/{invoice_id}/payment', data={
        'amount': '400.00', 'method': 'UPI', 'reference': 'UPI-001',
    })
    with app.app_context():
        invoice = db.session.get(Invoice, invoice_id)
        assert invoice.status == 'Partially Paid'
        assert invoice.amount_paid == Decimal('400.00')
        assert invoice.balance_due == Decimal('600.00')

    response = client.post(f'/admin/billing/invoice/{invoice_id}/payment', data={
        'amount': '700.00', 'method': 'Cash',
    }, follow_redirects=True)
    assert b'cannot exceed the outstanding balance' in response.data

    client.post(f'/admin/billing/invoice/{invoice_id}/payment', data={
        'amount': '600.00', 'method': 'Cash',
    })
    with app.app_context():
        invoice = db.session.get(Invoice, invoice_id)
        assert invoice.status == 'Paid'
        assert invoice.amount_paid == Decimal('1000.00')
        assert invoice.balance_due == Decimal('0.00')
        assert invoice.paid_at is not None


def test_discharged_admission_invoice_adds_room_charge(app):
    ids = _ids(app)
    with app.app_context():
        department = Department(name='Cardiology', code='CARD', is_active=True)
        db.session.add(department); db.session.flush()
        doctor = db.session.get(Doctor, ids['doctor'])
        doctor.department_id = department.id
        ward = Ward(
            department_id=department.id, name='Cardiac Ward', code='CW', ward_type='General',
            daily_rate=Decimal('2000.00'), is_active=True,
        )
        db.session.add(ward); db.session.flush()
        bed = Bed(ward_id=ward.id, bed_number='CW-01', status='Available')
        db.session.add(bed); db.session.flush()
        admission = Admission(
            patient_id=ids['patient'], doctor_id=ids['doctor'], department_id=department.id,
            ward_id=ward.id, bed_id=bed.id, reason='Observation', status='Discharged',
            admitted_at=datetime.utcnow() - timedelta(hours=30), discharged_at=datetime.utcnow(),
            discharge_summary='Stable', room_rate_snapshot=Decimal('2000.00'),
        )
        db.session.add(admission); db.session.commit()
        invoice = create_invoice(patient_id=ids['patient'], admission_id=admission.id)
        db.session.commit()
        assert invoice.total == Decimal('4000.00')
        assert invoice.items[0].source_type == 'AdmissionRoom'
        assert '2 days' in invoice.items[0].description


def test_patient_cannot_view_another_patients_invoice(app, client):
    ids = _ids(app)
    with app.app_context():
        invoice = create_invoice(patient_id=ids['patient'])
        invoice.status = 'Issued'
        invoice.total = Decimal('100.00')
        invoice.balance_due = Decimal('100.00')
        invoice.issued_at = datetime.utcnow()
        db.session.commit()
        invoice_id = invoice.id

    login(client, 'patient', 'Patient1234')
    assert client.get(f'/patient/billing/invoice/{invoice_id}').status_code == 200
    client.post('/logout', data={})
    login(client, 'other', 'Other1234')
    assert client.get(f'/patient/billing/invoice/{invoice_id}').status_code == 403
