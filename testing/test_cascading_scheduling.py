# testing/test_cascading_scheduling.py
"""
Tests for Cascading Job Size Scheduling feature.

Tests verify:
- New jobs never schedule on Friday
- Reschedules may land on Friday (if supported)
- 8h jobs prefer 8:00 starts and don't get blocked by earlier small jobs when an alternative exists
- 4h jobs fill clean 4h blocks
- Small jobs prefer gaps but do not destroy future large/medium feasibility when avoidable
- Regression tests for grace period + weather window + 8–8 boundaries
"""

import os
import pytest
from unittest.mock import patch
from datetime import datetime, timedelta

# Set required environment variables before importing
os.environ.setdefault("JOBBER_CLIENT_ID", "test_client_id")
os.environ.setdefault("JOBBER_CLIENT_SECRET", "test_secret")
os.environ.setdefault("JOBBER_API_BASE", "https://api.getjobber.com/api")
os.environ.setdefault("TEST_MODE", "True")
os.environ.setdefault("OPENWEATHER_API_KEY", "test_key")

from src.api.scheduler import (
    auto_book, 
    is_workday, 
    categorize_job_size, 
    JobSize,
    WORK_START, 
    WORK_END
)
from src.db import init_db, clear_visits, clear_processed_quotes


@pytest.fixture(autouse=True)
def clean_database():
    """Clean database before each test to ensure isolation."""
    init_db()
    clear_visits()
    clear_processed_quotes()
    yield
    clear_visits()
    clear_processed_quotes()


def test_job_size_categorization():
    """Test that jobs are correctly categorized by size."""
    assert categorize_job_size(timedelta(hours=8)) == JobSize.LARGE
    assert categorize_job_size(timedelta(hours=10)) == JobSize.LARGE
    assert categorize_job_size(timedelta(hours=4)) == JobSize.MEDIUM
    assert categorize_job_size(timedelta(hours=6)) == JobSize.MEDIUM
    assert categorize_job_size(timedelta(hours=3.5)) == JobSize.SMALL  # < 4 hours is SMALL
    assert categorize_job_size(timedelta(hours=2)) == JobSize.SMALL
    assert categorize_job_size(timedelta(hours=1)) == JobSize.SMALL
    assert categorize_job_size(timedelta(hours=3.9)) == JobSize.SMALL  # < 4 hours is SMALL


def test_friday_excluded_for_new_bookings():
    """Test that new bookings never schedule on Friday."""
    # Start from Thursday
    start_date = datetime(2025, 1, 16, 10, 0, 0)  # Thursday 10am
    duration = timedelta(hours=2)
    visits = []
    
    with patch("src.api.scheduler.check_weather_with_confidence") as mock_weather:
        mock_weather.return_value = {
            "suitable": True,
            "confidence": "high",
            "reason": "clear",
            "max_pop": 0.1,
            "severe_weather": False,
        }
        slot = auto_book(visits, start_date, duration, "Saskatoon", allow_friday=False)
    
    assert slot is not None, "Should find a slot"
    start_time = datetime.fromisoformat(slot["startAt"])
    
    # Should not be Friday (should be Thursday or next Monday)
    assert start_time.weekday() != 4, f"Slot {start_time} should not be on Friday"
    assert start_time.weekday() < 4, f"Slot {start_time} should be Mon-Thu"


def test_friday_allowed_for_reschedules():
    """Test that reschedules can land on Friday when allow_friday=True."""
    # Start from Thursday
    start_date = datetime(2025, 1, 16, 10, 0, 0)  # Thursday 10am
    duration = timedelta(hours=2)
    visits = []
    
    with patch("src.api.scheduler.check_weather_with_confidence") as mock_weather:
        mock_weather.return_value = {
            "suitable": True,
            "confidence": "high",
            "reason": "clear",
            "max_pop": 0.1,
            "severe_weather": False,
        }
        slot = auto_book(visits, start_date, duration, "Saskatoon", allow_friday=True)
    
    assert slot is not None, "Should find a slot"
    start_time = datetime.fromisoformat(slot["startAt"])
    
    # Should be able to schedule on Friday (weekday < 5)
    assert start_time.weekday() < 5, f"Slot {start_time} should be Mon-Fri when allow_friday=True"


