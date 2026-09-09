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

---

# Phase 6C — Laboratory Management

This slice adds a structured diagnostics workflow across outpatient and inpatient care.

## Added

- First-class `LabTest` catalog with code, name, category, specimen type, default unit, reference range, base price, turnaround time, and active/inactive state.
- Multi-test `LabOrder` records linked to patient, ordering doctor, optional appointment, and optional inpatient admission.
- Historical `LabOrderItem` snapshots preserve the exact test name/code/unit/reference range even if the catalog changes later.
- Clinical priorities: `Routine`, `Urgent`, and `STAT`.
- Laboratory workflow: `Ordered → Sample Collected → Processing → Completed` with cancellation before completion.
- Specimen tracking using a unique specimen ID / barcode and optional collection notes.
- Structured result entry with value, reference range, interpretation (`Normal`, `Low`, `High`, `Abnormal`, `Critical`) and result note.
- Results can only be released after every ordered test has a result.
- Doctors can order tests only for patients with an existing appointment/admission relationship.
- Doctors can cancel an order only before sample collection begins.
- Admin laboratory operations workspace for specimen collection, processing, result release, and catalog management.
- Patient laboratory portal for order tracking and released results.
- Notifications for new orders, sample collection, processing, cancellation, and released results.
- Audit events for catalog changes, orders, workflow transitions, cancellation, and result release.
- Dashboard visibility for open laboratory workload.

## Safety and data-integrity rules

- Inactive catalog tests cannot be used in new orders.
- A laboratory order must contain at least one active test.
- Duplicate tests inside one order are collapsed/rejected by database uniqueness.
- Specimen IDs are unique across laboratory orders.
- Workflow transitions are sequential; result release cannot bypass collection/processing.
- `Completed` is not available through the generic status transition path; completion requires validated results for every order item.
- Patients can only read their own laboratory records.
- Doctors can only read/cancel laboratory orders they created.
- Historical orders use test snapshots so later catalog edits do not rewrite old clinical records.

## Database compatibility

`ensure_phase6_schema()` creates `lab_test`, `lab_order`, and `lab_order_item` using `checkfirst=True`. Existing Phase 6A/6B departments, wards, beds, admissions, appointments and prescriptions remain intact. No database reset is required.

## Recommended demo

1. Admin → Laboratory → Test catalog → create CBC and Fasting Blood Sugar.
2. Doctor → Patient → **Order lab tests** → select both tests and choose `Urgent`.
3. Patient → Laboratory → show the new `Ordered` record.
4. Admin → Laboratory → open the order → record specimen `SP-2026-0001` and mark **Sample Collected**.
5. Advance to **Processing**.
6. Enter results for every test, including an interpretation, then **Finalize results**.
7. Patient receives a result notification and can read the released values/reference ranges.
8. Doctor receives a result notification and can review the same finalized order.

## Next

Phase 6D can build **Billing & Invoicing** using appointment charges, inpatient stay charges, and the `LabTest.base_price` values introduced here.

---

# Phase 6D — Billing & Invoicing

This slice converts completed clinical work into auditable financial records without coupling payment state back into the clinical workflow.

## Added

- Doctor consultation fee and Ward daily-rate configuration.
- Historical billing snapshots for laboratory prices and inpatient ward rates.
- Reusable Admin billing service catalog for procedures, supplies, and other manual charges.
- Draft `Invoice` records with source links to completed appointments or discharged admissions.
- Automatic charge import for:
  - consultation fees from completed appointments,
  - completed laboratory test items using stored price snapshots,
  - inpatient room/bed charges from discharged admissions.
- Editable draft invoice items, quantity, discounts, due date, and notes.
- Invoice lifecycle: `Draft → Issued → Partially Paid → Paid`, plus controlled `Void` state.
- Payment ledger with Cash, Card, UPI, Bank Transfer, Insurance, and Other methods.
- Overpayment prevention and immutable issued charge lines.
- Patient billing portal with outstanding balance and invoice/payment history.
- Printable invoice view using a dedicated print layout.
- Admin billing dashboard with outstanding receivables, 30-day collections, issued value, unpaid invoices, and drafts.
- Patient notifications when invoices are issued, payments are recorded, or an issued invoice is voided.
- Billing audit events for service-catalog changes, invoice changes, issue, payment, and void operations.

## Data-integrity rules

- Only completed appointments can generate consultation invoices.
- Only discharged admissions can generate final inpatient room charges.
- The same consultation, lab result item, or inpatient stay cannot be billed twice on active invoices.
- Invoice prices are snapshots: later changes to doctor fees, lab catalog prices, ward rates, or service catalog prices do not rewrite existing invoice items.
- Laboratory orders now snapshot `LabTest.base_price` at order time.
- New admissions and transfers snapshot ward rates for later inpatient billing.
- Draft charges can be edited; issued invoice charge lines cannot.
- Payments cannot exceed the current outstanding balance.
- Invoices with recorded payments cannot be voided.
- Patients can only access their own non-draft invoices.

## Database compatibility

`ensure_phase6_schema()` additively creates `billing_service`, `invoice`, `invoice_item`, and `payment`, and adds nullable billing-rate snapshot columns to Doctor, Ward, Admission, BedTransfer, and LabOrderItem. Existing clinical data is preserved and no database reset is required.

## Recommended demo

1. Admin sets Dr. Test consultation fee to ₹600.
2. Admin sets Cardiac Ward daily rate to ₹2,000 and creates CBC with a ₹250 laboratory base price.
3. Complete an appointment and linked CBC result.
4. Admin → Billing → New invoice → choose the completed appointment.
5. Show the draft automatically containing Consultation ₹600 + CBC ₹250.
6. Add an ECG service from the charge catalog, apply an optional discount, and issue the invoice.
7. Login as the patient and show the issued invoice plus printable view.
8. Admin records a partial UPI payment; show `Issued → Partially Paid` and reduced balance.
9. Record the remaining payment; show `Partially Paid → Paid` and the full payment ledger.
10. Generate a discharged-admission invoice to demonstrate automatic ward/day charging.
