"""Post-deployment smoke verification for Medora HMS.

Usage:
    python scripts/verify_deployment.py https://medora-web.onrender.com
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
import uuid


def _get(base_url: str, path: str, request_id: str | None = None):
    headers = {"User-Agent": "medora-phase7f-verifier/1.0"}
    if request_id:
        headers["X-Request-ID"] = request_id
    req = urllib.request.Request(base_url.rstrip("/") + path, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, dict(response.headers), body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, dict(exc.headers), body


def _json(body: str):
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Expected JSON response, received: {body[:300]!r}") from exc


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/verify_deployment.py https://your-production-host")

    base_url = sys.argv[1].rstrip("/")
    if not base_url.startswith("https://"):
        raise SystemExit("Production verification requires an https:// URL.")

    print(f"[phase7f] Verifying {base_url}")

    status, _, body = _get(base_url, "/health/live")
    live = _json(body)
    if status != 200 or live.get("status") != "ok":
        raise SystemExit(f"Liveness failed: HTTP {status} {live}")
    print("[phase7f] liveness: PASS")

    status, _, body = _get(base_url, "/health/ready")
    ready = _json(body)
    if status != 200 or ready.get("status") != "ready":
        raise SystemExit(f"Readiness failed: HTTP {status} {ready}")
    dependencies = ready.get("dependencies", {})
    if not dependencies.get("database", {}).get("ok"):
        raise SystemExit(f"Database readiness failed: {ready}")
    if not dependencies.get("redis", {}).get("ok"):
        raise SystemExit(f"Key Value readiness failed: {ready}")
    print("[phase7f] PostgreSQL + Key Value readiness: PASS")

    request_id = f"phase7f-{uuid.uuid4()}"
    status, headers, body = _get(base_url, "/health/live", request_id=request_id)
    returned = headers.get("X-Request-ID") or headers.get("x-request-id")
    if status != 200 or returned != request_id:
        raise SystemExit(
            f"Request correlation failed: expected {request_id!r}, got {returned!r}"
        )
    print("[phase7f] X-Request-ID correlation: PASS")

    status, _, _ = _get(base_url, "/metrics")
    if status not in (200, 404):
        raise SystemExit(f"Unexpected /metrics response: HTTP {status}")
    print(f"[phase7f] metrics exposure: {'enabled' if status == 200 else 'disabled'}")

    print("[phase7f] Production smoke verification: PASS")


if __name__ == "__main__":
    main()
