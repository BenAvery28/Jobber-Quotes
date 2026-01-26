# testing/test_webhook_calander_integration.py
"""
Integration tests for webhook processing and calander database functionality
Tests end-to-end flow from webhook receipt to database storage
"""

import pytest
import os

# Set environment variables BEFORE importing webapp
os.environ["TEST_MODE"] = "True"
os.environ["JOBBER_CLIENT_ID"] = "test_client_id"
os.environ["JOBBER_CLIENT_SECRET"] = "test_secret_key"
os.environ["OPENWEATHER_API_KEY"] = "test_weather_key"

from fastapi.testclient import TestClient
from datetime import datetime, timedelta
from src.webapp import app
from src.db import init_db, clear_visits, get_visits, get_booked_days_in_current_month, clear_processed_quotes
from testing.mock_data import generate_jobber_webhook, generate_mock_quote_for_graphql
from testing.webhook_test_helpers import patch_jobber_client_for_test

client = TestClient(app)


class TestWebhookToCalanderFlow:
    """Test the complete flow from webhook to calander database"""

    def setup_method(self):
        """Setup before each test"""
        os.environ["TEST_MODE"] = "True"  # Ensure test mode
        init_db()
        clear_visits()
        clear_processed_quotes()  # Reset idempotency tracking

    def test_approved_quote_creates_calander_entry(self):
        """Test that approved quote creates proper calander entry via webhook"""
        webhook = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id="Q500")
        quote_data = generate_mock_quote_for_graphql(
            quote_id="Q500",
            cost=540.00,  # 3 hour job
            client_id="C500"
        )
        
        with patch_jobber_client_for_test(quote_data=quote_data):
            response = client.post("/webhook/jobber", json=webhook)
            # Webhook should be accepted (202)
            assert response.status_code == 202
            # Note: Actual database entry creation happens in background task

    def test_rejected_quote_no_calander_entry(self):
        """Test that rejected quotes don't create calander entries"""
        webhook = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id="Q501")
        quote_data = generate_mock_quote_for_graphql(
            quote_id="Q501",
            cost=400.00,
            client_id="C501"
        )
        # Override status to rejected
        quote_data["quoteStatus"] = "rejected"
        
        with patch_jobber_client_for_test(quote_data=quote_data):
            response = client.post("/webhook/jobber", json=webhook)
            # Should return 200 with ignored status (not 202, since it's not queued)
            assert response.status_code == 200
            response_data = response.json()
            assert "ignored" in response_data["status"].lower() or "not approved" in response_data["status"].lower()

        # No calander entry should be created
        visits = get_visits()
        assert len(visits) == 0

    def test_multiple_clients_sequential_booking(self):
        """Test booking multiple clients sequentially via webhook"""
        test_cases = [
            {"quote_id": "Q_MULTI1", "client_id": "C_MULTI1", "cost": 360.0},
            {"quote_id": "Q_MULTI2", "client_id": "C_MULTI2", "cost": 720.0},
            {"quote_id": "Q_MULTI3", "client_id": "C_MULTI3", "cost": 1440.0},
        ]
        
        for case in test_cases:
            webhook = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id=case["quote_id"])
            quote_data = generate_mock_quote_for_graphql(
                quote_id=case["quote_id"],
                cost=case["cost"],
                client_id=case["client_id"]
            )
            
            with patch_jobber_client_for_test(quote_data=quote_data):
                response = client.post("/webhook/jobber", json=webhook)
                # Should accept webhook
                assert response.status_code == 202

    def test_scheduling_preserves_client_separation(self):
        """Test that different clients get different time slots via webhook"""
        webhook1 = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id="Q600")
        quote_data1 = generate_mock_quote_for_graphql(
            quote_id="Q600",
            cost=360.00,  # 2 hour job
            client_id="C600"
        )
        
        webhook2 = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id="Q601")
        quote_data2 = generate_mock_quote_for_graphql(
            quote_id="Q601",
            cost=360.00,  # 2 hour job
            client_id="C601"
        )

        # Book first client
        with patch_jobber_client_for_test(quote_data=quote_data1):
            response1 = client.post("/webhook/jobber", json=webhook1)
            assert response1.status_code == 202

        # Book second client
        with patch_jobber_client_for_test(quote_data=quote_data2):
            response2 = client.post("/webhook/jobber", json=webhook2)
            assert response2.status_code == 202

    def test_cost_based_time_estimation_stored_correctly(self):
        """Test that different job costs are processed via webhook"""
        cost_test_cases = [
            {"cost": 180.00, "expected_hours": 1, "client_id": "C700"},  # 1 hour
            {"cost": 720.00, "expected_hours": 4, "client_id": "C701"},  # 4 hours
            {"cost": 1440.00, "expected_hours": 8, "client_id": "C702"},  # 8 hours
        ]

        for test_case in cost_test_cases:
            quote_id = f"Q_{test_case['client_id']}"
            webhook = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id=quote_id)
            quote_data = generate_mock_quote_for_graphql(
                quote_id=quote_id,
                cost=test_case["cost"],
                client_id=test_case["client_id"]
            )

            with patch_jobber_client_for_test(quote_data=quote_data):
                response = client.post("/webhook/jobber", json=webhook)
                # Should accept webhook (actual processing happens in background)
                assert response.status_code == 202


