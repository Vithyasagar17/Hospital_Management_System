# Phase 2 — Clinical Experience Upgrade

Phase 2 builds on the Phase 1 scheduling/status workflow without removing existing functionality.

## Added

- Role-aware appointment detail page for doctors and patients
- Doctor consultation notes separated from status controls
- Structured prescriptions linked to an appointment
- Prescription fields: diagnosis, advice, follow-up date
- Medicine fields: dosage, frequency, duration, quantity, instructions
- Printable patient-friendly digital prescription
- Patient read-only prescription view
- Patient medical history redesigned as a chronological timeline
- Doctor patient-history timeline with diagnosis and prescription links
- Direct navigation between appointment details and prescriptions
- Automatic additive SQLite schema upgrade for existing bundled databases
- Fresh database reset seeds one completed consultation and structured prescription for demos

## Existing database compatibility

You can keep the existing `instance/hms.db`. On app startup, `app/schema_upgrade.py` adds only the new nullable Phase 2 columns if they are missing. Existing rows are preserved.