def test_large_job_prefers_8am_start():
    """Test that 8h jobs prefer 8:00 AM starts on earliest available day."""
    start_date = datetime(2025, 1, 13, 8, 0, 0)  # Monday 8am
    duration = timedelta(hours=8)  # LARGE job
    visits = []
    
    with patch("src.api.scheduler.check_weather_with_confidence") as mock_weather:
        mock_weather.return_value = {
            "suitable": True,
            "confidence": "high",
            "reason": "clear",
            "max_pop": 0.1,
            "severe_weather": False,
        }
        slot = auto_book(visits, start_date, duration, "Saskatoon")
    
    assert slot is not None, "Should find a slot"
    start_time = datetime.fromisoformat(slot["startAt"])
    
    # Should start at 8:00 AM
    assert start_time.hour == WORK_START, f"Large job should start at 8am, got {start_time.hour}:{start_time.minute}"
    assert start_time.minute == 0, f"Large job should start at 8:00, got {start_time.hour}:{start_time.minute}"


def test_medium_job_prefers_block_aligned():
    """Test that 4h jobs prefer block-aligned half-day chunks."""
    start_date = datetime(2025, 1, 13, 8, 0, 0)  # Monday 8am
    duration = timedelta(hours=4)  # MEDIUM job
    visits = []
    
    with patch("src.api.scheduler.check_weather_with_confidence") as mock_weather:
        mock_weather.return_value = {
            "suitable": True,
            "confidence": "high",
            "reason": "clear",
            "max_pop": 0.1,
            "severe_weather": False,
        }
        slot = auto_book(visits, start_date, duration, "Saskatoon")
    
    assert slot is not None, "Should find a slot"
    start_time = datetime.fromisoformat(slot["startAt"])
    
    # Should prefer one of: 8:00, 12:30, or 16:00
    preferred_hours = [8, 12, 16]
    preferred_minutes = {8: 0, 12: 30, 16: 0}
    
    assert start_time.hour in preferred_hours, \
        f"Medium job should start at preferred hour (8, 12, or 16), got {start_time.hour}:{start_time.minute}"
    
    if start_time.hour in preferred_minutes:
        assert start_time.minute == preferred_minutes[start_time.hour], \
            f"Medium job at {start_time.hour} should start at {preferred_minutes[start_time.hour]} minutes"


def test_small_job_does_not_fragment_schedule():
    """Test that small jobs don't destroy future large/medium feasibility."""
    start_date = datetime(2025, 1, 13, 8, 0, 0)  # Monday 8am
    small_duration = timedelta(hours=2)  # SMALL job
    visits = []
    
    with patch("src.api.scheduler.check_weather_with_confidence") as mock_weather:
        mock_weather.return_value = {
            "suitable": True,
            "confidence": "high",
            "reason": "clear",
            "max_pop": 0.1,
            "severe_weather": False,
        }
        
        # Book a small job
        small_slot = auto_book(visits, start_date, small_duration, "Saskatoon")
        assert small_slot is not None, "Should find slot for small job"
        visits.append(small_slot)
        
        # Try to book a large job (8h) - should still be possible
        large_duration = timedelta(hours=8)
        large_slot = auto_book(visits, start_date, large_duration, "Saskatoon")
        
        # Large job should still be bookable (on same day or next day)
        assert large_slot is not None, \
            "Small job should not prevent large job from being scheduled"
        
        large_start = datetime.fromisoformat(large_slot["startAt"])
        # Should be able to place on same day (if small job doesn't block it) or next day
        assert large_start.weekday() < 4, "Large job should be on Mon-Thu"


