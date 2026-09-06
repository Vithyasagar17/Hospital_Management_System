# Phase 6A — Hospital Departments

Phase 6A begins the hospital-operations layer by separating **clinical specialization** from **hospital department structure**.

## Added

- First-class `Department` model with name, unique code, description, location, status, and department head.
- Doctor-to-department assignment managed by Admin.
- Department head can only be an active doctor already assigned to that department.
- Reassigning or blacklisting a department head safely clears stale leadership assignment.
- Department deactivation is blocked while doctors are still assigned, preserving referential and operational consistency.
- Admin Department directory with active/inactive filters and 30-day activity summary.
- Department detail dashboard with:
  - active doctor count
  - unique patients served
  - total appointments
  - 30-day appointment volume
  - appointment status breakdown
  - assigned-doctor roster
  - recent department appointments
- Admin doctor directory can filter by department.
- Patient doctor discovery can search/filter by department.
- Patient and Doctor profile views now show the real department instead of conflating department with specialization.

## Database compatibility

`ensure_phase6_schema()` upgrades an existing Phase 5 SQLite database without resetting it:

- creates the `department` table
- adds nullable `doctor.department_id`
- adds an index for doctor department lookup

Existing doctors remain unassigned until an Admin places them into a department.

## Recommended demo

1. Admin → Departments → create **Cardiology (CARD)**.
2. Admin → Doctors → edit a doctor → assign Cardiology.
3. Open Cardiology → assign that doctor as Department Head.
4. Show department metrics and roster.
5. Patient → Find Doctors → filter by Cardiology department.
6. Doctor → My Profile → show the admin-managed department assignment.

## Next

Phase 6B should build on this structure with **wards, beds, admissions, transfers, and discharge workflows**.

---

# Phase 6B.1 — Wards & Bed Infrastructure

This slice adds the inpatient-capacity layer that admissions, transfers, and discharge will use in Phase 6B.2.

## Added

- First-class `Ward` model linked to a hospital department.
- Ward metadata: unique code, type, location, active/inactive state, and department association.
- Supported ward types: General, ICU, Private, Emergency, and Other.
- First-class `Bed` model with a ward-scoped unique bed number.
- Bed states: `Available`, `Reserved`, `Occupied`, and `Maintenance`.
- Admin ward directory with department/status/search filters and live bed-capacity summaries.
- Ward operations page for metadata, ward activation/deactivation, bed creation, and bed maintenance.
- Hospital-wide and department-level bed capacity metrics.
- Admin dashboard capacity cards for wards, total beds, available beds, reserved beds, and occupancy.
- Department detail pages now expose inpatient ward capacity.
- Audit events for ward and bed creation/update/state changes.

## Safety rules

- `Occupied` cannot be assigned manually; Phase 6B.2 admissions will own that state.
- Duplicate bed numbers inside the same ward are rejected.
- Duplicate ward codes are rejected hospital-wide.
- A ward with `Reserved` or `Occupied` beds cannot be deactivated or moved to another department.
- Beds in inactive wards cannot be newly reserved.
- Active wards prevent their parent department from being deactivated.
- No hard deletion is introduced, preserving future inpatient history.

## Database compatibility

`ensure_phase6_schema()` now also creates the `ward` and `bed` tables with `checkfirst=True`. Existing Phase 5/6A data remains unchanged; no database reset is required.

## Recommended demo

1. Admin → Departments → create **Cardiology**.
2. Admin → Wards & beds → create **Cardiac ICU (CICU)** under Cardiology.
3. Add beds `CICU-01`, `CICU-02`, and `CICU-03`.
4. Set one bed to Maintenance and another to Reserved.
5. Show the live ward capacity summary and Admin dashboard totals.
6. Attempt to deactivate the ward while a bed is Reserved to demonstrate the safety rule.

## Next

Phase 6B.2 will add **Admissions, bed allocation, ward/bed transfers, discharge, and inpatient history** on top of this infrastructure.

---

# Phase 6B.2 — Admissions, Transfers & Discharge

This slice turns the ward/bed inventory into a real inpatient workflow.

## Added

- First-class `Admission` model linking patient, admitting doctor, department, ward, bed, and optional source appointment.
- First-class `BedTransfer` history model that preserves every inpatient move instead of overwriting location history.
- Admin admission console for creating and searching active/discharged inpatient stays.
- Doctor inpatient workspace for admitting existing patients under their care.
- Patient hospital-stay history and current admission view.
- Automatic bed state transitions:
  - admission: `Available → Occupied`
  - transfer: old bed `Occupied → Available`, destination `Available → Occupied`
  - discharge: current bed `Occupied → Available`
- Transfer workflow restricted to available beds in the same department.
- Mandatory discharge summary and retained discharge timestamp/history.
- Inpatient notifications for admission, bed transfer, and discharge.
- Audit events for admission, transfer, and discharge.
- Ward bed board now identifies the patient occupying each bed and links to the active admission.
- Admin and Doctor dashboards expose current inpatient counts.

## Safety rules

- One active inpatient admission per patient.
- One active admission per bed.
- Blacklisted patients/doctors cannot be used for new admissions.
- Admitting doctor must belong to the same active department as the selected bed.
- Only active wards/departments and `Available` beds can receive admissions.
- Doctor admission is restricted to patients with an existing doctor–patient appointment relationship.
- Doctors can only view, transfer, and discharge admissions assigned to them.
- Patients can only view their own admission records.
- Database partial unique indexes protect active patient and active bed allocation from concurrent duplicate requests.

## Database compatibility

`ensure_phase6_schema()` creates `admission` and `bed_transfer` with `checkfirst=True` and adds partial unique indexes for active patient/bed assignment. Existing users, appointments, wards and beds are preserved.

## Recommended demo

1. Admin creates Cardiology → Cardiac Ward → beds `CW-01` and `CW-02`.
2. Assign a doctor to Cardiology.
3. Doctor opens an existing patient → **Admit patient** → choose `CW-01`.
4. Show `CW-01` automatically becoming **Occupied** and the patient appearing on the bed board.
5. Transfer the admission from `CW-01` to `CW-02` and show transfer history.
6. Discharge the patient with a summary and show `CW-02` returning to **Available**.
7. Login as the patient and show the complete hospital-stay record.

## Next

Phase 6C can add **laboratory ordering, sample tracking, results, and result notifications** on top of appointments and inpatient stays.
