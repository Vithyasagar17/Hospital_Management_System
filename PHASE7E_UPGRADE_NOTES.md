# Phase 7E — Logging, Health Checks & Observability

Phase 7E adds operational visibility without introducing a third-party monitoring platform yet. The application now emits structured logs, correlates every HTTP request, exposes liveness/readiness probes, and provides lightweight Prometheus-style process metrics.

## Added

- JSON structured logging to stdout for container/log-platform ingestion.
- Configurable log level and text-vs-JSON format.
- `X-Request-ID` correlation for incoming/outgoing HTTP requests.
- Per-request method/path/status/duration logs without logging form bodies, passwords, tokens, or query values.
- `/health/live` liveness probe that does not depend on PostgreSQL or Redis.
- `/health/ready` readiness probe that verifies PostgreSQL and, by default, Redis.
- `/health` readiness alias for operators/platforms with a single health URL.
- `/metrics` lightweight Prometheus-text endpoint with process HTTP counters/durations and dependency gauges.
- Docker web healthcheck moved from `/login` to `/health/live`.
- Structured logging initialization for Celery workers.
- Regression tests for probes, request IDs, and metrics.

## Endpoints

```text
GET /health/live
GET /health/ready
GET /health
GET /metrics
```

`/health/live` answers whether the web process is alive. It intentionally avoids database/network checks so a temporary dependency outage does not make the orchestrator repeatedly kill an otherwise healthy process.

`/health/ready` checks dependencies and returns `503` while the application should not receive traffic. PostgreSQL is always required. Redis can be made optional with:

```text
HMS_HEALTH_REQUIRE_REDIS=0
```

The default Docker configuration requires Redis because Phase 7C background processing is part of the deployed stack.

## Logging configuration

`.env` options:

```text
HMS_LOG_FORMAT=json
HMS_LOG_LEVEL=INFO
HMS_LOG_HEALTH_REQUESTS=0
```

Typical request log:

```json
{"timestamp":"...Z","level":"INFO","logger":"app","message":"http request completed","service":"web","event":"http.request","request_id":"...","method":"GET","path":"/patient/dashboard","status":200,"duration_ms":18.41}
```

Health/metrics request logs are suppressed by default to avoid probe noise. Enable them with `HMS_LOG_HEALTH_REQUESTS=1`.

Sensitive request bodies, passwords, cookies, bearer tokens, and query-string values are never included in the access log payload.

## Request correlation

Clients/reverse proxies may send:

```text
X-Request-ID: checkout-1234
```

Safe IDs are preserved; missing/invalid IDs are replaced with UUIDs. Every response includes the effective `X-Request-ID`, allowing a reported browser/API error to be correlated with server logs.

## Metrics

Metrics are enabled by default:

```text
HMS_METRICS_ENABLED=1
```

Example:

```text
hms_process_uptime_seconds 123.400
hms_http_requests_total{method="GET",status="200"} 42
hms_http_request_duration_seconds_sum 1.920000
hms_http_request_duration_seconds_count 42
hms_dependency_up{dependency="database"} 1
hms_dependency_up{dependency="redis"} 1
```

These counters are intentionally process-local. With multiple Gunicorn workers, `/metrics` reflects whichever worker serves the scrape. Phase 7F can wire the app to a real monitoring platform or a Prometheus multiprocess collector if deployment requirements justify it.

Disable metrics if they should not be externally exposed:

```text
HMS_METRICS_ENABLED=0
```

In production, prefer exposing `/metrics` only to an internal monitoring network/reverse-proxy route rather than the public Internet.

## Docker verification

Rebuild because application files changed:

```powershell
docker compose down
docker compose up --build -d
docker compose ps
```

Liveness:

```powershell
Invoke-RestMethod http://localhost:8000/health/live
```

Readiness:

```powershell
Invoke-RestMethod http://localhost:8000/health/ready
```

Metrics:

```powershell
Invoke-WebRequest http://localhost:8000/metrics | Select-Object -ExpandProperty Content
```

Request ID:

```powershell
$response = Invoke-WebRequest http://localhost:8000/health/live -Headers @{ 'X-Request-ID'='phase7e-test' }
$response.Headers['X-Request-ID']
```

Web logs:

```powershell
docker compose logs -f web
```

Worker logs:

```powershell
docker compose logs -f worker
```

## Failure interpretation

```text
/health/live = 200, /health/ready = 503
```

means the Flask/Gunicorn process itself is alive but PostgreSQL or required Redis is unavailable. Investigate dependencies rather than continuously restarting the web process.

```text
/health/live = unavailable
```

means the web process/container itself is not serving HTTP and should be restarted/investigated.
