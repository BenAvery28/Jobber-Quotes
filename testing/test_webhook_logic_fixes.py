# testing/test_webhook_logic_fixes.py
"""
Tests for webhook logic fixes:
- Visit creation failure rollback
- Idempotency with quote_id vs item_id
- App ID validation
"""

import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timedelta

# Set environment variables before importing
os.environ.setdefault("JOBBER_CLIENT_ID", "test_client_id")
os.environ.setdefault("JOBBER_CLIENT_SECRET", "test_secret")
os.environ.setdefault("JOBBER_API_BASE", "https://api.getjobber.com/api")
os.environ.setdefault("TEST_MODE", "True")
os.environ.setdefault("OPENWEATHER_API_KEY", "test_key")

from fastapi.testclient import TestClient
from src.webapp import app
from src.db import init_db, clear_visits, clear_processed_quotes, get_visits, get_processed_quote
from testing.mock_data import generate_jobber_webhook

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_database():
    """Clean database before each test."""
    init_db()
    clear_visits()
    clear_processed_quotes()
    yield
    clear_visits()
    clear_processed_quotes()


class TestVisitCreationFailureRollback:
    """Tests that visit creation failures rollback local bookings."""
    
    def test_visit_creation_failure_rolls_back_booking(self):
        """If visit creation fails, local booking should be removed."""
        webhook = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id="Q_ROLLBACK_TEST")
        
        # Mock successful quote fetch and job creation, but visit creation fails
        mock_quote = {
            "id": "Q_ROLLBACK_TEST",
            "quoteStatus": "approved",
            "title": "Test Job",
            "amounts": {"totalPrice": 500.0},
            "client": {
                "id": "C_TEST",
                "name": "Test Client",
                "billingAddress": {"city": "Saskatoon"}
            },
            "property": {"id": "P_TEST"}
        }
        
        mock_job = {"id": "J_TEST"}
        
        # Mock weather API and background task
        with patch('src.api.weather.get_hourly_forecast') as mock_weather:
            mock_weather.return_value = {
                "list": [
                    {
                        "dt": int((datetime.now() + timedelta(days=1)).timestamp()),
                        "weather": [{"main": "Clear"}],
                        "pop": 0.1
                    }
                ]
            }
            with patch('src.webapp.process_webhook_background') as mock_background:
                with patch('src.webapp.JobberClient') as mock_client_class:
                    mock_client = MagicMock()
                    mock_client_class.return_value = mock_client
                    mock_client.get_quote = AsyncMock(return_value=mock_quote)
                    mock_client.create_job = AsyncMock(return_value=mock_job)
                    mock_client.create_visit = AsyncMock(side_effect=Exception("Visit creation failed"))
                    
                    response = client.post("/webhook/jobber", json=webhook)
            
                    # Should return error
                    assert response.status_code == 500
                    assert "Failed to create visit" in response.json()["detail"]
                    
                    # Local booking should be rolled back (not in database)
                    visits = get_visits()
                    assert len(visits) == 0
                    
                    # Quote should not be marked as processed
                    processed = get_processed_quote("Q_ROLLBACK_TEST")
                    assert processed is None
    
    def test_visit_creation_success_marks_as_processed(self):
        """If visit creation succeeds, quote should be marked as processed."""
        webhook = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id="Q_SUCCESS_TEST")
        
        mock_quote = {
            "id": "Q_SUCCESS_TEST",
            "quoteStatus": "approved",
            "title": "Test Job",
            "amounts": {"totalPrice": 500.0},
            "client": {
                "id": "C_TEST",
                "name": "Test Client",
                "billingAddress": {"city": "Saskatoon"}
            },
            "property": {"id": "P_TEST"}
        }
        
        mock_job = {"id": "J_TEST"}
        mock_visit = {"id": "V_TEST"}
        
        # Mock weather API and background task
        with patch('src.api.weather.get_hourly_forecast') as mock_weather:
            mock_weather.return_value = {
                "list": [
                    {
                        "dt": int((datetime.now() + timedelta(days=1)).timestamp()),
                        "weather": [{"main": "Clear"}],
                        "pop": 0.1
                    }
                ]
            }
            with patch('src.webapp.process_webhook_background') as mock_background:
                with patch('src.webapp.JobberClient') as mock_client_class:
                    mock_client = MagicMock()
                    mock_client_class.return_value = mock_client
                    mock_client.get_quote = AsyncMock(return_value=mock_quote)
                    mock_client.create_job = AsyncMock(return_value=mock_job)
                    mock_client.create_visit = AsyncMock(return_value=mock_visit)
                    
                    with patch('src.webapp.auto_book') as mock_auto_book:
                        mock_auto_book.return_value = {
                            "startAt": (datetime.now()).isoformat(),
                            "endAt": (datetime.now()).isoformat(),
                            "booking_status": "confirmed",
                            "weather_confidence": "high"
                        }
                        
                        response = client.post("/webhook/jobber", json=webhook)
                        
                        # Should succeed
                        assert response.status_code == 200
                        
                        # Quote should be marked as processed
                        processed = get_processed_quote("Q_SUCCESS_TEST")
                        assert processed is not None
                        assert processed["quote_id"] == "Q_SUCCESS_TEST"


