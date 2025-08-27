#testing/test_book_job.py
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
    - generates a fake webhook payload with quote_id '123'
    - posts it to book-job endpoint
        - 200: to be expected if job was successfully scheduled
        - 400: to be expected if schedule for next month is full (subject to change)
    If 200: check
      - Response has correct message and fields
      - Job ID is generated correctly
      - Visits count increases
      - Cost is carried through
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








