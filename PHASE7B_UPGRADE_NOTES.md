# Phase 7B — Docker & Environment Configuration

Phase 7B makes the Phase 7A PostgreSQL/Alembic application reproducible as containers and introduces a safer separation between development and production runtime settings.

## Added

- `Dockerfile` based on Python 3.13 slim.
- Non-root `medora` runtime user.
- `docker-compose.yml` with Flask/Gunicorn and PostgreSQL 16 services.
- Persistent PostgreSQL named volume.
- PostgreSQL and web-container health checks.
- Migration-on-start entrypoint using the Phase 7A Alembic history.
- `requirements-prod.txt` with Gunicorn.
- Environment template in `.env.example`.
- Production startup validation for database, secret key, and secure cookies.
- Gunicorn worker/thread configuration through environment variables.
- Explicit one-time admin bootstrap script for a fresh PostgreSQL database.
- `.dockerignore` to keep secrets, virtual environments, local databases, caches and development artifacts out of the image context.

## First local Docker run

From the project root:

```powershell
Copy-Item .env.example .env
```

Generate a secret:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Put that value in `.env` as `HMS_SECRET_KEY` and replace the example PostgreSQL password. For local HTTP, keep:

```text
HMS_ENV=development
HMS_COOKIE_SECURE=0
```

Validate the composed configuration:

```powershell
docker compose config
```

Build and start:

```powershell
docker compose up --build -d
```

Inspect status and logs:

```powershell
docker compose ps
docker compose logs -f web
```

The web container waits for PostgreSQL to become healthy, validates its environment, executes:

```text
flask db upgrade
```

and then starts Gunicorn on port 8000.

Open:

```text
http://localhost:8000
```

## Bootstrap the first Admin on a fresh PostgreSQL database

The container intentionally does not seed demo credentials automatically. Create the first administrator explicitly:

```powershell
docker compose exec `
  -e HMS_BOOTSTRAP_ADMIN_PASSWORD="Choose-A-Strong-Password" `
  web python docker/bootstrap_admin.py
```

Optional overrides:

```text
HMS_BOOTSTRAP_ADMIN_USERNAME
HMS_BOOTSTRAP_ADMIN_EMAIL
```

The command is idempotent for an existing Admin username: rerunning it updates that Admin password rather than creating a duplicate account.

## Useful commands

Current migration:

```powershell
docker compose exec web python -m flask --app run db current
```

Run tests in an ephemeral image using the default test configuration:

```powershell
docker compose run --rm --no-deps -e HMS_RUN_MIGRATIONS=0 web python -m pytest -q
```

Open a shell:

```powershell
docker compose exec web sh
```

Stop containers while keeping database data:

```powershell
docker compose down
```

Delete containers **and PostgreSQL data**:

```powershell
docker compose down -v
```

Use `-v` only when you intentionally want a fresh database.

## Production mode

For a real HTTPS deployment set at least:

```text
HMS_ENV=production
HMS_COOKIE_SECURE=1
HMS_SECRET_KEY=<strong random secret>
POSTGRES_PASSWORD=<strong database password>
```

`docker/validate_env.py` refuses to start a production container with a placeholder/short secret, insecure cookies, or a non-PostgreSQL database URL.

The Compose defaults are intended for local development. Phase 7F will move deployment-specific concerns such as managed PostgreSQL, TLS/reverse-proxy settings, secrets management, release commands and horizontal scaling into the target hosting platform.

## Migration ownership

Phase 7B does not reintroduce runtime `ALTER TABLE` code. The entrypoint simply executes the Alembic migrations created in Phase 7A:

```text
Container starts
      ↓
Environment validation
      ↓
PostgreSQL healthy
      ↓
flask db upgrade
      ↓
Gunicorn
```

Set `HMS_RUN_MIGRATIONS=0` only when the deployment platform runs migrations as a separate release step.

## Architecture after Phase 7B

```text
Browser
   │
   ▼ :8000
Gunicorn / Flask container
   │
   ├── Alembic migration startup
   │
   └── SQLAlchemy + psycopg
              │
              ▼
        PostgreSQL 16
              │
              ▼
      persistent volume
```

Redis/Celery are deliberately not included yet; they belong to Phase 7C so background reminders, waitlist expiry and email delivery can be introduced as a separately testable infrastructure change.
