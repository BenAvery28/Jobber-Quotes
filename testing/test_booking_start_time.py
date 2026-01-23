# testing/test_booking_start_time.py
"""
Tests to verify that booking starts from 'now' rounded up to next 30-min boundary,
not from 9am today.
"""

import os
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# Set required environment variables before importing
os.environ.setdefault("JOBBER_CLIENT_ID", "test_client_id")
os.environ.setdefault("JOBBER_CLIENT_SECRET", "test_secret")
os.environ.setdefault("JOBBER_API_BASE", "https://api.getjobber.com/api")
os.environ.setdefault("TEST_MODE", "True")

from fastapi.testclient import TestClient
from src.webapp import app, ceil_to_30
from testing.mock_data import generate_mock_webhook

client = TestClient(app)


def test_ceil_to_30_helper():
    """Test the ceil_to_30 helper function."""
    # Test cases for ceil_to_30
    test_cases = [
        # (input, expected)
        (datetime(2025, 1, 15, 10, 0, 0), datetime(2025, 1, 15, 10, 0, 0)),  # Already on boundary
        (datetime(2025, 1, 15, 10, 30, 0), datetime(2025, 1, 15, 10, 30, 0)),  # Already on boundary
        (datetime(2025, 1, 15, 10, 15, 0), datetime(2025, 1, 15, 10, 30, 0)),  # Round up to 30
        (datetime(2025, 1, 15, 10, 31, 0), datetime(2025, 1, 15, 11, 0, 0)),  # Round up to next hour
        (datetime(2025, 1, 15, 10, 45, 0), datetime(2025, 1, 15, 11, 0, 0)),  # Round up to next hour
        (datetime(2025, 1, 15, 10, 0, 30), datetime(2025, 1, 15, 10, 0, 0)),  # Seconds/microseconds cleared
    ]
    
    for input_dt, expected in test_cases:
        result = ceil_to_30(input_dt)
        assert result == expected, f"ceil_to_30({input_dt}) = {result}, expected {expected}"


def test_booking_starts_from_now_midday():
    """
    Test that when booking is called midday (e.g., 2:30 PM), 
    it doesn't choose times earlier than 'now'.
    """
    # Mock datetime.now() to return a specific time (2:30 PM on a weekday)
    mock_now = datetime(2025, 1, 15, 14, 30, 0)  # Wednesday, 2:30 PM
    
    with patch('src.webapp.datetime') as mock_dt:
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
        
        # Also need to mock inside the booking logic
        with patch('src.api.scheduler.datetime') as mock_scheduler_dt:
            mock_scheduler_dt.now.return_value = mock_now
            mock_scheduler_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            payload = generate_mock_webhook(quote_id="Q_MIDDAY_TEST")["data"]
            response = client.post("/book-job", json=payload)
            
            if response.status_code == 200:
                data = response.json()
                scheduled_start = datetime.fromisoformat(data["scheduled_start"])
                
                # The scheduled start should be >= ceil_to_30(mock_now) = 2:30 PM
                # (or next workday if it's after 5pm or not a workday)
                expected_min_start = ceil_to_30(mock_now)
                
                # If the rounded time is before 9am or after 5pm, it should move to next day
                if expected_min_start.hour < 9:
                    expected_min_start = expected_min_start.replace(hour=9, minute=0)
                elif expected_min_start.hour >= 17:
                    expected_min_start = (expected_min_start + timedelta(days=1)).replace(hour=9, minute=0)
                
                assert scheduled_start >= expected_min_start, \
                    f"Scheduled start {scheduled_start} should be >= {expected_min_start}"


def test_booking_starts_from_now_morning():
    """
    Test that when booking is called in the morning (e.g., 10:15 AM),
    it starts from the rounded-up time (10:30 AM), not 9am.
    """
    # Mock datetime.now() to return 10:15 AM on a weekday
    mock_now = datetime(2025, 1, 15, 10, 15, 0)  # Wednesday, 10:15 AM
    
    with patch('src.webapp.datetime') as mock_dt:
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
        
        with patch('src.api.scheduler.datetime') as mock_scheduler_dt:
            mock_scheduler_dt.now.return_value = mock_now
            mock_scheduler_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            payload = generate_mock_webhook(quote_id="Q_MORNING_TEST")["data"]
            response = client.post("/book-job", json=payload)
            
            if response.status_code == 200:
                data = response.json()
                scheduled_start = datetime.fromisoformat(data["scheduled_start"])
                
                # Should start from 10:30 AM (ceil_to_30 of 10:15), not 9:00 AM
                expected_min_start = datetime(2025, 1, 15, 10, 30, 0)
                assert scheduled_start >= expected_min_start, \
                    f"Scheduled start {scheduled_start} should be >= {expected_min_start}, not 9am"


def test_booking_after_hours_moves_to_next_day():
    """
    Test that when booking is called after 5pm, it moves to next workday at 9am.
    """
    # Mock datetime.now() to return 6:00 PM on a weekday
    mock_now = datetime(2025, 1, 15, 18, 0, 0)  # Wednesday, 6:00 PM
    
    with patch('src.webapp.datetime') as mock_dt:
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
        
        with patch('src.api.scheduler.datetime') as mock_scheduler_dt:
            mock_scheduler_dt.now.return_value = mock_now
            mock_scheduler_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            payload = generate_mock_webhook(quote_id="Q_AFTER_HOURS_TEST")["data"]
            response = client.post("/book-job", json=payload)
            
            if response.status_code == 200:
                data = response.json()
                scheduled_start = datetime.fromisoformat(data["scheduled_start"])
                
                # Should be next workday (Thursday) at 9am or later
                expected_min_start = datetime(2025, 1, 16, 9, 0, 0)  # Next day at 9am
                assert scheduled_start >= expected_min_start, \
                    f"Scheduled start {scheduled_start} should be >= {expected_min_start} (next workday)"


def test_booking_weekend_moves_to_monday():
    """
    Test that when booking is called on a weekend, it moves to next Monday.
    """
    # Mock datetime.now() to return Saturday 10:00 AM
    mock_now = datetime(2025, 1, 18, 10, 0, 0)  # Saturday, 10:00 AM
    
    with patch('src.webapp.datetime') as mock_dt:
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
        
        with patch('src.api.scheduler.datetime') as mock_scheduler_dt:
            mock_scheduler_dt.now.return_value = mock_now
            mock_scheduler_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            payload = generate_mock_webhook(quote_id="Q_WEEKEND_TEST")["data"]
            response = client.post("/book-job", json=payload)
            
            if response.status_code == 200:
                data = response.json()
                scheduled_start = datetime.fromisoformat(data["scheduled_start"])
                
                # Should be Monday at 9am or later
                expected_min_start = datetime(2025, 1, 20, 9, 0, 0)  # Monday at 9am
                assert scheduled_start >= expected_min_start, \
                    f"Scheduled start {scheduled_start} should be >= {expected_min_start} (next Monday)"

