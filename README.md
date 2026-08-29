# Medora HMS — Hospital Management System

Python 3.10+ (Python 3.13 is supported by the pinned requirements).

## Quick run — Windows PowerShell

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
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
