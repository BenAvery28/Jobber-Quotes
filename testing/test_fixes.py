# testing/test_fixes.py
"""
Quick test script to verify the main fixes work correctly
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_time_estimation():
    """Test time estimation function"""
    print("=== Testing Time Estimation ===")

    try:
        from src.api.scheduler import estimate_time

        test_cases = [
            (180, 1),  # 1 hour
            (720, 4),  # 4 hours
            (1440, 8),  # 8 hours (full day)
        ]

        for cost, expected_hours in test_cases:
            duration = estimate_time(cost)
            if duration == -1:
                print(f"Cost: ${cost} - Invalid cost returned")
                continue

            actual_hours = duration.total_seconds() / 3600
            print(
                f"Cost: ${cost}, Expected: {expected_hours}h, Actual: {actual_hours}h, Match: {actual_hours == expected_hours}")

    except Exception as e:
        print(f"Error testing time estimation: {e}")


def test_database_operations():
    """Test basic database operations"""
    print("\n=== Testing Database Operations ===")

    try:
        from src.db import init_db, clear_visits, add_visit, get_visits

        # Initialize and clear
        init_db()
        clear_visits()
        print("Database initialized and cleared")

        # Add some test visits
        test_visits = [
            ("2025-08-29T09:00:00", "2025-08-29T11:00:00", "C001"),
            ("2025-08-29T13:00:00", "2025-08-29T15:00:00", "C002"),
            ("2025-08-30T10:00:00", "2025-08-30T12:00:00", "C003")
        ]

        for start, end, client_id in test_visits:
            add_visit(start, end, client_id)
            print(f"Added visit for client {client_id}")

        # Get visits back
        visits = get_visits()
        print(f"Retrieved {len(visits)} visits from database")

        # Check client IDs
        stored_client_ids = [visit["client_id"] for visit in visits]
        expected_client_ids = ["C001", "C002", "C003"]

        for expected_id in expected_client_ids:
            found = expected_id in stored_client_ids
            print(f"Client {expected_id} stored correctly: {found}")

        # Test that all 3 visits were stored (not overwritten)
        print(f"All 3 visits stored (no overwrites): {len(visits) == 3}")

    except Exception as e:
        print(f"Error testing database operations: {e}")


def test_webapp_import():
    """Test if webapp can be imported without errors"""
    print("\n=== Testing WebApp Import ===")

    try:
        # Set test mode first
        os.environ["TEST_MODE"] = "True"

        from src.webapp import app
        print("WebApp imported successfully")

        # Try to create test client
        from fastapi.testclient import TestClient
        client = TestClient(app)
        print("Test client created successfully")

        # Test a simple webhook call
        webhook_data = {
            "id": "Q_IMPORT_TEST",
            "quoteStatus": "APPROVED",
            "amounts": {"totalPrice": 360.00},
            "client": {
                "id": "C_IMPORT_TEST",
                "properties": [{"city": "Saskatoon"}]
            }
        }

        response = client.post("/book-job", json=webhook_data)
        print(f"Test webhook call status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            client_id_match = data.get('client_id') == 'C_IMPORT_TEST'
            print(f"Client ID extraction works: {client_id_match}")

        return None  # Fix pytest warning

    except Exception as e:
        print(f"Error importing webapp: {e}")
        return None


if __name__ == "__main__":
    # Test individual components first
    test_time_estimation()
    test_database_operations()

    # Test webapp import and processing
    client = test_webapp_import()
    test_webhook_processing(client)

    print("\n=== Test Summary ===")
    print("If all tests show 'True' or 'successfully', the main fixes are working!")