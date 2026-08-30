"""Security helpers used by Phase 4.

The project intentionally keeps these helpers framework-light so the local
Flask demo remains easy to run. SMTP is optional; in console mode security
links are printed to the terminal for local development only.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage
from urllib.parse import urljoin, urlparse

from flask import current_app, request, session, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

logger = logging.getLogger(__name__)


def validate_password(password: str) -> tuple[bool, str]:
    if len(password or '') < 8:
        return False, 'Password must be at least 8 characters long.'
    if not any(c.islower() for c in password):
        return False, 'Password must contain a lowercase letter.'
    if not any(c.isupper() for c in password):
        return False, 'Password must contain an uppercase letter.'
    if not any(c.isdigit() for c in password):
        return False, 'Password must contain a number.'
    return True, ''


def generate_csrf_token() -> str:
    token = session.get('_csrf_token')
    if not token:
        token = secrets.token_urlsafe(32)
        session['_csrf_token'] = token
    return token


def validate_csrf_token(token: str | None) -> bool:
    expected = session.get('_csrf_token')
    return bool(expected and token and hmac.compare_digest(expected, token))


def client_ip() -> str:
    # Only trust X-Forwarded-For when explicitly configured behind a proxy.
    if current_app.config.get('TRUST_PROXY_HEADERS'):
        forwarded = request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
        if forwarded:
            return forwarded[:64]
    return (request.remote_addr or 'unknown')[:64]


def ip_fingerprint(ip: str) -> str:
    salt = current_app.config['SECRET_KEY'].encode('utf-8')
    return hashlib.sha256(salt + ip.encode('utf-8')).hexdigest()[:32]


def is_safe_next_url(target: str | None) -> bool:
    if not target:
        return False
    host_url = urlparse(request.host_url)
    redirect_url = urlparse(urljoin(request.host_url, target))
    return redirect_url.scheme in {'http', 'https'} and host_url.netloc == redirect_url.netloc


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


def make_token(user, purpose: str) -> str:
    payload = {
        'uid': user.id,
        'email': user.email,
        'purpose': purpose,
        'sv': user.session_version,
    }
    return _serializer().dumps(payload, salt=f'hms-{purpose}')


def read_token(token: str, purpose: str, max_age: int):
    try:
        payload = _serializer().loads(token, salt=f'hms-{purpose}', max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    if payload.get('purpose') != purpose:
        return None
    return payload


def send_security_email(recipient: str, subject: str, body: str) -> bool:
    """Send via SMTP or print to console in local demo mode.

    HMS_MAIL_MODE=console is intentionally a development-only mode. In a
    deployed environment set HMS_MAIL_MODE=smtp plus HMS_SMTP_* variables.
    """
    mode = current_app.config.get('MAIL_MODE', 'console')
    if mode == 'console':
        logger.warning('DEV SECURITY EMAIL to %s | %s\n%s', recipient, subject, body)
        print(f'\n--- HMS SECURITY EMAIL (development console) ---\nTo: {recipient}\nSubject: {subject}\n{body}\n--- END SECURITY EMAIL ---\n')
        return True
    if mode != 'smtp':
        logger.error('Unknown MAIL_MODE=%s', mode)
        return False

    server = current_app.config.get('SMTP_SERVER')
    port = int(current_app.config.get('SMTP_PORT', 587))
    username = current_app.config.get('SMTP_USERNAME')
    password = current_app.config.get('SMTP_PASSWORD')
    sender = current_app.config.get('SMTP_FROM') or username
    if not server or not sender:
        logger.error('SMTP is not fully configured.')
        return False

    msg = EmailMessage()
    msg['From'] = sender
    msg['To'] = recipient
    msg['Subject'] = subject
    msg.set_content(body)
    context = ssl.create_default_context()
    try:
        if current_app.config.get('SMTP_USE_SSL'):
            with smtplib.SMTP_SSL(server, port, context=context, timeout=15) as smtp:
                if username:
                    smtp.login(username, password or '')
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(server, port, timeout=15) as smtp:
                smtp.ehlo()
                if current_app.config.get('SMTP_USE_TLS', True):
                    smtp.starttls(context=context)
                    smtp.ehlo()
                if username:
                    smtp.login(username, password or '')
                smtp.send_message(msg)
        return True
    except Exception:
        logger.exception('Could not send HMS security email.')
        return False


def send_verification_email(user) -> bool:
    token = make_token(user, 'verify-email')
    link = url_for('auth.verify_email', token=token, _external=True)
    body = (
        f'Hello {user.username},\n\n'
        f'Verify your Medora HMS email address using this link:\n{link}\n\n'
        'This link expires in 24 hours. If you did not create this account, ignore this message.'
    )
    return send_security_email(user.email, 'Verify your Medora HMS account', body)


def send_password_reset_email(user) -> bool:
    token = make_token(user, 'reset-password')
    link = url_for('auth.reset_password', token=token, _external=True)
    body = (
        f'Hello {user.username},\n\n'
        f'Reset your Medora HMS password using this link:\n{link}\n\n'
        'This link expires in 30 minutes. If you did not request a reset, ignore this message.'
    )
    return send_security_email(user.email, 'Reset your Medora HMS password', body)


def login_window_start() -> datetime:
    return datetime.utcnow() - timedelta(minutes=current_app.config.get('LOGIN_RATE_WINDOW_MINUTES', 15))
