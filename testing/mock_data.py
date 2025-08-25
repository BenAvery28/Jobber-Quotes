import random
from datetime import datetime, timedelta

def generate_mock_quote(quote_id=None):
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
            "amounts": {"totalPrice": 500.00}
        }
    }