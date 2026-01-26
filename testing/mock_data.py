# testing/mock_data.py
import random
from datetime import datetime, timedelta
from typing import Optional


def generate_mock_quote(quote_id=None):
    """
    Generate a mock Jobber quote (something like this will be input when an order is filled)
    params:
     - quote_id (str, optional): if none, generates a random quote id
    Returns:
     - dictionary quote containing: id, client (id, email + city), amount (total price)
    """

    if quote_id is None:
        quote_id = f"Q{random.randint(100, 999)}"

    client_id = f"C{random.randint(100, 999)}"

    return {
        "id": quote_id,
        "client": {
            "id": client_id,
            "emails": [{"address": f"client{random.randint(1, 10)}@example.com"}],
            "properties": [{"city": random.choice(["Saskatoon", "Warman", "Emma Lake"])}]
        },
        "amounts": {"totalPrice": round(random.uniform(100, 5000), 2)},
    }


def generate_mock_visits(count=5):
    """
    Generate a list of fake job visits starting from today's date
    (simulates situation that will occur when actually deployed)
    params:
    - count (int): number of fake visits to generate
    returns:
     list[dict]: Each visit has:
            - startAt: ISO start datetime
            - endAt: ISO end datetime (2 hours after start)
            - client_id: Mock client ID
    """

    return [
        {
            "startAt": (datetime.now() + timedelta(days=i)).isoformat(),
            "endAt": (datetime.now() + timedelta(days=i, hours=2)).isoformat(),
            "client_id": f"C{random.randint(100, 999)}"
        }
        for i in range(count)
    ]


def generate_mock_webhook(quote_id=None):
    """
    Generate a mock webhook payload similar to what jobber sends when a quote is approved.
    This is the LEGACY format used by /book-job endpoint for testing.
    
    Returns:
    dict containing:
        - id: "Q123" (default)
        - quoteStatus: "APPROVED"
        - amounts: totalPrice fixed at 500.00
        - client: mock client with ID and property with city "Saskatoon"
    """
    if quote_id is None or quote_id != "Q123":
        quote_id = "Q123"
    status = "APPROVED"
    client_id = "C123"  # Consistent client ID for testing

    return {
        "data": {
            "id": quote_id,
            "quoteStatus": status,
            "amounts": {"totalPrice": 500.00},
            "client": {
                "id": client_id,
                "properties": [{"city": "Saskatoon"}]
            }
        }
    }


def generate_jobber_webhook(topic="QUOTE_APPROVED", item_id="Q123", app_id=None):
    """
    Generate a mock webhook payload in Jobber's ACTUAL format.
    
    Jobber webhooks only contain IDs, not full data. The app must then
    query the Jobber API to get full details.
    
    Args:
        topic: Webhook topic (e.g., QUOTE_APPROVED, QUOTE_CREATE)
        item_id: The ID of the item (quote, client, job) that triggered the event
        app_id: App ID (defaults to test_client_id from env, or "test-app-id-123")
        
    Returns:
        dict in Jobber's webhook format
    """
    import os
    if app_id is None:
        # Use the test client ID from environment, or default
        app_id = os.getenv("JOBBER_CLIENT_ID", "test_client_id")
    
    return {
        "data": {
            "webHookEvent": {
                "topic": topic,
                "appId": app_id,
                "accountId": "ACC123",
                "itemId": item_id,
                "occurredAt": datetime.now().isoformat()
            }
        }
    }


def generate_mock_quote_for_graphql(quote_id="Q123", cost=500.0, client_id="C123", 
                                    client_name="Test Client", city="Saskatoon"):
    """
    Generate a mock quote response that would be returned from Jobber's GraphQL API.
    
    This simulates what get_quote() returns after receiving a webhook.
    Use this to mock JobberClient.get_quote() in tests.
    
    Args:
        quote_id: Quote ID
        cost: Total price of the quote
        client_id: Client ID
        client_name: Client name
        city: City for the job
        
    Returns:
        dict matching Jobber's GraphQL quote response format
    """
    return {
        "id": quote_id,
        "quoteNumber": 1001,
        "quoteStatus": "approved",
        "title": f"Window Cleaning Service - {quote_id}",
        "amounts": {
            "totalPrice": cost,
            "subtotal": cost,
        },
        "client": {
            "id": client_id,
            "name": client_name,
            "isCompany": False,
            "firstName": client_name.split()[0] if " " in client_name else client_name,
            "lastName": client_name.split()[-1] if " " in client_name else "",
            "companyName": None,
            "billingAddress": {
                "city": city,
                "street": "123 Main St",
                "postalCode": "S7K 1A1",
                "province": "SK",
            },
            "clientProperties": {
                "nodes": [
                    {
                        "id": f"P{quote_id}",
                        "address": {
                            "city": city,
                            "street": "123 Main St",
                            "postalCode": "S7K 1A1",
                            "province": "SK",
                        },
                    }
                ]
            },
            "phones": [
                {"number": "306-555-1234", "primary": True}
            ],
            "emails": [
                {"address": f"{client_name.lower().replace(' ', '.')}@example.com", "primary": True}
            ],
        },
        "property": {
            "id": f"P{quote_id}",
            "address": {
                "city": city,
                "street": "123 Main St",
                "postalCode": "S7K 1A1",
                "province": "SK",
            },
        },
    }


def generate_test_webhook_variations():
    """
    Generate various webhook payloads for testing different scenarios
    Returns list of test cases with different client IDs, costs, and cities
    """
    test_cases = [
        {
            "name": "standard_booking",
            "payload": {
                "id": "Q001",
                "quoteStatus": "APPROVED",
                "amounts": {"totalPrice": 720.00},  # 4-hour job
                "client": {
                    "id": "C001",
                    "properties": [{"city": "Saskatoon"}]
                }
            }
        },
        {
            "name": "high_value_booking",
            "payload": {
                "id": "Q002",
                "quoteStatus": "APPROVED",
                "amounts": {"totalPrice": 2880.00},  # 2-day job
                "client": {
                    "id": "C002",
                    "properties": [{"city": "Warman"}]
                }
            }
        },
        {
            "name": "small_booking",
            "payload": {
                "id": "Q003",
                "quoteStatus": "APPROVED",
                "amounts": {"totalPrice": 180.00},  # 1-hour job
                "client": {
                    "id": "C003",
                    "properties": [{"city": "Emma Lake"}]
                }
            }
        },
        {
            "name": "rejected_quote",
            "payload": {
                "id": "Q004",
                "quoteStatus": "REJECTED",
                "amounts": {"totalPrice": 500.00},
                "client": {
                    "id": "C004",
                    "properties": [{"city": "Saskatoon"}]
                }
            }
        }
    ]
    return test_cases


def generate_mock_calander_data():
    """
    Generate mock data that would exist in the calander table
    Returns list of dictionaries matching calander table structure
    """
    base_date = datetime.now()
    mock_entries = []

    for i in range(5):
        date = base_date + timedelta(days=i)
        start_time = date.replace(hour=9 + (i * 2), minute=0, second=0, microsecond=0)
        finish_time = start_time + timedelta(hours=2)

        entry = {
            "date": start_time.strftime("%Y-%m-%d"),
            "client_id": f"C{100 + i}",
            "start_time": start_time.isoformat(),
            "finish_time": finish_time.isoformat()
        }
        mock_entries.append(entry)

    return mock_entries