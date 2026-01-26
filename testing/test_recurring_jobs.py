# testing/test_recurring_jobs.py
"""
Comprehensive tests for recurring jobs functionality.
"""

import os
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

# Set required environment variables before importing
os.environ.setdefault("JOBBER_CLIENT_ID", "test_client_id")
os.environ.setdefault("JOBBER_CLIENT_SECRET", "test_secret")
os.environ.setdefault("JOBBER_API_BASE", "https://api.getjobber.com/api")
os.environ.setdefault("TEST_MODE", "True")

from src.db import init_db, clear_visits, create_recurring_job, get_recurring_jobs, deactivate_recurring_job, get_visits
from src.api.recurring_jobs import generate_bookings_from_recurring_job, book_entire_summer


@pytest.fixture
def clean_db():
    """Clear database before each test."""
    init_db()
    clear_visits()
    # Also clear recurring jobs
    import sqlite3
    from src.db import DB_PATH
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM recurring_jobs")
        conn.commit()
    yield
    clear_visits()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM recurring_jobs")
        conn.commit()


def test_create_recurring_job(clean_db):
    """Test creating a recurring job template."""
    recurring_id = create_recurring_job(
        client_id="C_RECURRING",
        day_of_week=0,  # Monday
        start_time="10:00",
        duration_hours=2.0,
        start_date="2025-06-01",
        end_date="2025-08-31",
        job_tag="residential"
    )
    
    assert recurring_id > 0
    
    # Retrieve it
    recurring_jobs = get_recurring_jobs(client_id="C_RECURRING")
    assert len(recurring_jobs) == 1
    assert recurring_jobs[0]["day_of_week"] == 0
    assert recurring_jobs[0]["start_time"] == "10:00"
    assert recurring_jobs[0]["duration_hours"] == 2.0
    assert recurring_jobs[0]["is_active"] == True


def test_recurring_job_manual_time_selection(clean_db):
    """Test that recurring jobs support manual time/day selection."""
    # Create recurring job for Tuesday at 2pm
    recurring_id = create_recurring_job(
        client_id="C_TUESDAY",
        day_of_week=1,  # Tuesday
        start_time="14:00",  # 2pm
        duration_hours=3.0,
        start_date="2025-06-01",
        end_date="2025-08-31",
        job_tag="commercial"
    )
    
    recurring_jobs = get_recurring_jobs(client_id="C_TUESDAY")
    assert len(recurring_jobs) == 1
    assert recurring_jobs[0]["day_of_week"] == 1  # Tuesday
    assert recurring_jobs[0]["start_time"] == "14:00"
    assert recurring_jobs[0]["job_tag"] == "commercial"


def test_generate_bookings_from_recurring_job(clean_db):
    """Test generating individual bookings from a recurring job."""
    # Create recurring job for Mondays
    recurring_id = create_recurring_job(
        client_id="C_MONDAY",
        day_of_week=0,  # Monday
        start_time="10:00",
        duration_hours=2.0,
        start_date="2025-06-02",  # June 2, 2025 is a Monday
        end_date="2025-06-30",  # June 30, 2025
        job_tag="residential"
    )
    
    # Generate bookings (mock weather to always allow)
    with patch('src.api.recurring_jobs.check_weather_with_confidence') as mock_weather:
        mock_weather.return_value = {
            'suitable': True,
            'confidence': 'high',
            'reason': 'Clear weather',
            'max_pop': 0.1,
            'severe_weather': False
        }
        
        result = generate_bookings_from_recurring_job(
            recurring_id, city="Saskatoon", check_weather=True, skip_conflicts=True
        )
    
    # Should have booked multiple Mondays in June
    assert result['booked'] > 0
    assert result['total_dates'] > 0
    assert len(result['bookings']) == result['booked']
    
    # Verify bookings were created
    visits = get_visits()
    monday_bookings = [v for v in visits if v['client_id'] == 'C_MONDAY']
    assert len(monday_bookings) == result['booked']
    
    # Verify all bookings are on Mondays
    for booking in monday_bookings:
        start_time = datetime.fromisoformat(booking['startAt'])
        assert start_time.weekday() == 0  # Monday
        assert start_time.hour == 10
        assert start_time.minute == 0


