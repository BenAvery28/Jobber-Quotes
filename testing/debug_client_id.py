# testing/debug_client_id.py
"""
Debug script to test client ID extraction step by step
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["TEST_MODE"] = "True"

from fastapi.testclient import TestClient
from src.webapp import app
from src.db import init_db, clear_visits, get_visits

# Recreate database with correct schema
init_db()
clear_visits()

client = TestClient(app)

# Test payload
test_payload = {
    "id": "Q_DEBUG",
    "quoteStatus": "APPROVED",
    "amounts": {"totalPrice": 360.00},
    "client": {
        "id": "C_DEBUG_TEST",
        "properties": [{"city": "Saskatoon"}]
    }
}

print("=== Debug Client ID Extraction ===")
print(f"Sending payload: {test_payload}")
print(f"Expected client_id: C_DEBUG_TEST")

response = client.post("/book-job", json=test_payload)

print(f"Response status: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    print(f"Response data: {data}")
    print(f"Response client_id: {data.get('client_id')}")
    print(f"Match: {data.get('client_id') == 'C_DEBUG_TEST'}")

    # Check database
    visits = get_visits()
    print(f"Database entries: {len(visits)}")
    if visits:
        print(f"Database client_id: {visits[0]['client_id']}")
        print(f"Database match: {visits[0]['client_id'] == 'C_DEBUG_TEST'}")
else:
    print(f"Error: {response.json()}")

# Test rejected quote
print("\n=== Testing Rejected Quote ===")
rejected_payload = {
    "id": "Q_REJECTED",
    "quoteStatus": "REJECTED",
    "amounts": {"totalPrice": 360.00},
    "client": {
        "id": "C_REJECTED",
        "properties": [{"city": "Saskatoon"}]
    }
}

response = client.post("/book-job", json=rejected_payload)
print(f"Response status: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    print(f"Response status message: {data.get('status')}")
    print(f"Should be ignored: {'Ignored' in data.get('status', '')}")