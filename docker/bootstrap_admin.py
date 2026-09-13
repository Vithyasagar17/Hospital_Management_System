"""Explicit one-time admin bootstrap for a freshly migrated database.

Usage inside Docker Compose:

    docker compose exec \
      -e HMS_BOOTSTRAP_ADMIN_PASSWORD='use-a-strong-password' \
      web python docker/bootstrap_admin.py
"""
from __future__ import annotations

import os
import sys

from app import create_app, db
from app.models import User


def main() -> None:
    username = os.environ.get('HMS_BOOTSTRAP_ADMIN_USERNAME', 'admin').strip()
    email = os.environ.get('HMS_BOOTSTRAP_ADMIN_EMAIL', 'admin@medora.local').strip()
    password = os.environ.get('HMS_BOOTSTRAP_ADMIN_PASSWORD', '')

    if not username:
        raise SystemExit('HMS_BOOTSTRAP_ADMIN_USERNAME cannot be empty.')
    if len(password) < 12:
        raise SystemExit('Set HMS_BOOTSTRAP_ADMIN_PASSWORD to at least 12 characters.')

    app = create_app()
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        if user and user.role != 'Admin':
            raise SystemExit(f'User {username!r} already exists and is not an Admin.')

        created = user is None
        if user is None:
            user = User(
                username=username,
                email=email or None,
                email_verified=bool(email),
                role='Admin',
                session_version=1,
            )
            db.session.add(user)
        elif email:
            user.email = email
            user.email_verified = True

        user.set_password(password)
        user.failed_login_count = 0
        user.locked_until = None
        db.session.commit()

        action = 'created' if created else 'updated'
        print(f'Admin account {action}: {username}')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Admin bootstrap failed: {exc}', file=sys.stderr)
        raise