def test_generate_bookings_skips_conflicts(clean_db):
    """Test that booking generation skips conflicting dates."""
    # Create an existing booking
    from src.db import add_visit
    add_visit("2025-06-09T10:00:00", "2025-06-09T12:00:00", "C_EXISTING", "residential")
    
    # Create recurring job for Mondays (June 9, 2025 is a Monday)
    recurring_id = create_recurring_job(
        client_id="C_MONDAY",
        day_of_week=0,
        start_time="10:00",
        duration_hours=2.0,
        start_date="2025-06-02",
        end_date="2025-06-30",
        job_tag="residential"
    )
    
    with patch('src.api.recurring_jobs.check_weather_with_confidence') as mock_weather:
        mock_weather.return_value = {
            'suitable': True,
            'confidence': 'high',
            'reason': 'Clear weather',
            'max_pop': 0.1,
            'severe_weather': False
        }
        
        result = generate_bookings_from_recurring_job(
            recurring_id, city="Saskatoon", check_weather=True, skip_conflicts=True
        )
    
    # Should have skipped the conflicting date
    assert result['skipped_conflicts'] >= 1
    
    # Verify no booking was created for the conflicting time
    visits = get_visits()
    conflicting_bookings = [v for v in visits if v['startAt'] == "2025-06-09T10:00:00"]
    assert len(conflicting_bookings) == 1  # Only the original booking


def test_generate_bookings_skips_bad_weather(clean_db):
    """Test that booking generation skips dates with bad weather."""
    recurring_id = create_recurring_job(
        client_id="C_MONDAY",
        day_of_week=0,
        start_time="10:00",
        duration_hours=2.0,
        start_date="2025-06-02",
        end_date="2025-06-30",
        job_tag="residential"
    )
    
    # Mock weather to return bad for some dates
    call_count = [0]
    def mock_weather(city, date, start_hour, end_hour):
        call_count[0] += 1
        # Return bad weather for first call, good for others
        if call_count[0] == 1:
            return {
                'suitable': False,
                'confidence': 'bad',
                'reason': 'Bad weather',
                'max_pop': 0.8,
                'severe_weather': True
            }
        return {
            'suitable': True,
            'confidence': 'high',
            'reason': 'Clear weather',
            'max_pop': 0.1,
            'severe_weather': False
        }
    
    with patch('src.api.recurring_jobs.check_weather_with_confidence', side_effect=mock_weather):
        result = generate_bookings_from_recurring_job(
            recurring_id, city="Saskatoon", check_weather=True, skip_conflicts=True
        )
    
    # Should have skipped at least one date due to weather
    assert result['skipped_weather'] >= 1


def test_generate_bookings_creates_tentative_for_low_confidence(clean_db):
    """Test that bookings are created as tentative for low confidence weather."""
    recurring_id = create_recurring_job(
        client_id="C_MONDAY",
        day_of_week=0,
        start_time="10:00",
        duration_hours=2.0,
        start_date="2025-06-02",
        end_date="2025-06-30",
        job_tag="residential"
    )
    
    with patch('src.api.recurring_jobs.check_weather_with_confidence') as mock_weather:
        mock_weather.return_value = {
            'suitable': True,
            'confidence': 'low',
            'reason': 'Uncertain weather',
            'max_pop': 0.45,
            'severe_weather': False
        }
        
        result = generate_bookings_from_recurring_job(
            recurring_id, city="Saskatoon", check_weather=True, skip_conflicts=True
        )
    
    # Should have created bookings
    assert result['booked'] > 0
    
    # Verify bookings are tentative
    visits = get_visits()
    monday_bookings = [v for v in visits if v['client_id'] == 'C_MONDAY']
    assert len(monday_bookings) > 0
    
    # All should be tentative
    for booking in monday_bookings:
        assert booking.get('booking_status') == 'tentative'


def test_book_entire_summer(clean_db):
    """Test the convenience function to book entire summer."""
    with patch('src.api.recurring_jobs.check_weather_with_confidence') as mock_weather:
        mock_weather.return_value = {
            'suitable': True,
            'confidence': 'high',
            'reason': 'Clear weather',
            'max_pop': 0.1,
            'severe_weather': False
        }
        
        result = book_entire_summer(
            client_id="C_SUMMER",
            day_of_week=2,  # Wednesday
            start_time="09:00",
            duration_hours=3.0,
            job_tag="commercial",
            start_date="2025-06-04",  # June 4, 2025 is a Wednesday
            end_date="2025-08-27"  # August 27, 2025 is a Wednesday
        )
    
    # Should have created recurring job and bookings
    assert 'recurring_job_id' in result or 'error' not in result
    assert result['booked'] > 0
    
    # Verify recurring job exists
    recurring_jobs = get_recurring_jobs(client_id="C_SUMMER")
    assert len(recurring_jobs) == 1


