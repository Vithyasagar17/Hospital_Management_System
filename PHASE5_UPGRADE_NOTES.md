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
