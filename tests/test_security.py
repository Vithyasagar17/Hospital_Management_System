from tests.conftest import login
from app import db
from app.models import User


def test_role_access_is_server_side(client):
    login(client,'patient','Patient1234')
    response=client.get('/admin/dashboard')
    assert response.status_code == 403


def test_doctor_cannot_open_unrelated_patient(client, app):
    login(client,'doctor','Doctor1234')
    with app.app_context():
        other=User.query.filter_by(username='other').first()
        other_id=other.id
    response=client.get(f'/doctor/patient/{other_id}')
    assert response.status_code == 403


def test_patient_cannot_open_another_patients_appointment(client, app):
    login(client,'other','Other1234')
    response=client.get('/patient/appointment/1')
    assert response.status_code == 403


def test_password_change_invalidates_other_sessions(app):
    c1=app.test_client(); c2=app.test_client()
    login(c1,'patient','Patient1234'); login(c2,'patient','Patient1234')
    r=c1.post('/account/change-password',data={'current_password':'Patient1234','new_password':'NewPatient123','confirm_password':'NewPatient123'})
    assert r.status_code in (302,303)
    # second client still has old session version and is forced back to login
    r2=c2.get('/patient/dashboard', follow_redirects=False)
    assert r2.status_code in (302,303)
    assert '/login' in r2.headers['Location']


def test_unverified_new_account_cannot_login(client, app):
    with app.app_context():
        user=User(username='pending',email='pending@example.com',email_verified=False,role='Patient'); user.set_password('Pending1234'); db.session.add(user); db.session.commit()
    r=client.post('/login',data={'username':'pending','password':'Pending1234'},follow_redirects=False)
    assert r.status_code in (302,303)
    assert '/verify-email/resend' in r.headers['Location']


def test_security_headers(client):
    r=client.get('/login')
    assert r.headers['X-Frame-Options']=='DENY'
    assert r.headers['X-Content-Type-Options']=='nosniff'
    assert 'frame-ancestors' in r.headers['Content-Security-Policy']
