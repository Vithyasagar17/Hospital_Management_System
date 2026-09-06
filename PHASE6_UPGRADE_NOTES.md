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
