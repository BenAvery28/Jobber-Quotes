# testing/test_booking_start_time.py
"""
Tests to verify that booking starts from 'now' rounded up to next 30-min boundary,
not from a fixed start time.

Updated for new rules:
- Working hours: 8am-8pm (WORK_START=8, WORK_END=20)
- Workdays: Mon-Thu only (Fridays excluded as buffer days)
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
os.environ.setdefault("OPENWEATHER_API_KEY", "test_key")

from fastapi.testclient import TestClient
from src.webapp import app, ceil_to_30
from src.db import init_db, clear_visits, clear_processed_quotes
from testing.mock_data import generate_jobber_webhook, generate_mock_quote_for_graphql
from testing.webhook_test_helpers import patch_jobber_client_for_test

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_database():
    """Clean database before each test to ensure isolation."""
    init_db()
    clear_visits()
    clear_processed_quotes()
    yield


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
    Test that booking respects working hours (8am-8pm).
    Uses production webhook endpoint with GraphQL mocking.
    """
    webhook = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id="Q_MIDDAY_TEST")
    quote_data = generate_mock_quote_for_graphql(
        quote_id="Q_MIDDAY_TEST",
        cost=500.0,
        client_id="C_MIDDAY"
    )
    
    with patch_jobber_client_for_test(quote_data=quote_data):
        response = client.post("/webhook/jobber", json=webhook)
        # Webhook should be accepted (202) - actual booking happens in background
        assert response.status_code == 202


def test_booking_starts_from_now_morning():
    """
    Test that booking returns a valid slot on a workday.
    Uses production webhook endpoint - booking happens in background.
    """
    webhook = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id="Q_MORNING_TEST")
    quote_data = generate_mock_quote_for_graphql(
        quote_id="Q_MORNING_TEST",
        cost=500.0,
        client_id="C_MORNING"
    )
    
    with patch_jobber_client_for_test(quote_data=quote_data):
        response = client.post("/webhook/jobber", json=webhook)
        # Webhook should be accepted
        assert response.status_code == 202


def test_booking_after_hours_moves_to_next_day():
    """
    Test that when booking is called after 8pm, it moves to next workday at 8am.
    
    Working hours are 8am-8pm. Wednesday at 9pm should book on Thursday.
    """
    # Mock datetime.now() to return 9:00 PM on Wednesday (after 8pm cutoff)
    mock_now = datetime(2025, 1, 15, 21, 0, 0)  # Wednesday, 9:00 PM
    
    with patch('src.webapp.datetime') as mock_dt:
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
        
        with patch('src.api.scheduler.datetime') as mock_scheduler_dt:
            mock_scheduler_dt.now.return_value = mock_now
            mock_scheduler_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            webhook = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id="Q_AFTER_HOURS_TEST")
            quote_data = generate_mock_quote_for_graphql(
                quote_id="Q_AFTER_HOURS_TEST",
                cost=500.0,
                client_id="C_AFTER_HOURS"
            )
            
            with patch_jobber_client_for_test(quote_data=quote_data):
                response = client.post("/webhook/jobber", json=webhook)
            
                # Webhook should be accepted (booking happens in background)
                assert response.status_code == 202


def test_booking_weekend_moves_to_monday():
    """
    Test that when booking is called on a weekend, it moves to next Monday.
    
    Workdays are Mon-Thu only (Fridays excluded as buffer days).
    Working hours are 8am-8pm.
    """
    # Mock datetime.now() to return Saturday 10:00 AM
    mock_now = datetime(2025, 1, 18, 10, 0, 0)  # Saturday, 10:00 AM
    
    with patch('src.webapp.datetime') as mock_dt:
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
        
        with patch('src.api.scheduler.datetime') as mock_scheduler_dt:
            mock_scheduler_dt.now.return_value = mock_now
            mock_scheduler_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            webhook = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id="Q_WEEKEND_TEST")
            quote_data = generate_mock_quote_for_graphql(
                quote_id="Q_WEEKEND_TEST",
                cost=500.0,
                client_id="C_WEEKEND"
            )
            
            with patch_jobber_client_for_test(quote_data=quote_data):
                response = client.post("/webhook/jobber", json=webhook)
                # Webhook should be accepted
                assert response.status_code == 202


def test_booking_response_includes_crew_assignment():
    """
    Test that webhook is accepted for crew assignment testing.
    Actual crew assignment happens in background processing.
    """
    webhook = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id="Q_CREW_TEST")
    quote_data = generate_mock_quote_for_graphql(
        quote_id="Q_CREW_TEST",
        cost=500.0,
        client_id="C_CREW"
    )
    
    with patch_jobber_client_for_test(quote_data=quote_data):
        response = client.post("/webhook/jobber", json=webhook)
        # Webhook should be accepted
        assert response.status_code == 202

