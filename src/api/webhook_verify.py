# src/api/webhook_verify.py
#
#   Verifies authenticity of Jobber webhooks using HMAC-SHA256
#   Based on Jobber's documentation

import hmac
import hashlib
import base64
from config.settings import JOBBER_CLIENT_SECRET, JOBBER_CLIENT_ID


def verify_jobber_webhook(payload: bytes, signature_header: str) -> bool:
    """
    Verify that a webhook request came from Jobber.
    
    Args:
        payload: Raw request body bytes
        signature_header: Value of X-Jobber-Hmac-SHA256 header
        
    Returns:
        True if signature is valid, False otherwise
    """
    if not signature_header:
        return False
    
    if not JOBBER_CLIENT_SECRET:
        # In test mode without secret, skip verification
        return True
    
    # Calculate expected signature
    digest = hmac.new(
        key=JOBBER_CLIENT_SECRET.encode('utf-8'),
        msg=payload,
        digestmod=hashlib.sha256
    ).digest()
    
    calculated_signature = base64.b64encode(digest).decode('utf-8')
    
    # Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(calculated_signature, signature_header)


def parse_webhook_payload(data: dict) -> dict:
    """
    Parse Jobber webhook payload and extract relevant fields.
    
    Jobber webhook format:
    {
        "data": {
            "webHookEvent": {
                "topic": "QUOTE_APPROVED",
                "appId": "...",
                "accountId": "...",
                "itemId": "...",  # This is the quote/job/client ID
                "occurredAt": "2021-08-12T16:31:36-06:00"  # or "occuredAt" for older apps
            }
        }
    }
    
    Note: Older apps (before Dec 8, 2023) use "occuredAt" (typo), newer apps use "occurredAt"
    
    Returns:
        dict with topic, item_id, account_id, occurred_at
    """
    webhook_event = data.get("data", {}).get("webHookEvent", {})
    
    # Handle both "occurredAt" (newer) and "occuredAt" (older apps, typo)
    occurred_at = webhook_event.get("occurredAt") or webhook_event.get("occuredAt")
    
    return {
        "topic": webhook_event.get("topic"),
        "item_id": webhook_event.get("itemId"),
        "account_id": webhook_event.get("accountId"),
        "app_id": webhook_event.get("appId"),
        "occurred_at": occurred_at,
    }


def validate_webhook_app_id(app_id: str) -> bool:
    """
    Validate that webhook appId matches our configured client ID (optional).
    This provides an additional layer of security beyond signature verification.
    
    Args:
        app_id: The appId from the webhook event
        
    Returns:
        True if validation passes or is skipped, False if validation fails
    """
    if not JOBBER_CLIENT_ID:
        # No client ID configured, skip validation
        return True
    
    if not app_id:
        # Missing app_id in webhook - this might be expected for some events
        # Return True to allow processing (signature verification is primary check)
        return True
    
    # If app_id is provided, it should match our client ID
    # Note: This is optional - Jobber may not always include appId
    # Signature verification is the primary security mechanism
    return app_id == JOBBER_CLIENT_ID


# Webhook topics we care about (based on WebHookTopicEnum)
QUOTE_TOPICS = [
    "QUOTE_CREATE",
    "QUOTE_UPDATE",
    "QUOTE_APPROVED",  # This is likely what we need
    "QUOTE_CONVERTED",
]

JOB_TOPICS = [
    "JOB_CREATE",
    "JOB_UPDATE",
    "JOB_COMPLETE",
]

# App disconnect topic - required for App Marketplace
APP_DISCONNECT_TOPIC = "APP_DISCONNECT"

