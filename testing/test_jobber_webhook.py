# testing/test_jobber_webhook.py
"""
Tests for Jobber webhook integration.
Tests the production webhook format and signature verification.
"""
import os
import hmac
import hashlib
import base64
import json
import pytest
from unittest import mock
from datetime import datetime

# Set test mode before importing modules
os.environ["TEST_MODE"] = "True"
os.environ["JOBBER_CLIENT_ID"] = "test_client_id"
os.environ["JOBBER_CLIENT_SECRET"] = "test_secret_key"
os.environ["OPENWEATHER_API_KEY"] = "test_weather_key"

from src.api.webhook_verify import (
    verify_jobber_webhook,
    parse_webhook_payload,
    QUOTE_TOPICS,
    JOB_TOPICS
)
from testing.mock_data import generate_jobber_webhook


class TestWebhookSignatureVerification:
    """Tests for HMAC-SHA256 webhook signature verification."""
    
    def test_valid_signature(self):
        """Valid signature should return True."""
        secret = "test_secret_key"
        payload = b'{"data": {"webHookEvent": {"topic": "QUOTE_APPROVED"}}}'
        
        # Calculate expected signature
        digest = hmac.new(secret.encode(), payload, hashlib.sha256).digest()
        signature = base64.b64encode(digest).decode()
        
        with mock.patch('src.api.webhook_verify.JOBBER_CLIENT_SECRET', secret):
            result = verify_jobber_webhook(payload, signature)
            assert result is True
    
    def test_invalid_signature(self):
        """Invalid signature should return False."""
        secret = "test_secret_key"
        payload = b'{"data": {"webHookEvent": {"topic": "QUOTE_APPROVED"}}}'
        wrong_signature = "wrong_signature_here"
        
        with mock.patch('src.api.webhook_verify.JOBBER_CLIENT_SECRET', secret):
            result = verify_jobber_webhook(payload, wrong_signature)
            assert result is False
    
    def test_empty_signature(self):
        """Empty signature should return False."""
        payload = b'{"data": {}}'
        result = verify_jobber_webhook(payload, "")
        assert result is False
    
    def test_none_signature(self):
        """None signature should return False."""
        payload = b'{"data": {}}'
        result = verify_jobber_webhook(payload, None)
        assert result is False
    
    def test_missing_secret_allows_verification(self):
        """If no client secret is configured, verification passes (test mode)."""
        payload = b'{"data": {}}'
        
        with mock.patch('src.api.webhook_verify.JOBBER_CLIENT_SECRET', None):
            result = verify_jobber_webhook(payload, "any_signature")
            assert result is True


class TestWebhookPayloadParsing:
    """Tests for parsing Jobber webhook payloads."""
    
    def test_parse_valid_payload(self):
        """Should extract all fields from valid payload."""
        payload = {
            "data": {
                "webHookEvent": {
                    "topic": "QUOTE_APPROVED",
                    "appId": "app-123",
                    "accountId": "ACC-456",
                    "itemId": "Q789",
                    "occurredAt": "2025-01-26T10:30:00-06:00"
                }
            }
        }
        
        result = parse_webhook_payload(payload)
        
        assert result["topic"] == "QUOTE_APPROVED"
        assert result["item_id"] == "Q789"
        assert result["account_id"] == "ACC-456"
        assert result["app_id"] == "app-123"
        assert result["occurred_at"] == "2025-01-26T10:30:00-06:00"
    
    def test_parse_empty_payload(self):
        """Should handle empty payload gracefully."""
        result = parse_webhook_payload({})
        
        assert result["topic"] is None
        assert result["item_id"] is None
    
    def test_parse_missing_webhook_event(self):
        """Should handle missing webHookEvent."""
        payload = {"data": {"other": "stuff"}}
        result = parse_webhook_payload(payload)
        
        assert result["topic"] is None
        assert result["item_id"] is None


class TestWebhookTopics:
    """Tests for webhook topic constants."""
    
    def test_quote_topics_exist(self):
        """QUOTE_TOPICS should contain expected topics."""
        assert "QUOTE_APPROVED" in QUOTE_TOPICS
        assert "QUOTE_CREATE" in QUOTE_TOPICS
        assert "QUOTE_UPDATE" in QUOTE_TOPICS
    
    def test_job_topics_exist(self):
        """JOB_TOPICS should contain expected topics."""
        assert "JOB_CREATE" in JOB_TOPICS
        assert "JOB_UPDATE" in JOB_TOPICS


