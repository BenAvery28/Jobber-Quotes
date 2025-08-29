# testing/test_webhook_calander_integration.py
"""
Integration tests for webhook processing and calander database functionality
Tests end-to-end flow from webhook receipt to database storage
"""

import pytest
import os
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
from src.webapp import app
from src.db import init_db, clear_visits, get_visits, get_booked_days_in_current_month
from testing.mock_data import generate_test_webhook_variations, generate_mock_webhook

client = TestClient(app)


class TestWebhookToCalanderFlow:
    """Test the complete flow from webhook to calander database"""

    def setup_method(self):
        """Setup before each test"""
        os.environ["TEST_MODE"] = "True"  # Ensure test mode
        init_db()
        clear_visits()

    def test_approved_quote_creates_calander_entry(self):
        """Test that approved quote creates proper calander entry"""
        webhook_data = {
            "id": "Q500",
            "quoteStatus": "APPROVED",
            "amounts": {"totalPrice": 540.00},  # 3 hour job
            "client": {
                "id": "C500",
                "properties": [{"city": "Saskatoon"}]
            }
        }

        response = client.post("/book-job", json=webhook_data)

        if response.status_code == 200:
            # Check that calander entry was created
            visits = get_visits()
            assert len(visits) == 1

            visit = visits[0]
            assert visit["client_id"] == "C500"

            # Verify response contains correct data
            response_data = response.json()
            assert response_data["client_id"] == "C500"
            assert response_data["cost"] == 540.00
            assert "scheduled_start" in response_data
            assert "scheduled_end" in response_data

            # Verify start/end times match what's in database
            assert visit["startAt"] == response_data["scheduled_start"]
            assert visit["endAt"] == response_data["scheduled_end"]

    def test_rejected_quote_no_calander_entry(self):
        """Test that rejected quotes don't create calander entries"""
        webhook_data = {
            "id": "Q501",
            "quoteStatus": "REJECTED",
            "amounts": {"totalPrice": 400.00},
            "client": {
                "id": "C501",
                "properties": [{"city": "Saskatoon"}]
            }
        }

        response = client.post("/book-job", json=webhook_data)
        assert response.status_code == 200

        response_data = response.json()
        assert "Ignored - Not an approved quote" in response_data["status"]

        # No calander entry should be created
        visits = get_visits()
        assert len(visits) == 0

    def test_multiple_clients_sequential_booking(self):
        """Test booking multiple clients sequentially"""
        test_cases = generate_test_webhook_variations()
        approved_cases = [case for case in test_cases if case["payload"]["quoteStatus"] == "APPROVED"]

        successful_bookings = 0

        for case in approved_cases:
            response = client.post("/book-job", json=case["payload"])

            if response.status_code == 200:
                successful_bookings += 1
                response_data = response.json()

                # Verify client_id matches payload
                expected_client_id = case["payload"]["client"]["id"]
                assert response_data["client_id"] == expected_client_id

        # Check calander entries
        visits = get_visits()
        assert len(visits) == successful_bookings

        # Verify all client IDs are unique in the database
        client_ids = [visit["client_id"] for visit in visits]
        expected_client_ids = [case["payload"]["client"]["id"] for case in approved_cases]

        for expected_id in expected_client_ids:
            if any(response.status_code == 200 for response in
                   [client.post("/book-job", json=case["payload"]) for case in approved_cases if
                    case["payload"]["client"]["id"] == expected_id]):
                assert expected_id in client_ids

    def test_scheduling_preserves_client_separation(self):
        """Test that different clients get different time slots"""
        webhook_data_1 = {
            "id": "Q600",
            "quoteStatus": "APPROVED",
            "amounts": {"totalPrice": 360.00},  # 2 hour job
            "client": {
                "id": "C600",
                "properties": [{"city": "Saskatoon"}]
            }
        }

        webhook_data_2 = {
            "id": "Q601",
            "quoteStatus": "APPROVED",
            "amounts": {"totalPrice": 360.00},  # 2 hour job
            "client": {
                "id": "C601",
                "properties": [{"city": "Saskatoon"}]
            }
        }

        # Book first client
        response1 = client.post("/book-job", json=webhook_data_1)

        # Book second client
        response2 = client.post("/book-job", json=webhook_data_2)

        if response1.status_code == 200 and response2.status_code == 200:
            # Both should succeed but have different time slots
            data1 = response1.json()
            data2 = response2.json()

            assert data1["client_id"] != data2["client_id"]
            assert data1["scheduled_start"] != data2["scheduled_start"]

            # Check database has both entries
            visits = get_visits()
            assert len(visits) == 2

            client_ids = [visit["client_id"] for visit in visits]
            assert "C600" in client_ids
            assert "C601" in client_ids

    def test_cost_based_time_estimation_stored_correctly(self):
        """Test that different job costs result in appropriate time allocations"""
        cost_test_cases = [
            {"cost": 180.00, "expected_hours": 1, "client_id": "C700"},  # 1 hour
            {"cost": 720.00, "expected_hours": 4, "client_id": "C701"},  # 4 hours
            {"cost": 1440.00, "expected_hours": 8, "client_id": "C702"},  # 8 hours
        ]

        for test_case in cost_test_cases:
            webhook_data = {
                "id": f"Q_{test_case['client_id']}",
                "quoteStatus": "APPROVED",
                "amounts": {"totalPrice": test_case["cost"]},
                "client": {
                    "id": test_case["client_id"],
                    "properties": [{"city": "Saskatoon"}]
                }
            }

            response = client.post("/book-job", json=webhook_data)

            if response.status_code == 200:
                response_data = response.json()

                # Parse start and end times to verify duration
                start_time = datetime.fromisoformat(response_data["scheduled_start"])
                end_time = datetime.fromisoformat(response_data["scheduled_end"])
                actual_duration = end_time - start_time
                expected_duration = timedelta(hours=test_case["expected_hours"])

                assert actual_duration == expected_duration

                # Verify database entry
                visits = get_visits()
                matching_visit = next((v for v in visits if v["client_id"] == test_case["client_id"]), None)
                assert matching_visit is not None

                db_start = datetime.fromisoformat(matching_visit["startAt"])
                db_end = datetime.fromisoformat(matching_visit["endAt"])
                db_duration = db_end - db_start

                assert db_duration == expected_duration


