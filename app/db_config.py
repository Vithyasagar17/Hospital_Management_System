"""Database URL handling shared by local SQLite and production PostgreSQL."""
from __future__ import annotations

import os
from pathlib import Path


def normalize_database_url(value: str) -> str:
    """Normalize common hosted PostgreSQL URLs for SQLAlchemy + psycopg 3."""
    value = value.strip()
    if value.startswith('postgres://'):
        return 'postgresql+psycopg://' + value[len('postgres://'):]
    if value.startswith('postgresql://'):
        return 'postgresql+psycopg://' + value[len('postgresql://'):]
    return value


def resolve_database_uri(instance_path: str) -> str:
    """Prefer explicit production URLs, otherwise keep the local SQLite DB."""
    configured = os.environ.get('HMS_DATABASE_URL') or os.environ.get('DATABASE_URL')
    if configured:
        return normalize_database_url(configured)

    database_path = Path(instance_path) / 'hms.db'
    return f"sqlite:///{database_path.as_posix()}"
