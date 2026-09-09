from app import db
from app.models import Admission, Bed, BedTransfer, Department, Doctor, Patient, User, Ward
from tests.conftest import login


def _setup_inpatient_capacity(app, two_beds=True):
    with app.app_context():
        doctor_user = User.query.filter_by(username='doctor').one()
        department = Department(name='Cardiology', code='CARD', is_active=True)
        db.session.add(department)
        db.session.flush()
        doctor = db.session.get(Doctor, doctor_user.id)
        doctor.department_id = department.id
        ward = Ward(department_id=department.id, name='Cardiac Ward', code='CW', ward_type='General', is_active=True)
        db.session.add(ward)
        db.session.flush()
        bed1 = Bed(ward_id=ward.id, bed_number='CW-01', status='Available')
        db.session.add(bed1)
        if two_beds:
            db.session.add(Bed(ward_id=ward.id, bed_number='CW-02', status='Available'))
        db.session.commit()
        return doctor.id, department.id, ward.id, bed1.id


def _ids(app):
    with app.app_context():
        return {
            'patient': User.query.filter_by(username='patient').one().id,
            'other': User.query.filter_by(username='other').one().id,
            'doctor': User.query.filter_by(username='doctor').one().id,
        }


def test_admin_admission_occupies_bed_and_blocks_duplicate_patient(app, client):
    doctor_id, _, ward_id, bed1_id = _setup_inpatient_capacity(app)
    ids = _ids(app)
    login(client, 'admin', 'Admin1234')

    response = client.post('/admin/admissions', data={
        'patient_id': ids['patient'],
        'doctor_id': doctor_id,
        'bed_id': bed1_id,
        'reason': 'Telemetry observation',
        'diagnosis': 'Chest pain under evaluation',
    }, follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        admission = Admission.query.filter_by(patient_id=ids['patient'], status='Active').one()
        assert admission.reason == 'Telemetry observation'
        assert db.session.get(Bed, bed1_id).status == 'Occupied'
        bed2 = Bed.query.filter_by(ward_id=ward_id, bed_number='CW-02').one()
        bed2_id = bed2.id

    response = client.post('/admin/admissions', data={
        'patient_id': ids['patient'],
        'doctor_id': doctor_id,
        'bed_id': bed2_id,
        'reason': 'Duplicate attempt',
    }, follow_redirects=True)
    assert b'already has an active inpatient admission' in response.data

    with app.app_context():
        assert Admission.query.filter_by(patient_id=ids['patient'], status='Active').count() == 1
        assert db.session.get(Bed, bed2_id).status == 'Available'


def test_transfer_releases_old_bed_and_records_history(app, client):
    doctor_id, _, ward_id, bed1_id = _setup_inpatient_capacity(app)
    ids = _ids(app)
    login(client, 'admin', 'Admin1234')
    client.post('/admin/admissions', data={
        'patient_id': ids['patient'], 'doctor_id': doctor_id,
        'bed_id': bed1_id, 'reason': 'Observation',
    })

    with app.app_context():
        admission = Admission.query.filter_by(patient_id=ids['patient'], status='Active').one()
        admission_id = admission.id
        bed2_id = Bed.query.filter_by(ward_id=ward_id, bed_number='CW-02').one().id

    response = client.post(f'/admin/admission/{admission_id}/transfer', data={
        'bed_id': bed2_id, 'reason': 'Step-down placement'
    }, follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        admission = db.session.get(Admission, admission_id)
        assert admission.bed_id == bed2_id
        assert db.session.get(Bed, bed1_id).status == 'Available'
        assert db.session.get(Bed, bed2_id).status == 'Occupied'
        transfer = BedTransfer.query.filter_by(admission_id=admission_id).one()
        assert transfer.from_bed_id == bed1_id
        assert transfer.to_bed_id == bed2_id
        assert transfer.reason == 'Step-down placement'


def test_discharge_releases_bed_and_preserves_history(app, client):
    doctor_id, _, _, bed1_id = _setup_inpatient_capacity(app, two_beds=False)
    ids = _ids(app)
    login(client, 'admin', 'Admin1234')
    client.post('/admin/admissions', data={
        'patient_id': ids['patient'], 'doctor_id': doctor_id,
        'bed_id': bed1_id, 'reason': 'Overnight monitoring',
    })

    with app.app_context():
        admission_id = Admission.query.filter_by(patient_id=ids['patient'], status='Active').one().id

    response = client.post(f'/admin/admission/{admission_id}/discharge', data={'summary': ''}, follow_redirects=True)
    assert b'discharge summary is required' in response.data.lower()
    with app.app_context():
        assert db.session.get(Admission, admission_id).status == 'Active'
        assert db.session.get(Bed, bed1_id).status == 'Occupied'

    client.post(f'/admin/admission/{admission_id}/discharge', data={
        'summary': 'Stable at discharge. Follow up in one week.'
    })
    with app.app_context():
        admission = db.session.get(Admission, admission_id)
        assert admission.status == 'Discharged'
        assert admission.discharged_at is not None
        assert 'Stable at discharge' in admission.discharge_summary
        assert db.session.get(Bed, bed1_id).status == 'Available'
        assert Admission.query.filter_by(patient_id=ids['patient']).count() == 1


def test_doctor_can_admit_existing_patient_but_not_unrelated_patient(app, client):
    _, _, _, bed1_id = _setup_inpatient_capacity(app)
    ids = _ids(app)
    login(client, 'doctor', 'Doctor1234')

    response = client.post('/doctor/inpatients/admit', data={
        'patient_id': ids['patient'], 'bed_id': bed1_id,
        'reason': 'Needs inpatient observation',
    }, follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        assert Admission.query.filter_by(patient_id=ids['patient'], doctor_id=ids['doctor'], status='Active').count() == 1
        bed2_id = Bed.query.filter_by(bed_number='CW-02').one().id

    response = client.post('/doctor/inpatients/admit', data={
        'patient_id': ids['other'], 'bed_id': bed2_id,
        'reason': 'Should not be allowed',
    }, follow_redirects=False)
    assert response.status_code == 403


def test_patient_can_only_view_own_admission(app, client):
    doctor_id, _, _, bed1_id = _setup_inpatient_capacity(app)
    ids = _ids(app)
    login(client, 'admin', 'Admin1234')
    client.post('/admin/admissions', data={
        'patient_id': ids['patient'], 'doctor_id': doctor_id,
        'bed_id': bed1_id, 'reason': 'Observation',
    })
    with app.app_context():
        admission_id = Admission.query.filter_by(patient_id=ids['patient']).one().id

    client.post('/logout', data={})
    login(client, 'patient', 'Patient1234')
    assert client.get(f'/patient/admission/{admission_id}').status_code == 200

    client.post('/logout', data={})
    login(client, 'other', 'Other1234')
    assert client.get(f'/patient/admission/{admission_id}').status_code == 403


def test_doctor_department_change_is_blocked_with_active_inpatient(app, client):
    doctor_id, _, _, bed1_id = _setup_inpatient_capacity(app)
    ids = _ids(app)
    with app.app_context():
        other_department = Department(name='Neurology', code='NEURO', is_active=True)
        db.session.add(other_department)
        db.session.commit()
        other_department_id = other_department.id

    login(client, 'admin', 'Admin1234')
    client.post('/admin/admissions', data={
        'patient_id': ids['patient'], 'doctor_id': doctor_id,
        'bed_id': bed1_id, 'reason': 'Observation',
    })
    response = client.post(f'/admin/doctor/{doctor_id}/edit', data={
        'name': 'Dr Test', 'department_id': other_department_id,
    }, follow_redirects=True)
    assert b'active inpatients before changing departments' in response.data

    with app.app_context():
        doctor = db.session.get(Doctor, doctor_id)
        assert doctor.department.code == 'CARD'
