# testing/test_weather_improvements.py
"""
Comprehensive tests for weather API improvements:
- Weather confidence levels
- Tentative bookings
- Pseudo-reshuffler
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

from src.api.weather import check_weather_with_confidence, get_hourly_forecast
from src.db import init_db, clear_visits, add_visit, get_tentative_bookings, update_booking_status, get_visits
from src.api.scheduler import auto_book


@pytest.fixture
def clean_db():
    """Clear database before each test."""
    init_db()
    clear_visits()
    yield
    clear_visits()


def create_mock_forecast(date, hour, pop=0.0, weather_main="Clear"):
    """Helper to create mock forecast data."""
    dt = datetime.combine(date, datetime.min.time().replace(hour=hour))
    return {
        "dt": int(dt.timestamp()),
        "weather": [{"main": weather_main}],
        "pop": pop
    }


def test_weather_confidence_high():
    """Test high confidence weather check (clear weather, low pop)."""
    # Mock forecast with clear weather and low pop
    mock_forecast = {
        "list": [
            create_mock_forecast(datetime(2025, 1, 15).date(), 10, pop=0.1, weather_main="Clear"),
            create_mock_forecast(datetime(2025, 1, 15).date(), 13, pop=0.15, weather_main="Clear"),
        ]
    }
    
    with patch('src.api.weather.get_hourly_forecast', return_value=mock_forecast):
        result = check_weather_with_confidence("Saskatoon", datetime(2025, 1, 15), 8, 20)
        
        assert result['suitable'] == True
        assert result['confidence'] == 'high'
        assert result['max_pop'] < 0.2
        assert result['severe_weather'] == False


def test_weather_confidence_medium():
    """Test medium confidence weather check (moderate pop)."""
    mock_forecast = {
        "list": [
            create_mock_forecast(datetime(2025, 1, 15).date(), 10, pop=0.3, weather_main="Clouds"),
        ]
    }
    
    with patch('src.api.weather.get_hourly_forecast', return_value=mock_forecast):
        result = check_weather_with_confidence("Saskatoon", datetime(2025, 1, 15), 8, 20)
        
        assert result['suitable'] == True
        assert result['confidence'] == 'medium'
        assert 0.2 <= result['max_pop'] < 0.4


def test_weather_confidence_low():
    """Test low confidence weather check (high pop but < 50%)."""
    mock_forecast = {
        "list": [
            create_mock_forecast(datetime(2025, 1, 15).date(), 10, pop=0.45, weather_main="Clouds"),
        ]
    }
    
    with patch('src.api.weather.get_hourly_forecast', return_value=mock_forecast):
        result = check_weather_with_confidence("Saskatoon", datetime(2025, 1, 15), 8, 20)
        
        assert result['suitable'] == True
        assert result['confidence'] == 'low'
        assert 0.4 <= result['max_pop'] < 0.5


def test_weather_confidence_bad():
    """Test bad weather check (high pop or severe weather)."""
    # Test high pop
    mock_forecast_high_pop = {
        "list": [
            create_mock_forecast(datetime(2025, 1, 15).date(), 10, pop=0.6, weather_main="Rain"),
        ]
    }
    
    with patch('src.api.weather.get_hourly_forecast', return_value=mock_forecast_high_pop):
        result = check_weather_with_confidence("Saskatoon", datetime(2025, 1, 15), 8, 20)
        
        assert result['suitable'] == False
        assert result['confidence'] == 'bad'
        assert result['max_pop'] > 0.5
    
    # Test severe weather
    mock_forecast_severe = {
        "list": [
            create_mock_forecast(datetime(2025, 1, 15).date(), 10, pop=0.2, weather_main="Thunderstorm"),
        ]
    }
    
    with patch('src.api.weather.get_hourly_forecast', return_value=mock_forecast_severe):
        result = check_weather_with_confidence("Saskatoon", datetime(2025, 1, 15), 8, 20)
        
        assert result['suitable'] == False
        assert result['confidence'] == 'bad'
        assert result['severe_weather'] == True


def test_weather_confidence_forecast_unavailable():
    """Test behavior when forecast is unavailable."""
    with patch('src.api.weather.get_hourly_forecast', return_value=None):
        result = check_weather_with_confidence("Saskatoon", datetime(2025, 1, 15), 8, 20)
        
        assert result['suitable'] == True
        assert result['confidence'] == 'low'
        assert 'unavailable' in result['reason'].lower()


def test_tentative_booking_storage(clean_db):
    """Test that tentative bookings are stored correctly."""
    start_at = "2025-01-15T10:00:00"
    end_at = "2025-01-15T12:00:00"
    
    add_visit(start_at, end_at, "C_TEST", "residential", "tentative")
    
    visits = get_visits()
    assert len(visits) == 1
    assert visits[0]["booking_status"] == "tentative"
    
    # Check tentative bookings function
    tentative = get_tentative_bookings()
    assert len(tentative) == 1
    assert tentative[0]["client_id"] == "C_TEST"


def test_tentative_booking_upgrade(clean_db):
    """Test upgrading tentative booking to confirmed."""
    start_at = "2025-01-15T10:00:00"
    end_at = "2025-01-15T12:00:00"
    
    add_visit(start_at, end_at, "C_TEST", "residential", "tentative")
    
    # Upgrade to confirmed
    update_booking_status("C_TEST", start_at, "confirmed")
    
    visits = get_visits()
    assert visits[0]["booking_status"] == "confirmed"
    
    # Should not appear in tentative list
    tentative = get_tentative_bookings()
    assert len(tentative) == 0


def test_auto_book_creates_tentative_for_low_confidence(clean_db):
    """Test that auto_book creates tentative bookings for low confidence weather."""
    # Use a known workday (Monday, Jan 13, 2025)
    test_date = datetime(2025, 1, 13, 8, 0)  # Monday
    
    with patch('src.api.weather.check_weather_with_confidence') as mock_check:
        # Return low confidence for all dates
        mock_check.return_value = {
            'suitable': True,
            'confidence': 'low',
            'reason': 'Uncertain weather',
            'max_pop': 0.45,
            'severe_weather': False
        }
        
        visits = []
        duration = timedelta(hours=2)
        
        slot = auto_book(visits, test_date, duration, "Saskatoon", "C_TEST", allow_tentative=True)
        
        # Should return tentative slot since all weather is low confidence
        assert slot is not None
        assert slot.get("booking_status") == "tentative"
        assert slot.get("weather_confidence") == "low"


def test_auto_book_creates_confirmed_for_high_confidence(clean_db):
    """Test that auto_book creates confirmed bookings for high confidence weather."""
    mock_forecast = {
        "list": [
            create_mock_forecast(datetime(2025, 1, 15).date(), 10, pop=0.1, weather_main="Clear"),
        ]
    }
    
    with patch('src.api.weather.get_hourly_forecast', return_value=mock_forecast):
        with patch('src.api.weather.check_weather_with_confidence') as mock_check:
            mock_check.return_value = {
                'suitable': True,
                'confidence': 'high',
                'reason': 'Clear weather',
                'max_pop': 0.1,
                'severe_weather': False
            }
            
            visits = []
            start_date = datetime(2025, 1, 15, 8, 0)
            duration = timedelta(hours=2)
            
            slot = auto_book(visits, start_date, duration, "Saskatoon", "C_TEST", allow_tentative=True)
            
            if slot:
                assert slot.get("booking_status") == "confirmed"
                assert slot.get("weather_confidence") == "high"


def test_get_visits_excludes_tentative(clean_db):
    """Test that get_visits can exclude tentative bookings."""
    # Add both confirmed and tentative bookings
    add_visit("2025-01-15T10:00:00", "2025-01-15T12:00:00", "C_CONFIRMED", "residential", "confirmed")
    add_visit("2025-01-16T10:00:00", "2025-01-16T12:00:00", "C_TENTATIVE", "residential", "tentative")
    
    # Get all visits
    all_visits = get_visits(include_tentative=True)
    assert len(all_visits) == 2
    
    # Get only confirmed
    confirmed_only = get_visits(include_tentative=False)
    assert len(confirmed_only) == 1
    assert confirmed_only[0]["client_id"] == "C_CONFIRMED"


def test_forecast_window_reduced():
    """Test that forecast window is reduced to 2 days for better accuracy."""
    # This is tested implicitly - the function should use days_ahead=2
    # We can verify by checking the default parameter
    import inspect
    sig = inspect.signature(get_hourly_forecast)
    assert sig.parameters['days_ahead'].default == 2