def test_small_jobs_prefer_gaps():
    """Test that small jobs prefer existing gaps over creating new fragments."""
    start_date = datetime(2025, 1, 13, 8, 0, 0)  # Monday 8am
    
    # Create a schedule with a gap: 8-10am booked, 10am-2pm free, 2pm-4pm booked
    visits = [
        {
            "startAt": datetime(2025, 1, 13, 8, 0, 0).isoformat(),
            "endAt": datetime(2025, 1, 13, 10, 0, 0).isoformat(),
        },
        {
            "startAt": datetime(2025, 1, 13, 14, 0, 0).isoformat(),
            "endAt": datetime(2025, 1, 13, 16, 0, 0).isoformat(),
        },
    ]
    
    small_duration = timedelta(hours=2)  # SMALL job
    
    with patch("src.api.scheduler.check_weather_with_confidence") as mock_weather:
        mock_weather.return_value = {
            "suitable": True,
            "confidence": "high",
            "reason": "clear",
            "max_pop": 0.1,
            "severe_weather": False,
        }
        
        slot = auto_book(visits, start_date, small_duration, "Saskatoon")
    
    assert slot is not None, "Should find a slot"
    start_time = datetime.fromisoformat(slot["startAt"])
    
    # Should prefer the gap (10am-2pm) over creating a new fragment
    # The gap is 10:00-14:00, so a 2h job should fit there
    assert start_time.hour >= 10, f"Small job should prefer gap, got {start_time}"
    assert start_time.hour < 14, f"Small job should fit in gap, got {start_time}"


def test_grace_period_respected():
    """Test that 30-minute grace period is respected between jobs."""
    start_date = datetime(2025, 1, 13, 8, 0, 0)  # Monday 8am
    
    # Book a job from 8am-10am
    visits = [
        {
            "startAt": datetime(2025, 1, 13, 8, 0, 0).isoformat(),
            "endAt": datetime(2025, 1, 13, 10, 0, 0).isoformat(),
        },
    ]
    
    duration = timedelta(hours=2)
    
    with patch("src.api.scheduler.check_weather_with_confidence") as mock_weather:
        mock_weather.return_value = {
            "suitable": True,
            "confidence": "high",
            "reason": "clear",
            "max_pop": 0.1,
            "severe_weather": False,
        }
        
        slot = auto_book(visits, start_date, duration, "Saskatoon")
    
    assert slot is not None, "Should find a slot"
    start_time = datetime.fromisoformat(slot["startAt"])
    end_time = datetime.fromisoformat(slot["endAt"])
    
    # Next job should start at 10:30 (10:00 + 30min grace period)
    assert start_time >= datetime(2025, 1, 13, 10, 30, 0), \
        f"Next job should respect 30min grace period, got {start_time}"


def test_working_hours_boundaries():
    """Test that bookings respect 8am-8pm boundaries."""
    start_date = datetime(2025, 1, 13, 7, 0, 0)  # Monday 7am (before work hours)
    duration = timedelta(hours=2)
    visits = []
    
    with patch("src.api.scheduler.check_weather_with_confidence") as mock_weather:
        mock_weather.return_value = {
            "suitable": True,
            "confidence": "high",
            "reason": "clear",
            "max_pop": 0.1,
            "severe_weather": False,
        }
        
        slot = auto_book(visits, start_date, duration, "Saskatoon")
    
    assert slot is not None, "Should find a slot"
    start_time = datetime.fromisoformat(slot["startAt"])
    end_time = datetime.fromisoformat(slot["endAt"])
    
    # Should start at 8am or later
    assert start_time.hour >= WORK_START, f"Start time {start_time} should be >= 8am"
    # Should end before 8pm
    assert end_time.hour < WORK_END or (end_time.hour == WORK_END and end_time.minute == 0), \
        f"End time {end_time} should be <= 8pm"


