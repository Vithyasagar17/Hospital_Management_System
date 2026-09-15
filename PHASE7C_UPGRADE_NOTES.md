# Phase 7C — Redis, Celery & Scheduled Background Jobs

Phase 7C turns the Phase 5 reminder and waitlist maintenance commands into real background services. The existing domain functions remain the source of truth; Celery simply schedules and executes them outside the web process.

## Added

- Redis 7 broker service with persistent AOF-backed Docker volume.
- Celery worker container for background execution.
- Celery Beat container for periodic scheduling.
- Flask-aware Celery task base so workers execute inside an application context.
- Automatic appointment reminder task every 5 minutes by default.
- Automatic expired waitlist-offer processing every 60 seconds by default.
- Existing reminder uniqueness constraints remain the idempotency/concurrency guard.
- Existing waitlist promotion workflow is reused instead of duplicated.
- Optional background doctor reminders and reminder email delivery.
- Generic asynchronous email task for future migration of security/transactional email flows.
- Eager-mode regression tests that do not require a live Redis server.

## Services after Phase 7C

```text
Browser
   |
   v
Gunicorn / Flask ---- PostgreSQL
                         ^
                         |
Redis <---- Celery Worker+
  ^              ^
  |              |
  +--- Celery Beat
```

Docker Compose now runs five services:

```text
db
redis
web
worker
beat
```

## Periodic jobs

Default schedule:

```text
Appointment reminders     every 300 seconds
Waitlist maintenance      every  60 seconds
```

Configure them in `.env`:

```text
CELERY_REMINDER_INTERVAL_SECONDS=300
CELERY_WAITLIST_INTERVAL_SECONDS=60
```

The code enforces a minimum of 60 seconds for reminder scans and 15 seconds for waitlist scans.

## Reminder behavior

The worker calls the same `process_appointment_reminders()` function introduced in Phase 5B. Therefore the existing database uniqueness constraint still prevents duplicate 24-hour/2-hour reminders even when Beat runs repeatedly or a task safely retries.

Patient in-app reminders are enabled by default. To also remind Doctors:

```text
HMS_BACKGROUND_REMIND_DOCTORS=1
```

To attempt reminder email delivery from the worker:

```text
HMS_BACKGROUND_SEND_REMINDER_EMAILS=1
```

With `HMS_MAIL_MODE=console`, email remains simulated in worker logs. With SMTP configured, the worker performs real SMTP delivery outside the Gunicorn request processes.

## Waitlist behavior

Beat queues `medora.waitlist_maintenance` every minute. The worker:

1. Finds expired 15-minute offers.
2. Marks them Expired.
3. Releases the slot.
4. Offers it to the next eligible waiting patient.
5. Commits the state transition atomically.

The manual command remains available for troubleshooting:

```powershell
python -m flask --app run process-waitlist-offers
```

## First run

Install the new Python dependencies for non-Docker development:

```powershell
python -m pip install -r requirements.txt
```

Rebuild because the image dependency set changed:

```powershell
docker compose down
docker compose up --build -d
```

Inspect all services:

```powershell
docker compose ps
```

Expected running services:

```text
db
redis
web
worker
beat
```

Watch worker jobs:

```powershell
docker compose logs -f worker
```

Watch the scheduler:

```powershell
docker compose logs -f beat
```

## Useful checks

Redis:

```powershell
docker compose exec redis redis-cli ping
```

Expected:

```text
PONG
```

Celery registered tasks:

```powershell
docker compose exec worker celery -A celery_worker:celery_app inspect registered
```

The output should include:

```text
medora.appointment_reminders
medora.waitlist_maintenance
medora.send_email
```

Trigger tasks manually through Celery rather than the Flask CLI:

```powershell
docker compose exec worker celery -A celery_worker:celery_app call medora.appointment_reminders
docker compose exec worker celery -A celery_worker:celery_app call medora.waitlist_maintenance
```

Then inspect worker logs for the result.

## Failure isolation

Redis/Celery are deliberately separate from Gunicorn. If the worker is restarting, normal HMS pages can continue serving as long as PostgreSQL and the web container are healthy. The background jobs resume once the worker/broker recover.

`HMS_RUN_MIGRATIONS=0` is forced for worker and Beat containers. Only the web startup applies Alembic migrations, preventing three services from racing to run the same migration.

## Generic email task

`medora.send_email` wraps the existing `send_app_email()` implementation. Phase 7C does not rewrite every authentication route to queue email yet; that would mix infrastructure work with a large authentication behavior change. Future flows can migrate to asynchronous delivery one endpoint at a time.

## Test strategy

`tests/test_phase7_background.py` uses Celery eager mode and in-memory transports, so the normal pytest suite can verify task registration and Flask-context execution without requiring a live Redis server.
