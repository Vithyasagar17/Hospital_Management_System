# Medora HMS — Hospital Management System

Python 3.10+ (Python 3.13 is supported by the pinned requirements).

## Quick run — Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m ensurepip --upgrade
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python run.py
```

Open: http://127.0.0.1:5000

> Use `python -m pip` instead of plain `pip`. This guarantees packages are installed into the same virtual environment used to run the project.

## Database

The ZIP already includes an SQLite database. You do **not** need to run `create_db.py` just to start the app.

To intentionally reset everything to seeded demo data:

```powershell
python create_db.py
```

This deletes/recreates `instance/hms.db`, seeds the accounts below, and publishes sample doctor availability for the coming week.

### Seeded accounts

- Admin: `admin` / `supersecretadmin`
- Doctor: `dr_sample` / `doctorpass`
- Patient: `patient_sample` / `patientpass`

## Phase 1 workflow added

- Role-specific dashboard analytics
- Admin 7-day appointment activity chart and status snapshot
- Doctor workload dashboard and upcoming consultation list
- Patient appointment status analytics and upcoming schedule
- Appointment filters for Admin, Doctor, and Patient
- Controlled workflow: Pending → Confirmed → Completed, with cancellation rules
- Doctor availability windows for the next 14 days
- Bookable 30-minute slots generated from doctor availability
- Blocked availability windows remove overlapping slots
- Existing appointments automatically remove occupied slots
- Server-side validation prevents stale/double-booked slot submissions

## Phase 2 clinical workflow added

- Unified appointment detail page for both Doctor and Patient portals
- Doctor consultation notes stored with each visit
- Structured prescription: diagnosis, advice and optional follow-up date
- Medicine details: dosage, frequency, duration, quantity and instructions
- Printable digital prescription layout
- Patient read-only prescription view
- Chronological medical timeline with status, notes, diagnosis and prescription links
- Doctor-facing patient clinical timeline
- Existing SQLite databases are upgraded automatically with additive nullable columns; no reset is required

## Phase 3 operations layer added

- Notification bell and full notification center for every authenticated role
- Real workflow notifications for booking, status changes, cancellations, prescriptions and account actions
- Read/unread notification states with mark-all-read
- Admin universal search across doctors, patients and appointments
- Advanced filters for doctor/patient directories, appointments and prescriptions
- Patient doctor discovery can filter by specialization and a date with real free slots
- Admin-only audit log with actor, role, action, entity, timestamp and description
- Audit entries for login/logout, registration, admin account controls, appointment workflow, notes, prescriptions, medicines and availability
- Existing Phase 2 databases are upgraded automatically with additive `notification` and `audit_log` tables

See `PHASE3_UPGRADE_NOTES.md` for the recommended Phase 3 demo flow.


## Phase 4 security & reliability

- Email verification for new accounts using signed, expiring verification links
- Forgot/reset password with signed 30-minute reset tokens
- Password-change flow that invalidates other active sessions
- Global CSRF protection for all state-changing forms
- Login throttling plus temporary account lockout after repeated failures
- Blacklisted-account enforcement on the server
- Stronger object-level authorization: doctors can only access patients they have an appointment relationship with
- Secure session cookies, inactivity timeout, anti-framing/CSP/security headers
- Branded 400/403/404/500 error pages
- Prescription archival instead of destructive deletion
- Automated security regression tests (`python -m pytest`)

### Local verification/reset emails

The default `HMS_MAIL_MODE=console` prints verification and password-reset links in the terminal for local development. For real email delivery use `HMS_MAIL_MODE=smtp` and configure the `HMS_SMTP_*` environment variables documented in `PHASE4_UPGRADE_NOTES.md`.

### Production environment

Before deployment, set a long random `HMS_SECRET_KEY`, serve the app only over HTTPS, and set `HMS_COOKIE_SECURE=1`.

### Developer tests

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```
