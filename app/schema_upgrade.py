"""Small SQLite compatibility upgrade for ZIP-based project versions.

The project intentionally keeps setup simple for coursework/demo use.  When an
older bundled hms.db is opened, these additive columns are created in-place so
Phase 2 works without deleting existing records or requiring a migration CLI.
"""
from sqlalchemy import text
from app import db


def _columns(table_name):
    rows = db.session.execute(text(f"PRAGMA table_info('{table_name}')")).fetchall()
    return {row[1] for row in rows}


def ensure_phase2_schema():
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
        try:
            existing = _columns(table_name)
        except Exception:
            # Fresh databases will be created from the SQLAlchemy models.
            continue
        for column, sql_type in additions.items():
            if column not in existing:
                db.session.execute(text(
                    f"ALTER TABLE {table_name} ADD COLUMN {column} {sql_type}"
                ))
    db.session.commit()
