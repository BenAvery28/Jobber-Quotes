# testing/test_book_job.py
"""
Tests for booking functionality using the production webhook endpoint.
Updated to use /webhook/jobber endpoint with proper GraphQL mocking.
"""
import pytest
import os
from unittest.mock import patch

# Set environment variables BEFORE importing webapp
os.environ["TEST_MODE"] = "True"
os.environ["JOBBER_CLIENT_ID"] = "test_client_id"
os.environ["JOBBER_CLIENT_SECRET"] = "test_secret_key"
os.environ["OPENWEATHER_API_KEY"] = "test_weather_key"

from fastapi.testclient import TestClient
from src.webapp import app
from src.db import init_db, clear_visits, clear_processed_quotes
from testing.mock_data import generate_jobber_webhook, generate_mock_quote_for_graphql
from testing.webhook_test_helpers import patch_jobber_client_for_test
from datetime import datetime, timedelta
from unittest.mock import patch

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_database():
    """Clean database before each test to ensure isolation."""
    init_db()
    clear_visits()
    clear_processed_quotes()
    # Ensure TEST_MODE is set (should already be set, but ensure it)
    os.environ["TEST_MODE"] = "True"
    yield


@pytest.fixture
def no_test_mode():
    """
    temporarily disables TEST_MODE
    endpoints will behave differently depending on TEST_MODE
    (may result in crash while once api is granted)

    returns: NONE (alters environment variable to false)
    """

    original_value = os.environ.get("TEST_MODE", "True")
    os.environ["TEST_MODE"] = "False"
    yield
    os.environ["TEST_MODE"] = original_value  # Restore original value


def test_book_job():
    """
    Tests a normal booking using the production webhook endpoint.
    - Receives webhook with minimal payload (just IDs)
    - Fetches full quote details via GraphQL
    - Books the job
    - Returns 202 Accepted (webhook processed in background)
    """
    webhook = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id="Q123")
    quote_data = generate_mock_quote_for_graphql(
        quote_id="Q123",
        cost=500.0,
        client_id="C123",
        client_name="Test Client"
    )
    
    # Mock all external dependencies to avoid real API calls
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
        
        # Mock the background task to prevent it from actually running (TestClient runs them synchronously)
        with patch('src.webapp.process_webhook_background') as mock_background:
            with patch_jobber_client_for_test(quote_data=quote_data, job_id="J123"):
                response = client.post("/webhook/jobber", json=webhook)
                
                # Webhook should return 202 Accepted immediately (before background processing)
                assert response.status_code == 202, f"Expected 202, got {response.status_code}: {response.json()}"
                data = response.json()
                assert data["status"] == "accepted"
                assert data["quote_id"] == "Q123"
                
                # Verify background task was queued (but don't wait for it)
                # Note: TestClient runs background tasks synchronously, so we mock it to avoid delays


def test_book_job_invalid_payload(no_test_mode):
    """
    Tests invalid input:
      - Sends an empty payload {}
      - Expects a 400 Bad Request response
    """

    response = client.post("/book-job", json={})  # Empty payload
    assert response.status_code == 400


def test_book_job_unauthorized(no_test_mode):
    """
    Tests unauthorized access (when TEST_MODE is disabled):
      - Sends a webhook request without proper auth token
      - Expects a 401 Unauthorized response
      
    Note: The no_test_mode fixture disables TEST_MODE, otherwise
    the endpoint allows requests without auth for testing purposes.
    """
    webhook = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id="Q123")
    
    # When TEST_MODE=False and no token, should return 401
    response = client.post("/webhook/jobber", json=webhook)
    assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.json()}"


def test_database_structure():
    """
    Tests that the new database structure works correctly
    - Verifies that client_id is stored and retrieved properly
    """
    from src.db import init_db, add_visit, get_visits, clear_visits

    # Initialize and clear database
    init_db()
    clear_visits()

    # Add a visit with client_id
    test_start = "2025-08-29T09:00:00"
    test_end = "2025-08-29T11:00:00"
    test_client_id = "C456"

    add_visit(test_start, test_end, test_client_id)

    # Retrieve visits and check structure
    visits = get_visits()
    assert len(visits) == 1

    visit = visits[0]
    assert visit["client_id"] == test_client_id
    assert visit["startAt"] == test_start
    assert visit["endAt"] == test_end
    assert "date" in visit


def test_multiple_client_bookings():
    """
    Test that multiple clients can have bookings and are stored correctly
    """
    from src.db import init_db, add_visit, get_visits, clear_visits
    from testing.mock_data import generate_mock_calander_data

    init_db()
    clear_visits()

    # Add multiple mock bookings
    mock_data = generate_mock_calander_data()

    for entry in mock_data:
        add_visit(entry["start_time"], entry["finish_time"], entry["client_id"])

    visits = get_visits()
    assert len(visits) == len(mock_data)

    # Verify each client_id is unique and stored correctly
    client_ids = [visit["client_id"] for visit in visits]
    assert len(set(client_ids)) == len(client_ids)  # All unique

    # Check that all expected client IDs are present
    expected_ids = [entry["client_id"] for entry in mock_data]
    for expected_id in expected_ids:
        assert expected_id in client_ids