class TestIdempotencyWithQuoteId:
    """Tests idempotency checks with both item_id and quote_id."""
    
    def test_idempotency_check_with_item_id(self):
        """Early idempotency check should work with item_id."""
        webhook = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id="Q_IDEMPOTENT")
        
        # Mark as processed first
        from src.db import mark_quote_processed
        mark_quote_processed("Q_IDEMPOTENT", "C_TEST", "J_TEST", 
                           datetime.now().isoformat(), datetime.now().isoformat())
        
        # Second webhook should return idempotent response
        response = client.post("/webhook/jobber", json=webhook)
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("idempotent") is True
        assert "already scheduled" in data.get("status", "")
    
    def test_idempotency_check_with_quote_id_after_fetch(self):
        """Idempotency should also check quote_id after fetching quote."""
        webhook = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id="Q_ITEM_123")
        
        mock_quote = {
            "id": "Q_QUOTE_456",  # Different from item_id
            "quoteStatus": "approved",
            "title": "Test Job",
            "amounts": {"totalPrice": 500.0},
            "client": {
                "id": "C_TEST",
                "name": "Test Client",
                "billingAddress": {"city": "Saskatoon"}
            },
            "property": {"id": "P_TEST"}
        }
        
        # Mark quote_id as processed (not item_id)
        from src.db import mark_quote_processed
        mark_quote_processed("Q_QUOTE_456", "C_TEST", "J_TEST",
                           datetime.now().isoformat(), datetime.now().isoformat())
        
        with patch('src.webapp.JobberClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.get_quote = AsyncMock(return_value=mock_quote)
            
            response = client.post("/webhook/jobber", json=webhook)
            
            # Should return idempotent response based on quote_id
            assert response.status_code == 200
            data = response.json()
            assert data.get("idempotent") is True


class TestAppIdValidation:
    """Tests for appId validation in webhooks."""
    
    def test_webhook_rejects_invalid_app_id(self):
        """Webhook should reject if appId doesn't match client ID."""
        webhook = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id="Q_APP_TEST")
        webhook["data"]["webHookEvent"]["appId"] = "wrong_app_id"
        
        with patch('src.webapp.JOBBER_CLIENT_ID', 'correct_app_id'):
            response = client.post("/webhook/jobber", json=webhook)
            
            # Should reject with 401
            assert response.status_code == 401
            assert "Invalid appId" in response.json()["detail"]
    
    def test_webhook_accepts_valid_app_id(self):
        """Webhook should accept if appId matches client ID."""
        webhook = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id="Q_APP_VALID")
        webhook["data"]["webHookEvent"]["appId"] = "test_client_id"
        
        mock_quote = {
            "id": "Q_APP_VALID",
            "quoteStatus": "approved",
            "title": "Test Job",
            "amounts": {"totalPrice": 500.0},
            "client": {
                "id": "C_TEST",
                "name": "Test Client",
                "billingAddress": {"city": "Saskatoon"}
            },
            "property": {"id": "P_TEST"}
        }
        
        # Mock weather API and background task
        with patch('src.api.weather.get_hourly_forecast') as mock_weather:
            mock_weather.return_value = {
                "list": [
                    {
                        "dt": int((datetime.now() + timedelta(days=1)).timestamp()),
                        "weather": [{"main": "Clear"}],
                        "pop": 0.1
                    }
                ]
            }
            with patch('src.webapp.process_webhook_background') as mock_background:
                with patch('src.webapp.JobberClient') as mock_client_class:
                    mock_client = MagicMock()
                    mock_client_class.return_value = mock_client
                    mock_client.get_quote = AsyncMock(return_value=mock_quote)
                    mock_client.create_job = AsyncMock(return_value={"id": "J_TEST"})
                    mock_client.create_visit = AsyncMock(return_value={"id": "V_TEST"})
                    
                    with patch('src.webapp.auto_book') as mock_auto_book:
                        mock_auto_book.return_value = {
                            "startAt": datetime.now().isoformat(),
                            "endAt": datetime.now().isoformat(),
                            "booking_status": "confirmed",
                            "weather_confidence": "high"
                        }
                        
                        response = client.post("/webhook/jobber", json=webhook)
                        
                        # Should proceed (may fail later, but appId validation passed)
                        assert response.status_code in [200, 400, 500]  # Not 401
    
    def test_webhook_allows_missing_app_id(self):
        """Webhook should allow missing appId (optional field)."""
        webhook = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id="Q_APP_MISSING")
        # Remove appId
        del webhook["data"]["webHookEvent"]["appId"]
        
        mock_quote = {
            "id": "Q_APP_MISSING",
            "quoteStatus": "approved",
            "title": "Test Job",
            "amounts": {"totalPrice": 500.0},
            "client": {
                "id": "C_TEST",
                "name": "Test Client",
                "billingAddress": {"city": "Saskatoon"}
            },
            "property": {"id": "P_TEST"}
        }
        
        with patch('src.webapp.JobberClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.get_quote = AsyncMock(return_value=mock_quote)
            mock_client.create_job = AsyncMock(return_value={"id": "J_TEST"})
            mock_client.create_visit = AsyncMock(return_value={"id": "V_TEST"})
            
            with patch('src.webapp.auto_book') as mock_auto_book:
                mock_auto_book.return_value = {
                    "startAt": datetime.now().isoformat(),
                    "endAt": datetime.now().isoformat(),
                    "booking_status": "confirmed",
                    "weather_confidence": "high"
                }
                
                response = client.post("/webhook/jobber", json=webhook)
                
                # Should not reject due to missing appId
                assert response.status_code != 401

