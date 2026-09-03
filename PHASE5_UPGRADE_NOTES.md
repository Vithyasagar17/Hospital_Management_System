# Phase 5A — Smart Scheduling Core

This slice establishes the scheduling rules that reminders and waitlists will build on.

## Added
- Patient appointment rescheduling using only live doctor availability.
- Rescheduled appointments return to `Pending` for doctor confirmation.
- Reschedule count and last-rescheduled timestamp are preserved on the appointment.
- Doctor and audit notifications for schedule changes.
- `No Show` appointment workflow for doctors after the scheduled time has passed.
- No-show timestamp and status filtering across Admin, Doctor, and Patient views.
- Patient conflict protection so one patient cannot hold two active visits at the same time.
- Stronger doctor-slot conflict validation during booking and rescheduling.
- Same-type doctor availability windows can no longer overlap redundantly.
- Phase 5 scheduling regression tests.

## Database compatibility
`ensure_phase5_schema()` adds these appointment columns without resetting existing data:
- `reschedule_count`
- `last_rescheduled_at`
- `no_show_at`

## Next Phase 5 slices
- Automated appointment reminders.
- Waitlist and released-slot notifications.
- No-show analytics and reminder effectiveness metrics.

## Phase 5B — Appointment reminders
- Added idempotent 24-hour and 2-hour reminder processing for confirmed appointments.
- Reminder windows are mutually exclusive so a late first run does not stack both reminders at once.
- Added `appointment_reminder` delivery ledger with a unique key across appointment, recipient, reminder type, and schedule snapshot.
- Rescheduled appointments can receive fresh reminders for the new schedule without deleting historical deliveries.
- Patient reminders are enabled by default; doctor reminders are optional from the CLI.
- In-app notifications are the default delivery channel.
- Optional email delivery reuses the existing console/SMTP mail transport; console mode remains simulated.
- Appointment detail shows which reminders have been sent for the current schedule.
- Added a manual CLI command suitable for local testing and future scheduler/worker integration.

### Run reminders manually
```powershell
python -m flask --app run send-appointment-reminders
```

Include doctors as recipients:
```powershell
python -m flask --app run send-appointment-reminders --include-doctors
```

Also attempt email delivery (console mode prints the email; SMTP mode sends it):
```powershell
python -m flask --app run send-appointment-reminders --email
```

## Phase 5C — Waitlist and released-slot promotion
- Patients can join a doctor's waitlist for a published date only when all bookable slots are occupied.
- Active duplicate waitlist entries are prevented at both application and SQLite index levels.
- Patient and doctor workspaces now include dedicated waitlist views.
- Cancelling or rescheduling an appointment immediately offers the released slot to the oldest eligible waiting patient.
- Doctor-side cancellation also triggers the same released-slot workflow.
- Offers last 15 minutes and create in-app notifications with a direct claim link.
- Offered slots are temporarily reserved and disappear from normal booking choices during the claim window.
- Patients explicitly claim offers; successful claims create a new `Pending` appointment for doctor confirmation.
- Declined/expired offers can promote the same slot to the next waiting patient.
- Waitlist history records Waiting, Offered, Booked, Cancelled, and Expired states.
- Added CLI maintenance for expired offers:

```powershell
python -m flask --app run process-waitlist-offers
```

- Added Phase 5C regression tests for fully-booked dates, released-slot offers, temporary holds, claiming, duplicate prevention, and expiry promotion.
