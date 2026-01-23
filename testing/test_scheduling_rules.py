# testing/test_scheduling_rules.py
"""
Tests for scheduling rules: holidays, working hours (8am-8pm), and Friday exclusion.
"""

import os
import pytest
from datetime import datetime, timedelta

# Set required environment variables before importing
os.environ.setdefault("JOBBER_CLIENT_ID", "test_client_id")
os.environ.setdefault("JOBBER_CLIENT_SECRET", "test_secret")
os.environ.setdefault("JOBBER_API_BASE", "https://api.getjobber.com/api")
os.environ.setdefault("TEST_MODE", "True")

from src.api.scheduler import is_workday, WORK_START, WORK_END, HOLIDAYS


def test_working_hours_constants():
    """Test that working hours are set to 8am-8pm."""
    assert WORK_START == 8, f"WORK_START should be 8 (8am), got {WORK_START}"
    assert WORK_END == 20, f"WORK_END should be 20 (8pm), got {WORK_END}"


def test_friday_exclusion():
    """Test that Fridays are excluded from booking."""
    # Test a Friday (2025-01-17 is a Friday)
    friday = datetime(2025, 1, 17)  # Friday
    assert friday.weekday() == 4, "Date should be a Friday"
    assert not is_workday(friday), "Friday should not be a workday"
    
    # Test another Friday
    friday2 = datetime(2025, 1, 24)  # Friday
    assert not is_workday(friday2), "Friday should not be a workday"


def test_weekend_exclusion():
    """Test that weekends are excluded from booking."""
    # Test Saturday (2025-01-18 is a Saturday)
    saturday = datetime(2025, 1, 18)  # Saturday
    assert saturday.weekday() == 5, "Date should be a Saturday"
    assert not is_workday(saturday), "Saturday should not be a workday"
    
    # Test Sunday (2025-01-19 is a Sunday)
    sunday = datetime(2025, 1, 19)  # Sunday
    assert sunday.weekday() == 6, "Date should be a Sunday"
    assert not is_workday(sunday), "Sunday should not be a workday"


def test_monday_through_thursday_allowed():
    """Test that Monday through Thursday are allowed."""
    # Test Monday (2025-01-13 is a Monday)
    monday = datetime(2025, 1, 13)  # Monday
    assert monday.weekday() == 0, "Date should be a Monday"
    assert is_workday(monday), "Monday should be a workday"
    
    # Test Tuesday (2025-01-14 is a Tuesday)
    tuesday = datetime(2025, 1, 14)  # Tuesday
    assert tuesday.weekday() == 1, "Date should be a Tuesday"
    assert is_workday(tuesday), "Tuesday should be a workday"
    
    # Test Wednesday (2025-01-15 is a Wednesday)
    wednesday = datetime(2025, 1, 15)  # Wednesday
    assert wednesday.weekday() == 2, "Date should be a Wednesday"
    assert is_workday(wednesday), "Wednesday should be a workday"
    
    # Test Thursday (2025-01-16 is a Thursday)
    thursday = datetime(2025, 1, 16)  # Thursday
    assert thursday.weekday() == 3, "Date should be a Thursday"
    assert is_workday(thursday), "Thursday should be a workday"


def test_holidays_exclusion():
    """Test that holidays in the HOLIDAYS list are excluded."""
    # Add a test holiday
    test_holiday = "2025-12-25"  # Christmas
    
    # Temporarily add holiday to the list
    original_holidays = HOLIDAYS.copy()
    HOLIDAYS.append(test_holiday)
    
    try:
        holiday_date = datetime(2025, 12, 25)  # Thursday, but should be excluded as holiday
        assert holiday_date.weekday() < 4, "Date should be a weekday (Mon-Thu)"
        assert not is_workday(holiday_date), "Holiday should not be a workday even if it's a weekday"
    finally:
        # Restore original holidays list
        HOLIDAYS.clear()
        HOLIDAYS.extend(original_holidays)


def test_holiday_on_weekend():
    """Test that holidays on weekends don't affect weekday booking."""
    # Add a holiday that falls on a weekend
    weekend_holiday = "2025-01-18"  # Saturday
    
    original_holidays = HOLIDAYS.copy()
    HOLIDAYS.append(weekend_holiday)
    
    try:
        # Monday should still be bookable
        monday = datetime(2025, 1, 20)  # Monday
        assert is_workday(monday), "Monday should be bookable even if a weekend day is a holiday"
    finally:
        HOLIDAYS.clear()
        HOLIDAYS.extend(original_holidays)


def test_multiple_holidays():
    """Test that multiple holidays can be excluded."""
    original_holidays = HOLIDAYS.copy()
    
    # Add multiple holidays
    HOLIDAYS.extend([
        "2025-12-25",  # Christmas
        "2026-01-01",  # New Year's Day
        "2026-06-28",  # Example holiday from requirements
    ])
    
    try:
        # Test each holiday
        christmas = datetime(2025, 12, 25)
        new_year = datetime(2026, 1, 1)
        example_holiday = datetime(2026, 6, 28)
        
        assert not is_workday(christmas), "Christmas should not be a workday"
        assert not is_workday(new_year), "New Year's Day should not be a workday"
        assert not is_workday(example_holiday), "Example holiday should not be a workday"
        
        # Test a regular weekday between holidays
        regular_day = datetime(2025, 12, 23)  # Tuesday
        if regular_day.weekday() < 4:  # Only if it's Mon-Thu
            assert is_workday(regular_day), "Regular weekday should be bookable"
    finally:
        HOLIDAYS.clear()
        HOLIDAYS.extend(original_holidays)


def test_workday_sequence():
    """Test that workdays are correctly identified in a sequence."""
    # Test a week: Mon, Tue, Wed, Thu, Fri, Sat, Sun
    dates = [
        datetime(2025, 1, 13),  # Monday
        datetime(2025, 1, 14),  # Tuesday
        datetime(2025, 1, 15),  # Wednesday
        datetime(2025, 1, 16),  # Thursday
        datetime(2025, 1, 17),  # Friday
        datetime(2025, 1, 18),  # Saturday
        datetime(2025, 1, 19),  # Sunday
    ]
    
    expected = [True, True, True, True, False, False, False]
    
    for date, expected_result in zip(dates, expected):
        assert is_workday(date) == expected_result, \
            f"{date.strftime('%A %Y-%m-%d')} should be {expected_result}"


def test_holiday_format():
    """Test that holidays use YYYY-MM-DD format."""
    # Verify the format of holidays in the list
    for holiday in HOLIDAYS:
        # Try to parse as date to verify format
        try:
            datetime.strptime(holiday, "%Y-%m-%d")
        except ValueError:
            pytest.fail(f"Holiday '{holiday}' is not in YYYY-MM-DD format")

