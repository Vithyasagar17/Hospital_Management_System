import pytest
from app import create_app, db
from app.models import User, Doctor, Patient, Appointment
from datetime import datetime, timedelta


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / 'test.db'
    app = create_app({
        'TESTING': True,
        'TESTING_CSRF_DISABLED': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        'SECRET_KEY': 'test-secret',
        'MAIL_MODE': 'console',
    })
    with app.app_context():
        db.drop_all(); db.create_all()
        admin=User(username='admin',email='admin@example.com',email_verified=True,role='Admin'); admin.set_password('Admin1234')
        doc=User(username='doctor',email='doctor@example.com',email_verified=True,role='Doctor'); doc.set_password('Doctor1234')
        pat=User(username='patient',email='patient@example.com',email_verified=True,role='Patient'); pat.set_password('Patient1234')
        other=User(username='other',email='other@example.com',email_verified=True,role='Patient'); other.set_password('Other1234')
        db.session.add_all([admin,doc,pat,other]); db.session.flush()
        db.session.add(Doctor(id=doc.id,name='Dr Test'))
        db.session.add_all([Patient(id=pat.id,name='Patient One'),Patient(id=other.id,name='Patient Two')]); db.session.flush()
        db.session.add(Appointment(patient_id=pat.id,doctor_id=doc.id,date=datetime.now()+timedelta(days=1),time='10:00',reason='Checkup',status='Confirmed'))
        db.session.commit()
    yield app


@pytest.fixture()
def client(app): return app.test_client()


def login(client, username, password):
    return client.post('/login', data={'username':username,'password':password}, follow_redirects=False)
