"""Time helpers.

System/audit timestamps are stored as naive UTC for compatibility with the
existing schema. Scheduled hospital appointment times remain local wall-clock
values and intentionally do not use this helper.
"""
from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return current UTC without tzinfo for legacy ``DateTime`` columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
