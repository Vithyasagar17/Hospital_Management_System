"""Fail fast on unsafe production container configuration."""
from __future__ import annotations

import os
import sys


def _fail(message: str) -> None:
    print(f"[medora] configuration error: {message}", file=sys.stderr)
    raise SystemExit(2)


def main() -> None:
    mode = os.environ.get('HMS_ENV', 'development').strip().lower()
    database_url = os.environ.get('HMS_DATABASE_URL', '').strip()
    secret = os.environ.get('HMS_SECRET_KEY', '')

    if not database_url:
        _fail('HMS_DATABASE_URL is required inside the container.')

    if mode == 'production':
        if not database_url.startswith(('postgresql://', 'postgresql+psycopg://', 'postgres://')):
            _fail('production containers must use PostgreSQL.')
        if len(secret) < 32 or secret.startswith('change-me') or secret.startswith('replace-with'):
            _fail('HMS_SECRET_KEY must be a strong random value of at least 32 characters.')
        if os.environ.get('HMS_COOKIE_SECURE', '0') != '1':
            _fail('HMS_COOKIE_SECURE must be 1 in production.')

    print(f"[medora] environment validation passed ({mode}).")


if __name__ == '__main__':
    main()