def test_deactivate_recurring_job(clean_db):
    """Test deactivating a recurring job."""
    recurring_id = create_recurring_job(
        client_id="C_DEACTIVATE",
        day_of_week=0,
        start_time="10:00",
        duration_hours=2.0,
        start_date="2025-06-01",
        end_date="2025-08-31",
        job_tag="residential"
    )
    
    # Deactivate it
    updated = deactivate_recurring_job(recurring_id)
    assert updated == 1
    
    # Should not appear in active list
    active_jobs = get_recurring_jobs(client_id="C_DEACTIVATE", active_only=True)
    assert len(active_jobs) == 0
    
    # Should appear in all list
    all_jobs = get_recurring_jobs(client_id="C_DEACTIVATE", active_only=False)
    assert len(all_jobs) == 1
    assert all_jobs[0]['is_active'] == False


def test_recurring_job_respects_workdays(clean_db):
    """Test that recurring jobs only book on valid workdays (Mon-Thu)."""
    # Try to create recurring job for Friday (should work, but bookings won't generate)
    recurring_id = create_recurring_job(
        client_id="C_FRIDAY",
        day_of_week=4,  # Friday (should be rejected or not generate bookings)
        start_time="10:00",
        duration_hours=2.0,
        start_date="2025-06-06",  # June 6, 2025 is a Friday
        end_date="2025-06-27",
        job_tag="residential"
    )
    
    with patch('src.api.recurring_jobs.check_weather_with_confidence') as mock_weather:
        mock_weather.return_value = {
            'suitable': True,
            'confidence': 'high',
            'reason': 'Clear weather',
            'max_pop': 0.1,
            'severe_weather': False
        }
        
        result = generate_bookings_from_recurring_job(
            recurring_id, city="Saskatoon", check_weather=True, skip_conflicts=True
        )
    
    # Should not book Fridays (they're excluded)
    assert result['booked'] == 0


def test_recurring_job_respects_work_hours(clean_db):
    """Test that recurring jobs respect work hours (8am-8pm)."""
    # Create recurring job that starts too early
    recurring_id = create_recurring_job(
        client_id="C_EARLY",
        day_of_week=0,
        start_time="07:00",  # Before 8am
        duration_hours=2.0,
        start_date="2025-06-02",
        end_date="2025-06-30",
        job_tag="residential"
    )
    
    with patch('src.api.recurring_jobs.check_weather_with_confidence') as mock_weather:
        mock_weather.return_value = {
            'suitable': True,
            'confidence': 'high',
            'reason': 'Clear weather',
            'max_pop': 0.1,
            'severe_weather': False
        }
        
        result = generate_bookings_from_recurring_job(
            recurring_id, city="Saskatoon", check_weather=True, skip_conflicts=True
        )
    
    # Should not book times outside work hours
    assert result['booked'] == 0


def test_multiple_recurring_jobs_same_client(clean_db):
    """Test that a client can have multiple recurring jobs."""
    # Create two recurring jobs for same client
    id1 = create_recurring_job(
        client_id="C_MULTI",
        day_of_week=0,  # Monday
        start_time="10:00",
        duration_hours=2.0,
        start_date="2025-06-01",
        end_date="2025-08-31",
        job_tag="residential"
    )
    
    id2 = create_recurring_job(
        client_id="C_MULTI",
        day_of_week=2,  # Wednesday
        start_time="14:00",
        duration_hours=3.0,
        start_date="2025-06-01",
        end_date="2025-08-31",
        job_tag="commercial"
    )
    
    recurring_jobs = get_recurring_jobs(client_id="C_MULTI")
    assert len(recurring_jobs) == 2
    
    # Verify they're different
    days = [rj['day_of_week'] for rj in recurring_jobs]
    assert 0 in days
    assert 2 in days

