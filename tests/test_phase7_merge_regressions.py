from datetime import datetime, timedelta, timezone

import pytest
from flask_migrate import downgrade, upgrade
from sqlalchemy import inspect, text

from app import create_app, db
from app.models import LoginAttempt, User
from app.timeutils import utc_now


@pytest.mark.parametrize('aware', [False, True])
def test_local_datetime_preserves_ist_display(app, aware):
    value = datetime(2026, 9, 13, 0, 0)
    if aware:
        value = value.replace(tzinfo=timezone.utc)
    display = app.jinja_env.filters['local_datetime']
    assert display(value, '%Y-%m-%d %H:%M') == '2026-09-13 05:30'
    assert display(None) == ''


def test_locked_login_does_not_add_failures(app, client):
    with app.app_context():
        user = User.query.filter_by(username='patient').one()
        user.locked_until = utc_now() + timedelta(minutes=15)
        db.session.commit()
        count = LoginAttempt.query.count()
    response = client.post('/login', data={
        'username': 'patient', 'password': 'Patient1234',
    })
    assert response.status_code == 429
    with app.app_context():
        assert LoginAttempt.query.count() == count


def test_csrf_remains_required(app, client):
    app.config['TESTING_CSRF_DISABLED'] = False
    assert client.post('/login', data={
        'username': 'patient', 'password': 'Patient1234',
    }).status_code == 400


def test_fresh_database_migration_roundtrip(tmp_path, monkeypatch):
    monkeypatch.delenv('HMS_LEGACY_SCHEMA_UPGRADE', raising=False)
    database = tmp_path / 'migrated.db'
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + database.as_posix(),
    })
    assert not database.exists(), 'Startup must not create or upgrade the database'
    with app.app_context():
        upgrade(directory='migrations')
        assert db.session.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '20260910_0002'
        inspector = inspect(db.engine)
        assert set(db.metadata.tables) <= set(inspector.get_table_names())
        for name, table in db.metadata.tables.items():
            assert set(table.columns.keys()) == {c['name'] for c in inspector.get_columns(name)}
        db.session.remove()
        downgrade(directory='migrations', revision='base')
        assert set(inspect(db.engine).get_table_names()) <= {'alembic_version'}
        upgrade(directory='migrations')
        db.session.remove()
        db.engine.dispose()
