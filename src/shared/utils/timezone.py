"""Timezone utilities for AShareInsight.

This module provides timezone constants and helper functions for working with
China timezone (Asia/Shanghai).
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

# China timezone (UTC+8)
CHINA_TZ = ZoneInfo("Asia/Shanghai")

# UTC timezone for compatibility
UTC_TZ = UTC


def now_china() -> datetime:
    """Get current datetime in China timezone.

    Returns:
        Current datetime with China timezone (Asia/Shanghai).
    """
    return datetime.now(CHINA_TZ)


def now_utc() -> datetime:
    """Get current datetime in UTC timezone.

    Returns:
        Current datetime with UTC timezone.
    """
    return datetime.now(UTC_TZ)


def to_china_tz(dt: datetime | None) -> datetime | None:
    """Convert datetime to China timezone.

    Args:
        dt: Datetime object (timezone-aware or naive) or None.

    Returns:
        Datetime in China timezone or None if input is None.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Assume naive datetime is in China timezone
        return dt.replace(tzinfo=CHINA_TZ)
    return dt.astimezone(CHINA_TZ)


def to_utc(dt: datetime) -> datetime:
    """Convert datetime to UTC timezone.

    Args:
        dt: Datetime object (timezone-aware or naive).

    Returns:
        Datetime in UTC timezone.
    """
    if dt.tzinfo is None:
        # Assume naive datetime is in China timezone
        dt = dt.replace(tzinfo=CHINA_TZ)
    return dt.astimezone(UTC_TZ)
