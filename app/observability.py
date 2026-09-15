"""Phase 7E observability primitives for Medora HMS.

The module intentionally keeps the runtime dependency surface small: structured
logging, request correlation, health probes, and lightweight Prometheus-style
metrics are implemented with Flask/SQLAlchemy/Redis plus the Python standard
library already present in the application.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import logging
import os
import re
import threading
import time
import uuid

from flask import Response, g, jsonify, request
from sqlalchemy import text

from app import db


_STARTED_AT = time.monotonic()
_METRICS_LOCK = threading.Lock()
_REQUESTS = Counter()
_REQUEST_DURATION_SECONDS = 0.0
_REQUEST_DURATION_COUNT = 0
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line for container/log-platform ingestion."""

    _standard = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": getattr(record, "service", os.environ.get("HMS_SERVICE_NAME", "web")),
        }
        for key, value in record.__dict__.items():
            if key not in self._standard and key not in {"message", "asctime"}:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, separators=(",", ":"))


def _log_level() -> int:
    name = os.environ.get("HMS_LOG_LEVEL", "INFO").upper().strip()
    return getattr(logging, name, logging.INFO)


def configure_logging(app=None, *, service_name: str | None = None) -> None:
    """Configure stdout logging once for Flask/Gunicorn/Celery processes."""
    service = service_name or os.environ.get("HMS_SERVICE_NAME", "web")
    log_format = os.environ.get("HMS_LOG_FORMAT", "json").lower().strip()

    handler = logging.StreamHandler()
    handler.setLevel(_log_level())
    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))

    root = logging.getLogger()
    root.setLevel(_log_level())
    root.handlers[:] = [handler]

    if app is not None:
        app.logger.handlers.clear()
        app.logger.propagate = True
        app.logger.setLevel(_log_level())
        app.logger.info(
            "observability initialized",
            extra={"event": "observability.init", "service": service},
        )


def _request_id() -> str:
    supplied = request.headers.get("X-Request-ID", "").strip()
    if supplied and _REQUEST_ID_RE.fullmatch(supplied):
        return supplied
    return str(uuid.uuid4())


def _redis_check() -> tuple[bool, float]:
    started = time.perf_counter()
    try:
        import redis

        url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
        client = redis.Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
        ok = bool(client.ping())
    except Exception:
        ok = False
    return ok, round((time.perf_counter() - started) * 1000, 2)


def _database_check() -> tuple[bool, float]:
    started = time.perf_counter()
    try:
        db.session.execute(text("SELECT 1"))
        ok = True
    except Exception:
        db.session.rollback()
        ok = False
    return ok, round((time.perf_counter() - started) * 1000, 2)


def _dependency_status() -> tuple[dict, bool]:
    db_ok, db_ms = _database_check()
    require_redis = os.environ.get("HMS_HEALTH_REQUIRE_REDIS", "1").strip().lower() in {
        "1", "true", "yes", "on"
    }
    redis_ok, redis_ms = _redis_check()
    healthy = db_ok and (redis_ok or not require_redis)
    return {
        "database": {"ok": db_ok, "latency_ms": db_ms},
        "redis": {"ok": redis_ok, "latency_ms": redis_ms, "required": require_redis},
    }, healthy


def _metrics_text() -> str:
    dependencies, _ = _dependency_status()
    with _METRICS_LOCK:
        rows = [
            "# HELP hms_process_uptime_seconds Process uptime in seconds.",
            "# TYPE hms_process_uptime_seconds gauge",
            f"hms_process_uptime_seconds {time.monotonic() - _STARTED_AT:.3f}",
            "# HELP hms_http_requests_total HTTP requests handled by this process.",
            "# TYPE hms_http_requests_total counter",
        ]
        for (method, status), count in sorted(_REQUESTS.items()):
            rows.append(f'hms_http_requests_total{{method="{method}",status="{status}"}} {count}')
        rows.extend(
            [
                "# HELP hms_http_request_duration_seconds_sum Total HTTP request duration.",
                "# TYPE hms_http_request_duration_seconds_sum counter",
                f"hms_http_request_duration_seconds_sum {_REQUEST_DURATION_SECONDS:.6f}",
                "# HELP hms_http_request_duration_seconds_count Number of timed HTTP requests.",
                "# TYPE hms_http_request_duration_seconds_count counter",
                f"hms_http_request_duration_seconds_count {_REQUEST_DURATION_COUNT}",
                "# HELP hms_dependency_up Dependency health (1=up, 0=down).",
                "# TYPE hms_dependency_up gauge",
                f'hms_dependency_up{{dependency="database"}} {1 if dependencies["database"]["ok"] else 0}',
                f'hms_dependency_up{{dependency="redis"}} {1 if dependencies["redis"]["ok"] else 0}',
            ]
        )
    return "\n".join(rows) + "\n"


def init_observability(app) -> None:
    """Attach health endpoints, correlation IDs, access logs, and metrics."""
    if app.extensions.get("hms_observability"):
        return
    app.extensions["hms_observability"] = True
    configure_logging(app, service_name=os.environ.get("HMS_SERVICE_NAME", "web"))

    @app.before_request
    def observability_before_request():
        g.request_id = _request_id()
        g.request_started_at = time.perf_counter()

    @app.after_request
    def observability_after_request(response):
        global _REQUEST_DURATION_SECONDS, _REQUEST_DURATION_COUNT

        request_id = getattr(g, "request_id", str(uuid.uuid4()))
        response.headers["X-Request-ID"] = request_id
        started = getattr(g, "request_started_at", time.perf_counter())
        duration = max(0.0, time.perf_counter() - started)

        with _METRICS_LOCK:
            _REQUESTS[(request.method, str(response.status_code))] += 1
            _REQUEST_DURATION_SECONDS += duration
            _REQUEST_DURATION_COUNT += 1

        log_health = os.environ.get("HMS_LOG_HEALTH_REQUESTS", "0") == "1"
        if log_health or request.path not in {"/health", "/health/live", "/health/ready", "/metrics"}:
            app.logger.info(
                "http request completed",
                extra={
                    "event": "http.request",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.path,
                    "status": response.status_code,
                    "duration_ms": round(duration * 1000, 2),
                },
            )
        return response

    @app.get("/health/live")
    def health_live():
        return jsonify(
            status="ok",
            service="medora-hms",
            uptime_seconds=round(time.monotonic() - _STARTED_AT, 3),
        )

    @app.get("/health/ready")
    def health_ready():
        dependencies, healthy = _dependency_status()
        payload = {
            "status": "ready" if healthy else "not_ready",
            "service": "medora-hms",
            "dependencies": dependencies,
        }
        return jsonify(payload), 200 if healthy else 503

    @app.get("/health")
    def health_summary():
        return health_ready()

    @app.get("/metrics")
    def metrics():
        if os.environ.get("HMS_METRICS_ENABLED", "1") != "1":
            return Response("metrics disabled\n", status=404, mimetype="text/plain")
        return Response(_metrics_text(), mimetype="text/plain; version=0.0.4; charset=utf-8")
