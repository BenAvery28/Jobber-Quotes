# testing/test_book_job.py
import pytest
import os
from fastapi.testclient import TestClient
from src.webapp import app
from testing.mock_data import generate_mock_webhook

client = TestClient(app)


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
    Tests a normal booking (booking that would be expected barring any failures)
    - generates a fake webhook payload with quote_id 'Q123'
    - posts it to book-job endpoint
        - 200: to be expected if job was successfully scheduled
        - 400: to be expected if schedule for next month is full (subject to change)
    If 200: check
      - Response has correct message and fields
      - Job ID is generated correctly
      - Visits count increases
      - Cost is carried through
      - Client ID is included in response
    """

    # Fake webhook payload
    payload = generate_mock_webhook(quote_id="Q123")["data"]
    response = client.post("/book-job", json=payload)
    assert response.status_code in [200, 400]  # 200 if weather OK, 400 if no slot

    if response.status_code == 200:
        data = response.json()
        assert data["status"] == "Quote Q123 approved and scheduled"
        assert "scheduled_start" in data
        assert "scheduled_end" in data
        assert data["job_id"].startswith("JQuote_")
        assert data["visits_count"] > 0
        assert data["cost"] == 500.0
        assert data["client_id"] == "C123"  # Check client ID is included


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
    Tests unauthorized access:
      - Clears the in-memory token store (TOKENS)
      - Sends a booking request without proper auth
      - Expects a 401 Unauthorized response
    """

    from src.webapp import TOKENS
    TOKENS.clear()
    response = client.post("/book-job", json=generate_mock_webhook()["data"])
    assert response.status_code == 401


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
    Test different webhook payload scenarios
    """
    from testing.mock_data import generate_test_webhook_variations

    test_cases = generate_test_webhook_variations()

    for case in test_cases:
        payload = case["payload"]
        response = client.post("/book-job", json=payload)

        if case["name"] == "rejected_quote":
            # Should ignore rejected quotes
            assert response.status_code == 200
            data = response.json()
            assert "Ignored - Not an approved quote" in data["status"]
        else:
            # Approved quotes should either succeed or fail due to scheduling
            assert response.status_code in [200, 400]

            if response.status_code == 200:
                data = response.json()
                assert data["client_id"] == payload["client"]["id"]
                assert data["cost"] == payload["amounts"]["totalPrice"]


def test_client_id_extraction():
    """
    Test that client IDs are properly extracted from various payload formats
    """
    from testing.mock_data import generate_test_webhook_variations

    test_cases = generate_test_webhook_variations()

    for case in test_cases:
        if case["payload"]["quoteStatus"] == "APPROVED":
            payload = case["payload"]
            response = client.post("/book-job", json=payload)

            if response.status_code == 200:
                data = response.json()
                expected_client_id = payload["client"]["id"]
                assert data["client_id"] == expected_client_id


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
    Test that time estimation works correctly and client info is preserved
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

        # Create webhook payload for this cost
        payload = {
            "id": f"Q_{cost}",
            "quoteStatus": "APPROVED",
            "amounts": {"totalPrice": cost},
            "client": {
                "id": f"C_{cost}",
                "properties": [{"city": "Saskatoon"}]
            }
        }

        response = client.post("/book-job", json=payload)

        if response.status_code == 200:
            data = response.json()
            assert data["client_id"] == f"C_{cost}"
            assert data["cost"] == cost


def test_scheduling_conflict_detection():
    """
    Test that the system properly detects scheduling conflicts for different clients
    """
    from src.db import init_db, clear_visits, add_visit, get_visits

    init_db()
    clear_visits()

    # Pre-book a slot
    existing_start = "2025-08-30T10:00:00"
    existing_end = "2025-08-30T12:00:00"
    add_visit(existing_start, existing_end, "C_EXISTING")

    # Try to book overlapping slot for different client
    payload = {
        "id": "Q_CONFLICT_TEST",
        "quoteStatus": "APPROVED",
        "amounts": {"totalPrice": 360},  # 2 hour job
        "client": {
            "id": "C_NEW",
            "properties": [{"city": "Saskatoon"}]
        }
    }

    response = client.post("/book-job", json=payload)

    # Should either succeed (finding different slot) or fail (no slots available)
    assert response.status_code in [200, 400]

    if response.status_code == 200:
        # If successful, should have found a different time slot
        data = response.json()
        assert data["scheduled_start"] != existing_start

        # Verify both bookings exist
        visits = get_visits()
        client_ids = [visit["client_id"] for visit in visits]
        assert "C_EXISTING" in client_ids
        assert "C_NEW" in client_ids