# testing/test_estimate_time.py
"""
Unit tests for estimate_time() function to verify the 8-hour day fix.
"""

import os
import pytest
from datetime import timedelta

# Set required environment variables before importing
os.environ.setdefault("JOBBER_CLIENT_ID", "test_client_id")
os.environ.setdefault("JOBBER_CLIENT_SECRET", "test_secret")
os.environ.setdefault("TEST_MODE", "True")

from src.api.scheduler import estimate_time


def test_estimate_time_1440_full_day():
    """Test that $1440 corresponds to 8 hours, not 24."""
    duration = estimate_time(1440)
    assert duration != -1, "Should not return -1 for valid cost"
    assert duration == timedelta(hours=8), f"Expected 8 hours, got {duration.total_seconds() / 3600} hours"


def test_estimate_time_720_half_day():
    """Test that $720 corresponds to 4 hours."""
    duration = estimate_time(720)
    assert duration != -1, "Should not return -1 for valid cost"
    assert duration == timedelta(hours=4), f"Expected 4 hours, got {duration.total_seconds() / 3600} hours"


def test_estimate_time_180_one_hour():
    """Test that $180 corresponds to 1 hour."""
    duration = estimate_time(180)
    assert duration != -1, "Should not return -1 for valid cost"
    assert duration == timedelta(hours=1), f"Expected 1 hour, got {duration.total_seconds() / 3600} hours"


def test_estimate_time_1620_nine_hours():
    """Test that $1620 (8 + 1) corresponds to 9 hours."""
    duration = estimate_time(1620)
    assert duration != -1, "Should not return -1 for valid cost"
    assert duration == timedelta(hours=9), f"Expected 9 hours, got {duration.total_seconds() / 3600} hours"


def test_estimate_time_multiple_days():
    """Test multiple full days calculation."""
    # 2 full days = 2880 = 16 hours (2 * 8)
    duration = estimate_time(2880)
    assert duration != -1, "Should not return -1 for valid cost"
    assert duration == timedelta(hours=16), f"Expected 16 hours, got {duration.total_seconds() / 3600} hours"


def test_estimate_time_combined():
    """Test combined calculation: 1 day + 1 half day + 1 hour = 13 hours."""
    # 1440 (8h) + 720 (4h) + 180 (1h) = 2340 = 13 hours
    duration = estimate_time(2340)
    assert duration != -1, "Should not return -1 for valid cost"
    assert duration == timedelta(hours=13), f"Expected 13 hours, got {duration.total_seconds() / 3600} hours"


def test_estimate_time_invalid():
    """Test that invalid costs return -1."""
    assert estimate_time(0) == -1
    assert estimate_time(-100) == -1

