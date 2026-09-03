"""Additive compatibility upgrades for ZIP-based project versions."""
from sqlalchemy import text, inspect
from app import db


def _columns(table_name):
    rows = db.session.execute(text(f"PRAGMA table_info('{table_name}')")).fetchall()
    return {row[1] for row in rows}


def _add_columns(table_name, additions):
    inspector = inspect(db.engine)
    if not inspector.has_table(table_name):
        return
    existing = _columns(table_name)
    for column, sql_type in additions.items():
        if column not in existing:
            db.session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column} {sql_type}"))


def ensure_phase2_schema():
    _add_columns('prescription', {
        'advice': 'TEXT',
        'follow_up_date': 'DATE',
        'updated_at': 'DATETIME',
    })
    _add_columns('prescription_item', {
        'frequency': 'VARCHAR(100)',
        'instructions': 'VARCHAR(255)',
    })
    db.session.commit()


def ensure_phase3_schema():
    inspector = inspect(db.engine)
    if not inspector.has_table('user'):
        db.create_all()
        return
    ensure_phase2_schema()
    from app.models import Notification, AuditLog
    Notification.__table__.create(bind=db.engine, checkfirst=True)
    AuditLog.__table__.create(bind=db.engine, checkfirst=True)


def ensure_phase4_schema():
    inspector = inspect(db.engine)
    if not inspector.has_table('user'):
        db.create_all()
        return
    ensure_phase3_schema()

    # Existing users are marked verified so an upgrade never locks out the
    # current demo/admin accounts. New registrations explicitly set False.
    _add_columns('user', {
        'email': 'VARCHAR(255)',
        'email_verified': 'BOOLEAN NOT NULL DEFAULT 1',
        'failed_login_count': 'INTEGER NOT NULL DEFAULT 0',
        'locked_until': 'DATETIME',
        'last_login_at': 'DATETIME',
        'password_changed_at': 'DATETIME',
        'session_version': 'INTEGER NOT NULL DEFAULT 1',
    })
    _add_columns('prescription', {
        'is_deleted': 'BOOLEAN NOT NULL DEFAULT 0',
        'deleted_at': 'DATETIME',
        'deleted_by': 'INTEGER',
    })
    db.session.commit()

    from app.models import LoginAttempt
    LoginAttempt.__table__.create(bind=db.engine, checkfirst=True)
    # Application validation also protects uniqueness; this makes upgraded
    # SQLite databases enforce it when email is present.
    db.session.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_user_email_unique "
        "ON user(email) WHERE email IS NOT NULL"
    ))
    db.session.commit()


def ensure_phase5_schema():
    """Add scheduling metadata without resetting an existing Phase 4 database."""
    inspector = inspect(db.engine)
    if not inspector.has_table('user'):
        db.create_all()
        return

    ensure_phase4_schema()
    _add_columns('appointment', {
        'reschedule_count': 'INTEGER NOT NULL DEFAULT 0',
        'last_rescheduled_at': 'DATETIME',
        'no_show_at': 'DATETIME',
    })
    db.session.commit()
