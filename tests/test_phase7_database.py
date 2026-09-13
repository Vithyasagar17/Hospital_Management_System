from datetime import datetime, timezone

from app import create_app
from app.db_config import normalize_database_url, resolve_database_uri
from app.models import Appointment, WaitlistEntry
from app.timeutils import utc_now


def test_postgres_urls_are_normalized_to_psycopg3():
    assert normalize_database_url('postgres://u:p@db.example/hms') == 'postgresql+psycopg://u:p@db.example/hms'
    assert normalize_database_url('postgresql://u:p@db.example/hms') == 'postgresql+psycopg://u:p@db.example/hms'
    assert normalize_database_url('postgresql+psycopg://u:p@db.example/hms') == 'postgresql+psycopg://u:p@db.example/hms'


def test_database_url_environment_has_priority(monkeypatch, tmp_path):
    monkeypatch.setenv('HMS_DATABASE_URL', 'sqlite:///' + str(tmp_path / 'env.db').replace('\\', '/'))
    uri = resolve_database_uri(str(tmp_path / 'instance'))
    assert uri.endswith('/env.db')


def test_legacy_schema_upgrade_is_disabled_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv('HMS_LEGACY_SCHEMA_UPGRADE', raising=False)
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(tmp_path / 'phase7.db').replace('\\', '/'),
    })
    assert app.config['LEGACY_SCHEMA_UPGRADE'] is False


def test_utc_now_preserves_naive_utc_schema_contract():
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    value = utc_now()
    after = datetime.now(timezone.utc).replace(tzinfo=None)
    assert value.tzinfo is None
    assert before <= value <= after


def test_production_indexes_are_present_in_model_metadata():
    appointment_indexes = {index.name for index in Appointment.__table__.indexes}
    assert 'ix_appointment_doctor_date_status' in appointment_indexes
    assert 'ix_appointment_patient_date_status' in appointment_indexes

    waitlist_indexes = {index.name for index in WaitlistEntry.__table__.indexes}
    assert 'ix_waitlist_active_unique' in waitlist_indexes
    assert 'ix_waitlist_doctor_date_status_created' in waitlist_indexes
