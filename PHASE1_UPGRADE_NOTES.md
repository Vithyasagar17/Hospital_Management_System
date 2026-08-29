# Phase 1 Upgrade

This build extends the UI upgrade with functional scheduling and operational analytics while preserving the existing Flask/SQLite architecture.

## Dashboard analytics
- Admin: doctor/patient totals, today's appointments, total appointments, status counts, 7-day activity chart, recent activity.
- Doctor: today's visits, pending/confirmed/completed counts, 7-day workload chart, upcoming consultations.
- Patient: pending/confirmed/completed counts, upcoming consultations, appointment-status chart.

## Appointment workflow
- New requests begin as `Pending`.
- Doctors can transition `Pending → Confirmed` or `Pending → Cancelled`.
- Confirmed visits can transition `Confirmed → Completed` or `Confirmed → Cancelled`.
- Completed/Cancelled visits are terminal states.
- Patients can cancel only future Pending/Confirmed appointments.
- Role appointment pages now include status filters and clearer workflow actions.

## Availability and live slots
- Doctors can publish bookable windows up to 14 days ahead.
- Doctors can also create blocked windows inside availability.
- Patient booking generates 30-minute slots from those windows.
- Booked slots and blocked times are automatically removed.
- Booking is validated again server-side to prevent double bookings/stale selections.

## No schema migration required
Phase 1 uses the existing `Appointment` and `DoctorAvailability` tables, so the included database remains compatible.