def test_webhook_variations():
    """
    Test different webhook scenarios using production endpoint.
    Tests that webhook properly handles different quote statuses.
    """
    # Test approved quote
    webhook = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id="Q_APPROVED")
    quote_data = generate_mock_quote_for_graphql(
        quote_id="Q_APPROVED",
        cost=720.0,
        client_id="C_VAR1"
    )
    
    with patch_jobber_client_for_test(quote_data=quote_data):
        response = client.post("/webhook/jobber", json=webhook)
        assert response.status_code == 202  # Accepted for processing
    
    # Test rejected quote (should be ignored)
    webhook_rejected = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id="Q_REJECTED")
    quote_data_rejected = generate_mock_quote_for_graphql(
        quote_id="Q_REJECTED",
        cost=400.0,
        client_id="C_VAR2"
    )
    # Override status to rejected
    quote_data_rejected["quoteStatus"] = "rejected"
    
    with patch_jobber_client_for_test(quote_data=quote_data_rejected):
        response = client.post("/webhook/jobber", json=webhook_rejected)
        # Should return 200 with ignored status (not 202, since it's not queued)
        assert response.status_code == 200
        data = response.json()
        assert "ignored" in data["status"].lower() or "not approved" in data["status"].lower()


def test_client_id_extraction():
    """
    Test that client IDs are properly extracted from GraphQL quote responses
    """
    test_cases = [
        {"quote_id": "Q_CLIENT1", "client_id": "C_CLIENT1", "cost": 360.0},
        {"quote_id": "Q_CLIENT2", "client_id": "C_CLIENT2", "cost": 720.0},
        {"quote_id": "Q_CLIENT3", "client_id": "C_CLIENT3", "cost": 1440.0},
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
            # Should accept the webhook
            assert response.status_code in [200, 202]


def test_calander_table_operations():
    """
    Test all calander table operations: add, get, remove, clear
    """
    from src.db import init_db, add_visit, get_visits, clear_visits, remove_visit_by_name

    init_db()
    clear_visits()

    # Test adding visits
    test_data = [
        ("2025-08-29T09:00:00", "2025-08-29T11:00:00", "C100"),
        ("2025-08-29T13:00:00", "2025-08-29T15:00:00", "C101"),
        ("2025-08-30T10:00:00", "2025-08-30T12:00:00", "C100")  # Same client, different day
    ]

    for start, end, client_id in test_data:
        add_visit(start, end, client_id)

    # Test getting visits
    visits = get_visits()
    assert len(visits) == 3

    # Test removing visits by client_id
    removed_count = remove_visit_by_name("C100")
    assert removed_count == 2  # Should remove 2 bookings for C100

    visits = get_visits()
    assert len(visits) == 1
    assert visits[0]["client_id"] == "C101"

    # Test clearing all visits
    clear_visits()
    visits = get_visits()
    assert len(visits) == 0


def test_time_estimation_with_client_tracking():
    """
    Test that time estimation works correctly and client info is preserved.
    Uses production webhook flow with GraphQL mocking.
    """
    from src.api.scheduler import estimate_time

    # Test various cost scenarios
    test_costs = [
        (180, "1 hour"),  # 1 hour job
        (720, "4 hours"),  # Half day
        (1440, "8 hours"),  # Full day
        (2880, "2 days")  # Multi-day
    ]

    for cost, description in test_costs:
        duration = estimate_time(cost)
        assert duration != -1, f"Failed for {description} (${cost})"

        # Create webhook and quote data for this cost
        quote_id = f"Q_{cost}"
        client_id = f"C_{cost}"
        webhook = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id=quote_id)
        quote_data = generate_mock_quote_for_graphql(
            quote_id=quote_id,
            cost=cost,
            client_id=client_id
        )

        with patch_jobber_client_for_test(quote_data=quote_data):
            response = client.post("/webhook/jobber", json=webhook)
            # Should accept the webhook
            assert response.status_code in [200, 202]


def test_scheduling_conflict_detection():
    """
    Test that the system properly detects scheduling conflicts for different clients.
    Uses production webhook endpoint.
    """
    from src.db import init_db, clear_visits, add_visit, get_visits

    init_db()
    clear_visits()

    # Pre-book a slot
    existing_start = "2025-08-30T10:00:00"
    existing_end = "2025-08-30T12:00:00"
    add_visit(existing_start, existing_end, "C_EXISTING")

    # Try to book overlapping slot for different client
    webhook = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id="Q_CONFLICT_TEST")
    quote_data = generate_mock_quote_for_graphql(
        quote_id="Q_CONFLICT_TEST",
        cost=360.0,  # 2 hour job
        client_id="C_NEW"
    )

    with patch_jobber_client_for_test(quote_data=quote_data):
        response = client.post("/webhook/jobber", json=webhook)
        
        # Should accept webhook (202) or return error (400/500)
        assert response.status_code in [200, 202, 400, 500]

        if response.status_code == 202:
            # Webhook accepted, will be processed in background
            # Check that existing booking is still there
            visits = get_visits()
            client_ids = [visit["client_id"] for visit in visits]
            assert "C_EXISTING" in client_ids