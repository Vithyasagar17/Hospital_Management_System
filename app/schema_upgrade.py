"""Small SQLite compatibility upgrades for ZIP-based project versions.

Existing Phase 1/2 databases are upgraded additively in place. If the database
is missing entirely, the current SQLAlchemy model set is created instead.
"""
from sqlalchemy import text, inspect
from app import db


def _columns(table_name):
    rows = db.session.execute(text(f"PRAGMA table_info('{table_name}')")).fetchall()
    return {row[1] for row in rows}


def ensure_phase2_schema():
    inspector = inspect(db.engine)
    upgrades = {
        'prescription': {
            'advice': 'TEXT',
            'follow_up_date': 'DATE',
            'updated_at': 'DATETIME',
        },
        'prescription_item': {
            'frequency': 'VARCHAR(100)',
            'instructions': 'VARCHAR(255)',
        },
    }

    for table_name, additions in upgrades.items():
        if not inspector.has_table(table_name):
            continue
        existing = _columns(table_name)
        for column, sql_type in additions.items():
            if column not in existing:
                db.session.execute(text(
                    f"ALTER TABLE {table_name} ADD COLUMN {column} {sql_type}"
                ))
    db.session.commit()


def ensure_phase3_schema():
    inspector = inspect(db.engine)
    if not inspector.has_table('user'):
        # Handles a first run where instance/hms.db was removed manually.
        db.create_all()
        return

    ensure_phase2_schema()

    # New Phase 3 features use entirely additive tables. SQLAlchemy can create
    # only those missing tables without modifying any existing records.
    from app.models import Notification, AuditLog
    Notification.__table__.create(bind=db.engine, checkfirst=True)
    AuditLog.__table__.create(bind=db.engine, checkfirst=True)
