from app import db
from app.departments import department_snapshot
from app.models import Department, Doctor
from tests.conftest import login


def test_admin_creates_department_and_assigns_doctor(app, client):
    login(client, 'admin', 'Admin1234')

    response = client.post('/admin/departments', data={
        'name': 'Cardiology',
        'code': 'CARD',
        'description': 'Heart and cardiovascular services',
        'location': 'Block B · Floor 2',
    }, follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        department = Department.query.filter_by(code='CARD').one()
        doctor = Doctor.query.filter_by(name='Dr Test').one()
        department_id = department.id
        doctor_id = doctor.id

    response = client.post(f'/admin/doctor/{doctor_id}/edit', data={
        'name': 'Dr Test',
        'specialization_id': '',
        'department_id': str(department_id),
    }, follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        doctor = db.session.get(Doctor, doctor_id)
        assert doctor.department_id == department_id


def test_department_head_must_belong_to_department(app, client):
    login(client, 'admin', 'Admin1234')
    client.post('/admin/departments', data={'name': 'Neurology', 'code': 'NEURO'})

    with app.app_context():
        department = Department.query.filter_by(code='NEURO').one()
        doctor = Doctor.query.filter_by(name='Dr Test').one()
        department_id = department.id
        doctor_id = doctor.id

    # The doctor has not been assigned yet, so leadership must be rejected.
    response = client.post(f'/admin/department/{department_id}', data={
        'name': 'Neurology',
        'code': 'NEURO',
        'description': '',
        'location': '',
        'head_doctor_id': str(doctor_id),
    }, follow_redirects=True)
    assert b'must be an active doctor assigned to this department' in response.data

    with app.app_context():
        assert db.session.get(Department, department_id).head_doctor_id is None


def test_department_metrics_and_patient_filter(app, client):
    login(client, 'admin', 'Admin1234')
    client.post('/admin/departments', data={'name': 'General Medicine', 'code': 'GEN'})

    with app.app_context():
        department = Department.query.filter_by(code='GEN').one()
        doctor = Doctor.query.filter_by(name='Dr Test').one()
        department_id = department.id
        doctor.department_id = department_id
        db.session.commit()

        snapshot = department_snapshot(department_id)
        assert snapshot['doctor_count'] == 1
        assert snapshot['active_doctors'] == 1
        assert snapshot['appointment_count'] == 1
        assert snapshot['unique_patients'] == 1

    client.post('/logout')
    login(client, 'patient', 'Patient1234')
    response = client.get(f'/patient/search-doctors?department_id={department_id}')
    assert response.status_code == 200
    assert b'Dr Test' in response.data
    assert b'General Medicine' in response.data


def test_department_cannot_deactivate_while_doctors_are_assigned(app, client):
    login(client, 'admin', 'Admin1234')
    client.post('/admin/departments', data={'name': 'Orthopedics', 'code': 'ORTHO'})

    with app.app_context():
        department = Department.query.filter_by(code='ORTHO').one()
        doctor = Doctor.query.filter_by(name='Dr Test').one()
        department_id = department.id
        doctor.department_id = department_id
        db.session.commit()

    response = client.post(f'/admin/department/{department_id}/toggle', follow_redirects=True)
    assert b'Reassign all doctors before deactivating this department' in response.data

    with app.app_context():
        assert db.session.get(Department, department_id).is_active is True


def test_department_head_cleared_when_doctor_moves(app, client):
    login(client, 'admin', 'Admin1234')
    client.post('/admin/departments', data={'name': 'Cardiology', 'code': 'CARD'})
    client.post('/admin/departments', data={'name': 'Emergency Medicine', 'code': 'ER'})

    with app.app_context():
        cardiology = Department.query.filter_by(code='CARD').one()
        emergency = Department.query.filter_by(code='ER').one()
        doctor = Doctor.query.filter_by(name='Dr Test').one()
        doctor.department_id = cardiology.id
        db.session.commit()
        cardiology.head_doctor_id = doctor.id
        db.session.commit()
        cardiology_id, emergency_id, doctor_id = cardiology.id, emergency.id, doctor.id

    client.post(f'/admin/doctor/{doctor_id}/edit', data={
        'name': 'Dr Test',
        'specialization_id': '',
        'department_id': str(emergency_id),
    })

    with app.app_context():
        assert db.session.get(Doctor, doctor_id).department_id == emergency_id
        assert db.session.get(Department, cardiology_id).head_doctor_id is None
