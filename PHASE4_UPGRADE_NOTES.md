# Phase 4 — Security & Reliability

## Added
- Global CSRF protection for every state-changing form.
- Email verification for new accounts (SMTP or local console mail mode).
- Forgot/reset password flow with expiring signed tokens.
- Authenticated password change with session invalidation.
- Login throttling and temporary account lockout after repeated failures.
- Server-side blacklisted-account enforcement.
- Stronger role/resource authorization (doctors only see patients they have treated/booked).
- Secure session/cookie defaults and common browser security headers.
- 400/403/404/500 branded error pages.
- Soft-delete/archive behavior for prescriptions so clinical history is not physically erased.
- Security audit events.
- UTF-8 requirements file plus separate `requirements-dev.txt`.
- Automated security regression tests under `tests/`.

## Email during local development
Default `HMS_MAIL_MODE=console` prints verification/reset links to the terminal. For deployment set `HMS_MAIL_MODE=smtp` and configure `HMS_SMTP_SERVER`, `HMS_SMTP_PORT`, `HMS_SMTP_USERNAME`, `HMS_SMTP_PASSWORD`, and `HMS_SMTP_FROM`.

## Production
Set a strong `HMS_SECRET_KEY` and enable HTTPS cookies with `HMS_COOKIE_SECURE=1`.
