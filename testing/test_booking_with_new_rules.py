# testing/test_booking_with_new_rules.py
"""
Integration tests to verify booking respects new scheduling rules:
- 8am-8pm working hours
- No Friday bookings
- Holiday exclusion
"""

import os
import pytest
from datetime import datetime, timedelta

# Set required environment variables before importing
os.environ.setdefault("JOBBER_CLIENT_ID", "test_client_id")
os.environ.setdefault("JOBBER_CLIENT_SECRET", "test_secret")
os.environ.setdefault("JOBBER_API_BASE", "https://api.getjobber.com/api")
os.environ.setdefault("TEST_MODE", "True")

from src.api.scheduler import auto_book, is_workday, WORK_START, WORK_END, HOLIDAYS
from src.db import init_db, clear_visits, get_visits


@pytest.fixture
def clean_db():
    """Clear database before each test."""
    init_db()
    clear_visits()
    yield
    clear_visits()


def test_booking_respects_8am_8pm_hours(clean_db):
    """Test that bookings are scheduled within 8am-8pm window."""
    # Start from a Monday at 7am (before work hours)
    start_date = datetime(2025, 1, 13, 7, 0, 0)  # Monday 7am
    duration = timedelta(hours=2)
    visits = []
    
    slot = auto_book(visits, start_date, duration, "Saskatoon", "C_TEST")
    
    assert slot is not None, "Should find a slot"
    
    start_time = datetime.fromisoformat(slot["startAt"])
    end_time = datetime.fromisoformat(slot["endAt"])
    
    # Start should be at 8am or later
    assert start_time.hour >= WORK_START, f"Start time {start_time} should be >= 8am"
    # End should be before 8pm
    assert end_time.hour < WORK_END or (end_time.hour == WORK_END and end_time.minute == 0), \
        f"End time {end_time} should be <= 8pm"


def test_booking_skips_fridays(clean_db):
    """Test that bookings skip Fridays."""
    # Start from a Thursday
    start_date = datetime(2025, 1, 16, 10, 0, 0)  # Thursday 10am
    duration = timedelta(hours=2)
    visits = []
    
    slot = auto_book(visits, start_date, duration, "Saskatoon", "C_TEST")
    
    assert slot is not None, "Should find a slot"
    
    start_time = datetime.fromisoformat(slot["startAt"])
    
    # Should not be a Friday
    assert start_time.weekday() != 4, f"Slot {start_time} should not be on Friday"
    # Should be Monday-Thursday
    assert start_time.weekday() < 4, f"Slot {start_time} should be Mon-Thu"


def test_booking_skips_holidays(clean_db):
    """Test that bookings skip holidays."""
    # Add a test holiday
    original_holidays = HOLIDAYS.copy()
    test_holiday = "2025-01-15"  # Wednesday
    HOLIDAYS.append(test_holiday)
    
    try:
        # Start from the holiday itself - should skip to next workday (Thursday)
        start_date = datetime(2025, 1, 15, 10, 0, 0)  # Wednesday 10am (holiday)
        duration = timedelta(hours=2)
        visits = []
        
        slot = auto_book(visits, start_date, duration, "Saskatoon", "C_TEST")
        
        assert slot is not None, "Should find a slot"
        
        start_time = datetime.fromisoformat(slot["startAt"])
        
        # Should not be on the holiday (Wednesday)
        assert start_time.strftime("%Y-%m-%d") != test_holiday, \
            f"Slot {start_time} should not be on holiday {test_holiday}"
        # Should skip to Thursday
        assert start_time.weekday() == 3, f"Slot {start_time} should be Thursday (skipping holiday)"
    finally:
        HOLIDAYS.clear()
        HOLIDAYS.extend(original_holidays)


def test_booking_after_8pm_moves_to_next_day(clean_db):
    """Test that booking requests after 8pm move to next workday at 8am."""
    # Note: auto_book starts from the given date, so we need to pass next day
    # In webapp.py, the logic moves to next day before calling auto_book
    # Here we test that auto_book correctly skips Friday when starting from Friday
    start_date = datetime(2025, 1, 17, 8, 0, 0)  # Friday 8am (should be skipped)
    duration = timedelta(hours=2)
    visits = []
    
    slot = auto_book(visits, start_date, duration, "Saskatoon", "C_TEST")
    
    assert slot is not None, "Should find a slot"
    
    start_time = datetime.fromisoformat(slot["startAt"])
    
    # Should be next Monday at 8am (skipping Friday, Saturday, Sunday)
    assert start_time.weekday() == 0, f"Slot {start_time} should be Monday (next workday after Friday)"
    assert start_time.hour == WORK_START, f"Slot {start_time} should start at 8am"


def test_booking_sequence_respects_all_rules(clean_db):
    """Test that multiple bookings respect all rules."""
    visits = []
    duration = timedelta(hours=2)
    
    # Start from Monday
    start_date = datetime(2025, 1, 13, 8, 0, 0)  # Monday 8am
    
    # Book 5 jobs
    booked_slots = []
    for i in range(5):
        slot = auto_book(visits, start_date, duration, "Saskatoon", f"C_TEST_{i}")
        assert slot is not None, f"Should find slot {i+1}"
        
        start_time = datetime.fromisoformat(slot["startAt"])
        end_time = datetime.fromisoformat(slot["endAt"])
        
        # Verify rules
        assert start_time.weekday() < 4, f"Slot {i+1} should not be Friday"
        assert start_time.hour >= WORK_START, f"Slot {i+1} should start >= 8am"
        assert end_time.hour < WORK_END or (end_time.hour == WORK_END and end_time.minute == 0), \
            f"Slot {i+1} should end <= 8pm"
        
        # Add to visits for next iteration
        visits.append(slot)
        booked_slots.append(slot)
    
    # Verify no Friday bookings
    for slot in booked_slots:
        start_time = datetime.fromisoformat(slot["startAt"])
        assert start_time.weekday() != 4, "No slot should be on Friday"

