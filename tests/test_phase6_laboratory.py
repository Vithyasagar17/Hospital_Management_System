from app import db
from app.models import LabOrder, LabOrderItem, LabTest, Notification, Patient, User
from tests.conftest import login


def _seed_tests(app):
    with app.app_context():
        cbc = LabTest(
            code='CBC', name='Complete Blood Count', category='Hematology',
            specimen_type='Whole blood', default_unit='g/dL', reference_range='12-16',
            turnaround_hours=6, is_active=True,
        )
        glucose = LabTest(
            code='FBS', name='Fasting Blood Sugar', category='Biochemistry',
            specimen_type='Plasma', default_unit='mg/dL', reference_range='70-99',
            turnaround_hours=4, is_active=True,
        )
        db.session.add_all([cbc, glucose])
        db.session.commit()
        return cbc.id, glucose.id


def _ids(app):
    with app.app_context():
        return {
            'doctor': User.query.filter_by(username='doctor').one().id,
            'patient': User.query.filter_by(username='patient').one().id,
            'other': User.query.filter_by(username='other').one().id,
        }


def test_doctor_creates_multi_test_order_for_related_patient(app, client):
    cbc_id, glucose_id = _seed_tests(app)
    ids = _ids(app)
    login(client, 'doctor', 'Doctor1234')

    response = client.post('/doctor/laboratory/order/new', data={
        'patient_id': ids['patient'],
        'priority': 'Urgent',
        'clinical_notes': 'Fever and weakness',
        'test_ids': [str(cbc_id), str(glucose_id)],
    }, follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        order = LabOrder.query.one()
        assert order.patient_id == ids['patient']
        assert order.doctor_id == ids['doctor']
        assert order.priority == 'Urgent'
        assert order.status == 'Ordered'
        assert {item.test_code_snapshot for item in order.items} == {'CBC', 'FBS'}
        assert Notification.query.filter_by(user_id=ids['patient'], title='Laboratory tests ordered').count() == 1


def test_doctor_cannot_order_for_unrelated_patient(app, client):
    cbc_id, _ = _seed_tests(app)
    ids = _ids(app)
    login(client, 'doctor', 'Doctor1234')

    response = client.post('/doctor/laboratory/order/new', data={
        'patient_id': ids['other'], 'priority': 'Routine', 'test_ids': [str(cbc_id)],
    }, follow_redirects=False)
    assert response.status_code == 403
    with app.app_context():
        assert LabOrder.query.count() == 0


def test_admin_lab_workflow_requires_specimen_and_releases_results(app, client):
    cbc_id, glucose_id = _seed_tests(app)
    ids = _ids(app)
    login(client, 'doctor', 'Doctor1234')
    client.post('/doctor/laboratory/order/new', data={
        'patient_id': ids['patient'], 'priority': 'Routine',
        'test_ids': [str(cbc_id), str(glucose_id)],
    })
    with app.app_context():
        order_id = LabOrder.query.one().id

    client.post('/logout', data={})
    login(client, 'admin', 'Admin1234')

    response = client.post(f'/admin/laboratory/order/{order_id}/status', data={
        'status': 'Sample Collected', 'specimen_id': '',
    }, follow_redirects=True)
    assert b'specimen ID' in response.data
    with app.app_context():
        assert db.session.get(LabOrder, order_id).status == 'Ordered'

    client.post(f'/admin/laboratory/order/{order_id}/status', data={
        'status': 'Sample Collected', 'specimen_id': 'SP-0001', 'sample_notes': 'Fasting sample',
    })
    client.post(f'/admin/laboratory/order/{order_id}/status', data={'status': 'Processing'})

    with app.app_context():
        order = db.session.get(LabOrder, order_id)
        assert order.status == 'Processing'
        assert order.specimen_id == 'SP-0001'
        items = sorted(order.items, key=lambda item: item.test_code_snapshot)
        item_ids = [item.id for item in items]

    response = client.post(f'/admin/laboratory/order/{order_id}/results', data={
        f'result_{item_ids[0]}': '13.8', f'interpretation_{item_ids[0]}': 'Normal',
        f'notes_{item_ids[0]}': '',
        f'result_{item_ids[1]}': '', f'interpretation_{item_ids[1]}': 'Normal',
        f'notes_{item_ids[1]}': '',
    }, follow_redirects=True)
    assert b'Enter a result' in response.data
    with app.app_context():
        assert db.session.get(LabOrder, order_id).status == 'Processing'

    client.post(f'/admin/laboratory/order/{order_id}/results', data={
        f'result_{item_ids[0]}': '13.8', f'interpretation_{item_ids[0]}': 'Normal',
        f'notes_{item_ids[0]}': 'Within range',
        f'result_{item_ids[1]}': '112', f'interpretation_{item_ids[1]}': 'High',
        f'notes_{item_ids[1]}': 'Repeat fasting if clinically indicated',
    })

    with app.app_context():
        order = db.session.get(LabOrder, order_id)
        assert order.status == 'Completed'
        assert order.completed_at is not None
        assert all(item.result_value for item in order.items)
        assert Notification.query.filter_by(user_id=ids['patient'], title='Lab results available').count() == 1
        assert Notification.query.filter_by(user_id=ids['doctor'], title='Lab results available').count() == 1


def test_specimen_id_is_unique(app, client):
    cbc_id, _ = _seed_tests(app)
    ids = _ids(app)
    login(client, 'doctor', 'Doctor1234')
    for _ in range(2):
        client.post('/doctor/laboratory/order/new', data={
            'patient_id': ids['patient'], 'priority': 'Routine', 'test_ids': [str(cbc_id)],
        })
    with app.app_context():
        order_ids = [order.id for order in LabOrder.query.order_by(LabOrder.id).all()]

    client.post('/logout', data={})
    login(client, 'admin', 'Admin1234')
    client.post(f'/admin/laboratory/order/{order_ids[0]}/status', data={
        'status': 'Sample Collected', 'specimen_id': 'SP-DUPLICATE',
    })
    response = client.post(f'/admin/laboratory/order/{order_ids[1]}/status', data={
        'status': 'Sample Collected', 'specimen_id': 'SP-DUPLICATE',
    }, follow_redirects=True)
    assert b'already assigned' in response.data
    with app.app_context():
        assert db.session.get(LabOrder, order_ids[1]).status == 'Ordered'


def test_patient_can_only_view_own_lab_order(app, client):
    cbc_id, _ = _seed_tests(app)
    ids = _ids(app)
    login(client, 'doctor', 'Doctor1234')
    client.post('/doctor/laboratory/order/new', data={
        'patient_id': ids['patient'], 'priority': 'Routine', 'test_ids': [str(cbc_id)],
    })
    with app.app_context():
        order_id = LabOrder.query.one().id

    client.post('/logout', data={})
    login(client, 'patient', 'Patient1234')
    assert client.get(f'/patient/laboratory/order/{order_id}').status_code == 200

    client.post('/logout', data={})
    login(client, 'other', 'Other1234')
    assert client.get(f'/patient/laboratory/order/{order_id}').status_code == 403


def test_inactive_catalog_test_cannot_be_ordered(app, client):
    cbc_id, _ = _seed_tests(app)
    ids = _ids(app)
    with app.app_context():
        test = db.session.get(LabTest, cbc_id)
        test.is_active = False
        db.session.commit()
    login(client, 'doctor', 'Doctor1234')
    response = client.post('/doctor/laboratory/order/new', data={
        'patient_id': ids['patient'], 'priority': 'Routine', 'test_ids': [str(cbc_id)],
    }, follow_redirects=True)
    assert b'unavailable' in response.data
    with app.app_context():
        assert LabOrder.query.count() == 0


def test_order_snapshot_survives_catalog_edit(app, client):
    cbc_id, _ = _seed_tests(app)
    ids = _ids(app)
    login(client, 'doctor', 'Doctor1234')
    client.post('/doctor/laboratory/order/new', data={
        'patient_id': ids['patient'], 'priority': 'Routine', 'test_ids': [str(cbc_id)],
    })
    with app.app_context():
        test = db.session.get(LabTest, cbc_id)
        test.name = 'CBC - Updated Catalog Name'
        test.reference_range = 'New range'
        db.session.commit()
        item = LabOrderItem.query.one()
        assert item.test_name_snapshot == 'Complete Blood Count'
        assert item.reference_range_snapshot == '12-16'