def test_large_job_not_blocked_by_small_jobs():
    """Test that 8h jobs can still be placed even when small jobs exist, if alternative exists."""
    start_date = datetime(2025, 1, 13, 8, 0, 0)  # Monday 8am
    
    # Create schedule: small job 8-10am on Monday, but Tuesday is free
    visits = [
        {
            "startAt": datetime(2025, 1, 13, 8, 0, 0).isoformat(),
            "endAt": datetime(2025, 1, 13, 10, 0, 0).isoformat(),
        },
    ]
    
    large_duration = timedelta(hours=8)  # LARGE job
    
    with patch("src.api.scheduler.check_weather_with_confidence") as mock_weather:
        mock_weather.return_value = {
            "suitable": True,
            "confidence": "high",
            "reason": "clear",
            "max_pop": 0.1,
            "severe_weather": False,
        }
        
        slot = auto_book(visits, start_date, large_duration, "Saskatoon")
    
    assert slot is not None, "Large job should be bookable"
    start_time = datetime.fromisoformat(slot["startAt"])
    
    # Should prefer Tuesday at 8am (next available day) over fragmenting Monday
    # Or could be Monday if the small job doesn't block the full day
    assert start_time.weekday() < 4, "Large job should be on Mon-Thu"
    # If on Monday, should start after 10:30 (grace period)
    # If on Tuesday, should start at 8am
    if start_time.weekday() == 0:  # Monday
        assert start_time >= datetime(2025, 1, 13, 10, 30, 0), \
            "If on Monday, should start after grace period"
    elif start_time.weekday() == 1:  # Tuesday
        assert start_time.hour == WORK_START, \
            "If on Tuesday, should start at 8am"


def test_medium_job_fills_clean_blocks():
    """Test that 4h jobs fill clean 4h blocks when available."""
    start_date = datetime(2025, 1, 13, 8, 0, 0)  # Monday 8am
    medium_duration = timedelta(hours=4)  # MEDIUM job
    visits = []
    
    with patch("src.api.scheduler.check_weather_with_confidence") as mock_weather:
        mock_weather.return_value = {
            "suitable": True,
            "confidence": "high",
            "reason": "clear",
            "max_pop": 0.1,
            "severe_weather": False,
        }
        
        slot = auto_book(visits, start_date, medium_duration, "Saskatoon")
    
    assert slot is not None, "Should find a slot"
    start_time = datetime.fromisoformat(slot["startAt"])
    end_time = datetime.fromisoformat(slot["endAt"])
    
    # Should be a clean 4h block
    duration_hours = (end_time - start_time).total_seconds() / 3600
    assert abs(duration_hours - 4.0) < 0.1, \
        f"Medium job should be ~4 hours, got {duration_hours} hours"
    
    # Should prefer block-aligned start (8:00, 12:30, or 16:00)
    preferred_starts = [(8, 0), (12, 30), (16, 0)]
    start_tuple = (start_time.hour, start_time.minute)
    assert start_tuple in preferred_starts, \
        f"Medium job should start at preferred time, got {start_time.hour}:{start_time.minute}"


def test_multiple_job_sizes_cascade_correctly():
    """Test that multiple jobs of different sizes are scheduled optimally."""
    start_date = datetime(2025, 1, 13, 8, 0, 0)  # Monday 8am
    visits = []
    
    with patch("src.api.scheduler.check_weather_with_confidence") as mock_weather:
        mock_weather.return_value = {
            "suitable": True,
            "confidence": "high",
            "reason": "clear",
            "max_pop": 0.1,
            "severe_weather": False,
        }
        
        # Book a large job (8h)
        large_slot = auto_book(visits, start_date, timedelta(hours=8), "Saskatoon")
        assert large_slot is not None
        visits.append(large_slot)
        
        # Book a medium job (4h) - should go to next day
        medium_slot = auto_book(visits, start_date, timedelta(hours=4), "Saskatoon")
        assert medium_slot is not None
        visits.append(medium_slot)
        
        # Book a small job (2h) - should fill gaps
        small_slot = auto_book(visits, start_date, timedelta(hours=2), "Saskatoon")
        assert small_slot is not None
    
    # Verify all jobs are on Mon-Thu
    for slot in [large_slot, medium_slot, small_slot]:
        start_time = datetime.fromisoformat(slot["startAt"])
        assert start_time.weekday() < 4, f"Job should be on Mon-Thu, got {start_time}"