class TestMockWebhookGeneration:
    """Tests for the mock webhook generator."""
    
    def test_generate_default_webhook(self):
        """Should generate webhook with default values."""
        webhook = generate_jobber_webhook()
        
        assert "data" in webhook
        assert "webHookEvent" in webhook["data"]
        
        event = webhook["data"]["webHookEvent"]
        assert event["topic"] == "QUOTE_APPROVED"
        assert event["itemId"] == "Q123"
        assert "occurredAt" in event
    
    def test_generate_custom_webhook(self):
        """Should generate webhook with custom values."""
        webhook = generate_jobber_webhook(
            topic="QUOTE_CREATE",
            item_id="CUSTOM_ID"
        )
        
        event = webhook["data"]["webHookEvent"]
        assert event["topic"] == "QUOTE_CREATE"
        assert event["itemId"] == "CUSTOM_ID"


class TestJobberWebhookFormat:
    """Tests to verify our understanding of Jobber's webhook format."""
    
    def test_webhook_contains_only_ids(self):
        """
        Jobber webhooks only contain IDs, not full entity data.
        This test documents this important behavior.
        """
        webhook = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id="Q123")
        event = webhook["data"]["webHookEvent"]
        
        # Webhook should NOT contain full quote data
        assert "amounts" not in event
        assert "client" not in event
        assert "totalPrice" not in event
        
        # Should only have reference IDs
        assert "itemId" in event
        assert "accountId" in event
    
    def test_webhook_requires_api_query_for_details(self):
        """
        Document that we need to query the API after receiving a webhook.
        """
        # This is a documentation test - the webhook only gives us the ID
        webhook = generate_jobber_webhook(topic="QUOTE_APPROVED", item_id="Q123")
        item_id = webhook["data"]["webHookEvent"]["itemId"]
        
        # To get quote details, we'd need to call:
        # client = JobberClient(access_token)
        # quote = await client.get_quote(item_id)
        
        assert item_id == "Q123"


class TestSignatureCalculation:
    """Tests that match Jobber's documented signature calculation."""
    
    def test_signature_matches_jobber_docs_example(self):
        """
        Test our signature calculation matches Jobber's documented example.
        From their docs:
        verify_webhook(
            '{"data":{"webHookEvent":{"topic":"APP_CONNECT",...}}}',
            "ks1dre6TCHsMO2GVWnDYmx3ZrxubXGbCNZ5gPiXvP9E="
        )
        """
        # We can't reproduce their exact example without their secret,
        # but we can verify our algorithm works correctly
        secret = "my_test_secret"
        payload = b'{"data":{"webHookEvent":{"topic":"APP_CONNECT"}}}'
        
        # Calculate signature our way
        digest = hmac.new(secret.encode(), payload, hashlib.sha256).digest()
        our_signature = base64.b64encode(digest).decode()
        
        # Verify it validates
        with mock.patch('src.api.webhook_verify.JOBBER_CLIENT_SECRET', secret):
            assert verify_jobber_webhook(payload, our_signature) is True
            # And a wrong signature fails
            assert verify_jobber_webhook(payload, "wrong") is False


class TestWebhookAppIdValidation:
    """Tests for appId validation."""
    
    def test_validate_app_id_matches_client_id(self):
        """App ID should match client ID when both are provided."""
        from src.api.webhook_verify import validate_webhook_app_id
        
        with mock.patch('src.api.webhook_verify.JOBBER_CLIENT_ID', 'test_client_123'):
            assert validate_webhook_app_id('test_client_123') is True
            assert validate_webhook_app_id('wrong_id') is False
    
    def test_validate_app_id_skips_when_no_client_id(self):
        """Validation should pass when no client ID is configured."""
        from src.api.webhook_verify import validate_webhook_app_id
        
        with mock.patch('src.api.webhook_verify.JOBBER_CLIENT_ID', None):
            assert validate_webhook_app_id('any_app_id') is True
            assert validate_webhook_app_id(None) is True
    
    def test_validate_app_id_allows_missing_app_id(self):
        """Validation should pass when app_id is missing (optional field)."""
        from src.api.webhook_verify import validate_webhook_app_id
        
        with mock.patch('src.api.webhook_verify.JOBBER_CLIENT_ID', 'test_client_123'):
            assert validate_webhook_app_id(None) is True
            assert validate_webhook_app_id('') is True