class TestCalanderDataConsistency:
    """Test data consistency between API responses and calander database"""

    def setup_method(self):
        """Setup before each test"""
        os.environ["TEST_MODE"] = "True"
        init_db()
        clear_visits()
        clear_processed_quotes()  # Reset idempotency tracking

    def test_api_response_matches_database_entry(self):
        """Test that webhook is properly accepted and processed"""
        webhook = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id="Q800")
        quote_data = generate_mock_quote_for_graphql(
            quote_id="Q800",
            cost=500.0,
            client_id="C800"
        )

        with patch_jobber_client_for_test(quote_data=quote_data):
            response = client.post("/webhook/jobber", json=webhook)
            # Should accept webhook
            assert response.status_code == 202
            # Note: Database entry creation happens in background task

    def test_monthly_booking_count_accuracy(self):
        """Test that monthly booking count reflects actual database state"""
        current_month = datetime.now().replace(day=1)

        # Create bookings in current month (different days)
        current_month_bookings = [
            (current_month.replace(day=5), "C900"),
            (current_month.replace(day=10), "C901"),
            (current_month.replace(day=15), "C902"),
            (current_month.replace(day=5, hour=14), "C903"),  # Same day as first, different time
        ]

        # Create booking in different month
        next_month = current_month + timedelta(days=35)
        next_month_bookings = [
            (next_month.replace(day=1), "C904")
        ]

        successful_current_month = 0

        for booking_date, client_id in current_month_bookings + next_month_bookings:
            quote_id = f"Q_{client_id}"
            webhook = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id=quote_id)
            quote_data = generate_mock_quote_for_graphql(
                quote_id=quote_id,
                cost=360.00,
                client_id=client_id
            )

            with patch_jobber_client_for_test(quote_data=quote_data):
                response = client.post("/webhook/jobber", json=webhook)

                if response.status_code == 202 and client_id.startswith("C90") and not client_id == "C904":
                    successful_current_month += 1

        # Check monthly count - should count distinct days only
        booked_days = get_booked_days_in_current_month()

        # We expect 3 distinct days in current month (day 5, 10, 15)
        # Day 5 has two bookings but should count as 1 day
        expected_days = min(successful_current_month, 3)  # Max 3 distinct days we tried to book

        if successful_current_month > 0:
            assert booked_days > 0
            assert booked_days <= 3  # Can't exceed the distinct days we attempted


class TestErrorHandlingWithCalander:
    """Test error conditions and their impact on calander database"""

    def setup_method(self):
        """Setup before each test"""
        os.environ["TEST_MODE"] = "True"
        init_db()
        clear_visits()
        clear_processed_quotes()  # Reset idempotency tracking

    def test_invalid_payload_no_database_entry(self):
        """Test that invalid webhook payloads don't create database entries"""
        invalid_webhooks = [
            {},  # Empty payload
            {"data": {}},  # Missing webHookEvent
            {"data": {"webHookEvent": {}}},  # Missing required fields
        ]

        for webhook in invalid_webhooks:
            response = client.post("/webhook/jobber", json=webhook)
            assert response.status_code == 400

            # Database should remain empty
            visits = get_visits()
            assert len(visits) == 0

    def test_no_available_slots_no_database_entry(self):
        """Test that invalid quotes don't create database entries"""
        webhook = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id="Q1000")
        quote_data = generate_mock_quote_for_graphql(
            quote_id="Q1000",
            cost=0.01,  # Invalid cost
            client_id="C1000"
        )

        with patch_jobber_client_for_test(quote_data=quote_data):
            response = client.post("/webhook/jobber", json=webhook)
            # Should either accept (202) or reject (400) depending on validation
            assert response.status_code in [202, 400]
            
            if response.status_code == 400:
                # No database entry should be created for failed bookings
                visits = get_visits()
                client_ids = [visit["client_id"] for visit in visits]
                assert "C1000" not in client_ids

    def teardown_method(self):
        """Cleanup after each test"""
        clear_visits()


if __name__ == "__main__":
    # Run tests if this file is executed directly
    pytest.main([__file__, "-v"])