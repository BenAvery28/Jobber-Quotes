#testing/mock_data.py
import random
from datetime import datetime, timedelta

def generate_mock_quote(quote_id=None):
    """
    Generate a mock Jobber quote (something like this will be input when an order is filled)
    params:
     - quote_id (str, optional): if none, generates a random quote id
    Returns:
     - dictionary quote containing: id, client (email + city), amount (total price)
    """

    if quote_id is None:
        quote_id = f"Q{random.randint(100, 999)}"

    return {
        "id": quote_id,
        "client": {
            "emails": [{"address": f"client{random.randint(1, 10)}@example.com"}],
            "properties": [{"city": random.choice(["Saskatoon, Warman, Emma Lake"])}]
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
    """

    return [
        {
            "startAt": (datetime.now() + timedelta(days=i)).isoformat(),
            "endAt": (datetime.now() + timedelta(days=i, hours=2)).isoformat()
        }
        for i in range(count)
    ]

def generate_mock_webhook(quote_id=None):
    """
    Generate a mock Jobber webhook payload for testing with a fixed approved quote.
    """
    if quote_id is None or quote_id != "Q123":
        quote_id = "Q123"
    status = "APPROVED"
    return {
        "data": {
            "id": quote_id,
            "quoteStatus": status,
            "amounts": {"totalPrice": 500.00},
            "client": {"properties": [{"city": "Saskatoon"}]}
        }
    }