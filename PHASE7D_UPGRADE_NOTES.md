# Phase 7D — GitHub Actions CI/CD

Phase 7D adds automated validation and container delivery for Medora HMS. The goal is to catch regressions before merge and produce a reproducible Docker image after code reaches `main`, without deploying the application yet.

## Added

- Pull-request and push CI with GitHub Actions.
- PostgreSQL 16 and Redis 7 service containers during CI.
- Fresh-database Alembic migration verification on every CI run.
- Full `pytest` regression suite on Python 3.13.
- Python bytecode compilation smoke check.
- Docker Compose configuration validation.
- Production Docker image build validation.
- GHCR container publishing from `main`, version tags, or manual workflow dispatch.
- SHA, `latest`, and release-tag image metadata.
- GitHub Actions build cache for faster repeated image builds.
- Container provenance and SBOM generation on published images.
- Weekly Dependabot checks for Python, Docker, and GitHub Actions dependencies.

## CI workflow

`.github/workflows/ci.yml` runs for:

- pushes to `main`;
- pushes to `feature/**` branches;
- pull requests targeting `main`.

The validation pipeline is:

```text
Checkout
   ↓
Python 3.13
   ↓
Install dependencies
   ↓
Compile Python sources
   ↓
PostgreSQL + Redis service health
   ↓
Alembic upgrade on an empty PostgreSQL database
   ↓
Alembic revision inspection
   ↓
pytest
   ↓
Docker Compose validation
   ↓
Docker image build
```

The database used by CI is temporary. GitHub destroys the runner and service containers after the job finishes, so CI never touches local or production data.

## Why migrations are tested against an empty PostgreSQL database

Phase 7A established Alembic as the schema source of truth. A migration can appear correct against a developer database that already contains tables or data but still fail during a clean deployment.

The CI workflow therefore starts an empty PostgreSQL database and executes:

```bash
python -m flask --app run db upgrade
```

before running the test suite. This verifies that a new environment can be created entirely from migration history.

## Container delivery

`.github/workflows/container-release.yml` publishes a Docker image to GitHub Container Registry (GHCR).

It runs on:

- pushes to `main`;
- tags beginning with `v`, such as `v1.0.0`;
- manual `workflow_dispatch` runs.

The image name is:

```text
ghcr.io/<github-owner>/hospital-management-system
```

A push to the default branch receives tags similar to:

```text
latest
sha-<commit>
```

A release tag such as:

```text
v1.0.0
```

also produces a `v1.0.0` image tag.

No external registry password is required. GitHub Actions authenticates to GHCR through the repository-scoped `GITHUB_TOKEN` and the workflow requests only `contents: read` and `packages: write` permissions.

## This is delivery, not production deployment

Phase 7D intentionally stops after publishing the deployable container image:

```text
GitHub repository
      ↓
CI tests
      ↓
Docker build
      ↓
GHCR image
```

It does **not** automatically connect to a production server or hosting provider. Managed secrets, TLS, deployment environments, release commands, production database configuration, and rollback behavior belong to Phase 7F.

## First GitHub verification

Commit and push Phase 7D:

```powershell
git add .
git commit -m "ci: add phase 7D GitHub Actions pipeline"
git push origin feature/phase-7-production-engineering
```

Then open the repository on GitHub and select the **Actions** tab. The `CI` workflow should start for the feature branch.

The expected jobs are:

```text
Python tests + migrations  ✅
Docker build               ✅
```

If the branch is later merged into `main`, both `CI` and `Container Release` will run. The released image will appear under the repository/account package listings in GHCR.

## Pull-request protection

After the first successful CI run, repository branch protection can require the CI checks before allowing merges to `main`.

Recommended required check:

```text
Python tests + migrations
Docker build
```

Repository settings and protection-rule availability vary by GitHub plan and repository configuration, so Phase 7D does not attempt to modify those settings automatically.

## Dependabot

`.github/dependabot.yml` checks weekly for updates to:

- Python packages in `requirements*.txt`;
- Docker base images;
- GitHub Actions used by the workflows.

Dependabot opens pull requests rather than modifying `main` directly, so every proposed dependency update still passes through the same CI pipeline.

## Useful local equivalents

Before pushing, the closest local checks are:

```powershell
python -m pytest -q
python -m flask --app run db current
docker compose config
docker compose build web
```

The GitHub workflow adds a stronger fresh-PostgreSQL migration check and a clean Linux runner environment.

## Phase 7 progression

```text
7A  PostgreSQL + Alembic                    complete
7B  Docker + Gunicorn + environment config complete
7C  Redis + Celery + Celery Beat           complete
7D  GitHub Actions CI/CD                    complete
7E  Logging + health + observability        next
7F  Production deployment                   later
```
