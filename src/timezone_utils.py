# src/timezone_utils.py
#
# Timezone utilities for consistent datetime handling

from datetime import datetime, timezone, timedelta
from typing import Optional
import os

# Default timezone (Saskatoon, SK is UTC-6 in standard time, UTC-5 in daylight time)
# Using America/Regina which is the same timezone as Saskatoon
DEFAULT_TIMEZONE = os.getenv("APP_TIMEZONE", "America/Regina")

try:
    import pytz
    HAS_PYTZ = True
    _tz = pytz.timezone(DEFAULT_TIMEZONE)
except ImportError:
    HAS_PYTZ = False
    _tz = None
    import warnings
    warnings.warn("pytz not installed, using UTC for timezone operations. Install pytz for proper timezone support.")


def now() -> datetime:
    """
    Get current timezone-aware datetime.
    Returns UTC if pytz is not available.
    """
    if HAS_PYTZ and _tz:
        return datetime.now(_tz)
    return datetime.now(timezone.utc)


def to_utc(dt: datetime) -> datetime:
    """
    Convert a datetime to UTC.
    If datetime is naive, assumes it's in the default timezone.
    """
    if dt.tzinfo is None:
        # Naive datetime - assume it's in default timezone
        if HAS_PYTZ and _tz:
            dt = _tz.localize(dt)
        else:
            # No timezone info available, assume UTC
            dt = dt.replace(tzinfo=timezone.utc)
    
    return dt.astimezone(timezone.utc)


def from_utc(dt: datetime) -> datetime:
    """
    Convert a UTC datetime to the default timezone.
    """
    if dt.tzinfo is None:
        # Assume naive datetime is UTC
        dt = dt.replace(tzinfo=timezone.utc)
    
    if HAS_PYTZ and _tz:
        return dt.astimezone(_tz)
    return dt.astimezone(timezone.utc)


def make_aware(dt: datetime, tz: Optional[str] = None) -> datetime:
    """
    Make a naive datetime timezone-aware.
    
    Args:
        dt: Naive datetime
        tz: Timezone name (default: DEFAULT_TIMEZONE)
    
    Returns:
        Timezone-aware datetime
    """
    if dt.tzinfo is not None:
        return dt
    
    tz_name = tz or DEFAULT_TIMEZONE
    
    if HAS_PYTZ:
        tz_obj = pytz.timezone(tz_name)
        return tz_obj.localize(dt)
    
    # Fallback: assume UTC
    return dt.replace(tzinfo=timezone.utc)


def parse_iso_with_tz(iso_string: str) -> datetime:
    """
    Parse ISO format string and ensure timezone awareness.
    If no timezone info, assumes UTC.
    """
    try:
        dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        # Fallback: try parsing without timezone
        dt = datetime.fromisoformat(iso_string)
        return make_aware(dt)

