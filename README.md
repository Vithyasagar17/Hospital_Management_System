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


## Phase 5 smart scheduling

- Patient appointment rescheduling with conflict-safe slot validation
- No-show workflow and status analytics
- 24-hour and 2-hour idempotent appointment reminders
- Waitlist queue with temporary released-slot offers and patient claim flow
- Scheduling intelligence for no-shows, reminders, waitlist conversion and doctor utilization

## Phase 6 hospital operations

- First-class department records with code, description, location and active/inactive state
- Administrator-controlled doctor-to-department assignment
- Department-head assignment restricted to active doctors in the same department
- Safe reassignment rules that clear stale department-head relationships
- Department directory and department detail dashboards
- Department metrics for doctor count, unique patients, appointments, 30-day volume and workflow status
- Patient doctor discovery by department in addition to specialization
- Department context in doctor profiles, booking, and patient-facing doctor profiles
- Additive schema upgrade; existing Phase 5 data is preserved

### Phase 6B.1 wards & beds

- Department-linked ward directory with General, ICU, Private, Emergency and custom ward types
- Ward activation/deactivation and operational location metadata
- Bed inventory with Available, Reserved, Occupied and Maintenance states
- Duplicate bed and ward protection plus audit logging
- Hospital-wide and department-level bed-capacity metrics
- Admin dashboard occupancy and available-bed visibility
- Safety rules that reserve `Occupied` state for the upcoming admission workflow
- Additive schema upgrade with no database reset

### Phase 6B.2 admissions, transfers & discharge

- Inpatient admission records linked to patient, doctor, department, ward and bed
- Automatic bed occupation/release on admission, transfer and discharge
- Bed-transfer history with non-destructive movement tracking
- Admin and Doctor inpatient workspaces plus Patient hospital-stay history
- One-active-admission-per-patient and one-active-patient-per-bed concurrency safeguards
- Admission/transfer/discharge audit logging and notifications

See `PHASE6_UPGRADE_NOTES.md` for the Phase 6A, 6B.1 and 6B.2 demo flows.

### Phase 6C laboratory management

- Admin-managed laboratory test catalog with specimen/reference metadata and base pricing
- Multi-test diagnostic orders linked to outpatient appointments or inpatient admissions
- Routine/Urgent/STAT priority and sequential sample-processing workflow
- Unique specimen/barcode tracking and collection notes
- Structured result values, reference ranges, interpretations and result notes
- Doctor ordering restricted to established doctor-patient relationships
- Patient result portal plus Doctor/Admin laboratory workspaces
- Result-ready notifications, audit logging, and historical test-definition snapshots
- Additive schema upgrade with no database reset