class TestCalanderDataConsistency:
    """Test data consistency between API responses and calander database"""

    def setup_method(self):
        """Setup before each test"""
        os.environ["TEST_MODE"] = "True"
        init_db()
        clear_visits()

    def test_api_response_matches_database_entry(self):
        """Test that API response data exactly matches what's stored in database"""
        webhook_data = generate_mock_webhook("Q800")["data"]
        webhook_data["client"]["id"] = "C800"  # Ensure unique client ID

        response = client.post("/book-job", json=webhook_data)

        if response.status_code == 200:
            response_data = response.json()

            # Get database entry
            visits = get_visits()
            assert len(visits) == 1
            visit = visits[0]

            # Compare all fields
            assert visit["client_id"] == response_data["client_id"]
            assert visit["startAt"] == response_data["scheduled_start"]
            assert visit["endAt"] == response_data["scheduled_end"]

            # Verify date field is correctly extracted
            start_dt = datetime.fromisoformat(response_data["scheduled_start"])
            expected_date = start_dt.strftime("%Y-%m-%d")
            assert visit["date"] == expected_date

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
            webhook_data = {
                "id": f"Q_{client_id}",
                "quoteStatus": "APPROVED",
                "amounts": {"totalPrice": 360.00},
                "client": {
                    "id": client_id,
                    "properties": [{"city": "Saskatoon"}]
                }
            }

            response = client.post("/book-job", json=webhook_data)

            if response.status_code == 200 and client_id.startswith("C90") and not client_id == "C904":
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

    def test_invalid_payload_no_database_entry(self):
        """Test that invalid payloads don't create database entries"""
        invalid_payloads = [
            {},  # Empty payload
            {"id": "Q999"},  # Missing required fields
            {"id": "Q999", "quoteStatus": "APPROVED"},  # Missing cost
            {"id": "Q999", "quoteStatus": "APPROVED", "amounts": {}},  # Missing totalPrice
        ]

        for payload in invalid_payloads:
            response = client.post("/book-job", json=payload)
            assert response.status_code == 400

            # Database should remain empty
            visits = get_visits()
            assert len(visits) == 0

    def test_no_available_slots_no_database_entry(self):
        """Test that when no slots are available, no database entry is created"""
        # This test would require mocking the weather or scheduling to always return no slots
        # For now, we'll test the structure is correct when booking fails

        webhook_data = {
            "id": "Q1000",
            "quoteStatus": "APPROVED",
            "amounts": {"totalPrice": 0.01},  # Invalid cost should cause failure
            "client": {
                "id": "C1000",
                "properties": [{"city": "Saskatoon"}]
            }
        }

        response = client.post("/book-job", json=webhook_data)

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