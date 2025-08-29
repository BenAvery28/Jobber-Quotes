# testing/test_invalid_payloads.py
"""
Test that invalid payloads properly return 400 errors
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["TEST_MODE"] = "True"

from fastapi.testclient import TestClient
from src.webapp import app
from src.db import init_db, clear_visits

init_db()
clear_visits()

client = TestClient(app)


def test_invalid_payloads():
    """Test various invalid payloads"""

    invalid_payloads = [
        {},  # Empty payload
        {"id": "Q999"},  # Missing required fields
        {"id": "Q999", "quoteStatus": "APPROVED"},  # Missing cost
        {"id": "Q999", "quoteStatus": "APPROVED", "amounts": {}},  # Missing totalPrice
    ]

    print("=== Testing Invalid Payloads ===")

    for i, payload in enumerate(invalid_payloads):
        print(f"\nTest {i + 1}: {payload}")
        response = client.post("/book-job", json=payload)
        print(f"Status: {response.status_code}")

        if response.status_code == 400:
            print("✓ Correctly rejected with 400")
        else:
            print(f"✗ Expected 400, got {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"Response: {data}")


def test_valid_payload():
    """Test that valid payloads still work"""

    print("\n=== Testing Valid Payload ===")

    valid_payload = {
        "id": "Q_VALID",
        "quoteStatus": "APPROVED",
        "amounts": {"totalPrice": 360.00},
        "client": {
            "id": "C_VALID",
            "properties": [{"city": "Saskatoon"}]
        }
    }

    response = client.post("/book-job", json=valid_payload)
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print("✓ Valid payload processed successfully")
        print(f"Client ID: {data.get('client_id')}")
    else:
        print(f"✗ Valid payload failed: {response.json()}")


if __name__ == "__main__":
    test_invalid_payloads()
    test_valid_payload()