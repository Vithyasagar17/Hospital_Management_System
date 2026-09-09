from app import db
from app.inpatient import department_bed_snapshot, hospital_bed_snapshot, ward_snapshot
from app.models import Bed, Department, Ward
from tests.conftest import login


def _create_department(client, name='Cardiology', code='CARD'):
    response = client.post('/admin/departments', data={'name': name, 'code': code}, follow_redirects=False)
    assert response.status_code == 302


def _department_id(app, code='CARD'):
    with app.app_context():
        return Department.query.filter_by(code=code).one().id


def test_admin_creates_ward_and_beds(app, client):
    login(client, 'admin', 'Admin1234')
    _create_department(client)
    department_id = _department_id(app)

    response = client.post('/admin/wards', data={
        'department_id': department_id,
        'name': 'Cardiac ICU',
        'code': 'CICU',
        'ward_type': 'ICU',
        'location': 'Block B · Floor 3',
    }, follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        ward = Ward.query.filter_by(code='CICU').one()
        ward_id = ward.id
        assert ward.department_id == department_id
        assert ward.ward_type == 'ICU'

    response = client.post(f'/admin/ward/{ward_id}/beds', data={
        'bed_number': 'CICU-01',
        'status': 'Available',
        'notes': 'Ventilator-ready',
    }, follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        bed = Bed.query.filter_by(ward_id=ward_id, bed_number='CICU-01').one()
        assert bed.status == 'Available'
        assert bed.notes == 'Ventilator-ready'


def test_duplicate_bed_number_is_rejected_within_ward(app, client):
    login(client, 'admin', 'Admin1234')
    _create_department(client)
    department_id = _department_id(app)
    client.post('/admin/wards', data={
        'department_id': department_id, 'name': 'General Ward', 'code': 'GENW', 'ward_type': 'General'
    })

    with app.app_context():
        ward_id = Ward.query.filter_by(code='GENW').one().id

    client.post(f'/admin/ward/{ward_id}/beds', data={'bed_number': 'G-01', 'status': 'Available'})
    response = client.post(
        f'/admin/ward/{ward_id}/beds',
        data={'bed_number': 'g-01', 'status': 'Available'},
        follow_redirects=True,
    )
    assert b'bed number already exists in this ward' in response.data

    with app.app_context():
        assert Bed.query.filter_by(ward_id=ward_id).count() == 1


def test_admin_cannot_manually_create_occupied_bed(app, client):
    login(client, 'admin', 'Admin1234')
    _create_department(client)
    department_id = _department_id(app)
    client.post('/admin/wards', data={
        'department_id': department_id, 'name': 'Private Ward', 'code': 'PRIV', 'ward_type': 'Private'
    })

    with app.app_context():
        ward_id = Ward.query.filter_by(code='PRIV').one().id

    response = client.post(
        f'/admin/ward/{ward_id}/beds',
        data={'bed_number': 'P-01', 'status': 'Occupied'},
        follow_redirects=True,
    )
    assert b'Occupied beds can only be assigned through the admission workflow' in response.data

    with app.app_context():
        assert Bed.query.filter_by(ward_id=ward_id).count() == 0


def test_reserved_bed_blocks_ward_deactivation(app, client):
    login(client, 'admin', 'Admin1234')
    _create_department(client)
    department_id = _department_id(app)
    client.post('/admin/wards', data={
        'department_id': department_id, 'name': 'Emergency Ward', 'code': 'ERW', 'ward_type': 'Emergency'
    })

    with app.app_context():
        ward = Ward.query.filter_by(code='ERW').one()
        ward_id = ward.id
        db.session.add(Bed(ward_id=ward.id, bed_number='ER-01', status='Reserved'))
        db.session.commit()

    response = client.post(f'/admin/ward/{ward_id}/toggle', follow_redirects=True)
    assert b'reserved or occupied beds cannot be deactivated' in response.data

    with app.app_context():
        assert db.session.get(Ward, ward_id).is_active is True


def test_active_ward_blocks_department_deactivation(app, client):
    login(client, 'admin', 'Admin1234')
    _create_department(client, name='Neurology', code='NEURO')
    department_id = _department_id(app, 'NEURO')
    client.post('/admin/wards', data={
        'department_id': department_id, 'name': 'Neuro Ward', 'code': 'NW', 'ward_type': 'General'
    })

    response = client.post(f'/admin/department/{department_id}/toggle', follow_redirects=True)
    assert b'Deactivate all wards before deactivating this department' in response.data

    with app.app_context():
        assert db.session.get(Department, department_id).is_active is True


def test_bed_capacity_metrics(app):
    with app.app_context():
        department = Department(name='Critical Care', code='CC', is_active=True)
        db.session.add(department)
        db.session.flush()
        ward = Ward(department_id=department.id, name='Critical Care Unit', code='CCU', ward_type='ICU')
        db.session.add(ward)
        db.session.flush()
        db.session.add_all([
            Bed(ward_id=ward.id, bed_number='01', status='Available'),
            Bed(ward_id=ward.id, bed_number='02', status='Reserved'),
            Bed(ward_id=ward.id, bed_number='03', status='Occupied'),
            Bed(ward_id=ward.id, bed_number='04', status='Maintenance'),
        ])
        db.session.commit()

        ward_metrics = ward_snapshot(ward.id)
        assert ward_metrics['capacity'] == 4
        assert ward_metrics['available'] == 1
        assert ward_metrics['reserved'] == 1
        assert ward_metrics['occupied'] == 1
        assert ward_metrics['maintenance'] == 1
        assert ward_metrics['occupancy_rate'] == 33.3

        department_metrics = department_bed_snapshot(department.id)
        assert department_metrics['ward_count'] == 1
        assert department_metrics['total_beds'] == 4
        assert department_metrics['available_beds'] == 1

        hospital_metrics = hospital_bed_snapshot()
        assert hospital_metrics['total_beds'] == 4
        assert hospital_metrics['occupied'] == 1
        assert hospital_metrics['occupancy_rate'] == 33.3
