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
    """Add Phase 5 scheduling, reminder, and waitlist data safely."""
    inspector = inspect(db.engine)
    fresh_database = not inspector.has_table('user')

    if fresh_database:
        db.create_all()
    else:
        ensure_phase4_schema()
        _add_columns('appointment', {
            'reschedule_count': 'INTEGER NOT NULL DEFAULT 0',
            'last_rescheduled_at': 'DATETIME',
            'no_show_at': 'DATETIME',
        })

    from app.models import AppointmentReminder, WaitlistEntry
    AppointmentReminder.__table__.create(bind=db.engine, checkfirst=True)
    WaitlistEntry.__table__.create(bind=db.engine, checkfirst=True)

    # One live queue entry per patient/doctor/date. Closed historical rows do
    # not block the patient from joining that date again later.
    db.session.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_waitlist_active_unique "
        "ON waitlist_entry(patient_id, doctor_id, target_date) "
        "WHERE status IN ('Waiting', 'Offered')"
    ))
    db.session.commit()



def ensure_phase6_schema():
    """Add Phase 6 hospital operations structure without resetting Phase 5 data."""
    inspector = inspect(db.engine)
    fresh_database = not inspector.has_table('user')

    if fresh_database:
        db.create_all()
        return

    ensure_phase5_schema()

    from app.models import Department, Ward, Bed
    Department.__table__.create(bind=db.engine, checkfirst=True)
    _add_columns('doctor', {
        'department_id': 'INTEGER REFERENCES department(id)',
    })
    db.session.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_doctor_department_id ON doctor(department_id)"
    ))

    # Phase 6B.1: inpatient capacity infrastructure.
    Ward.__table__.create(bind=db.engine, checkfirst=True)
    Bed.__table__.create(bind=db.engine, checkfirst=True)

    # Phase 6B.2: admissions, transfer history and discharge workflow.
    from app.models import Admission, BedTransfer
    Admission.__table__.create(bind=db.engine, checkfirst=True)
    BedTransfer.__table__.create(bind=db.engine, checkfirst=True)
    db.session.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_admission_active_patient_unique "
        "ON admission(patient_id) WHERE status = 'Active'"
    ))
    db.session.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_admission_active_bed_unique "
        "ON admission(bed_id) WHERE status = 'Active'"
    ))

    # Phase 6C: laboratory catalog, multi-test orders and structured results.
    from app.models import LabTest, LabOrder, LabOrderItem
    LabTest.__table__.create(bind=db.engine, checkfirst=True)
    LabOrder.__table__.create(bind=db.engine, checkfirst=True)
    LabOrderItem.__table__.create(bind=db.engine, checkfirst=True)
    db.session.commit()
