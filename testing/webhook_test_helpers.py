# testing/webhook_test_helpers.py
"""
Helper functions for testing webhook endpoints with proper GraphQL mocking.
These helpers ensure tests accurately simulate the production flow:
1. Webhook received (minimal payload with just IDs)
2. GraphQL query to fetch full quote details
3. Processing and booking
"""

from unittest.mock import patch, AsyncMock, MagicMock
from testing.mock_data import generate_jobber_webhook, generate_mock_quote_for_graphql


def create_mock_jobber_client(quote_data=None, job_id="J_TEST", visit_id="V_TEST", 
                              create_visit_error=None):
    """
    Create a mock JobberClient for testing.
    
    Args:
        quote_data: Quote data dict (from generate_mock_quote_for_graphql)
        job_id: Mock job ID to return
        visit_id: Mock visit ID to return
        create_visit_error: Exception to raise when creating visit (for error testing)
    
    Returns:
        MagicMock configured as JobberClient
    """
    mock_client = MagicMock()
    
    # Mock get_quote to return quote data
    if quote_data:
        mock_client.get_quote = AsyncMock(return_value=quote_data)
    else:
        mock_client.get_quote = AsyncMock(return_value=generate_mock_quote_for_graphql())
    
    # Mock create_job to return job ID
    mock_client.create_job = AsyncMock(return_value={"id": job_id})
    
    # Mock create_visit
    if create_visit_error:
        mock_client.create_visit = AsyncMock(side_effect=create_visit_error)
    else:
        mock_client.create_visit = AsyncMock(return_value={"id": visit_id})
    
    return mock_client


def patch_jobber_client_for_test(quote_data=None, job_id="J_TEST", visit_id="V_TEST",
                                  create_visit_error=None):
    """
    Context manager to patch JobberClient for webhook tests.
    
    Usage:
        with patch_jobber_client_for_test(quote_data=my_quote) as mock_client:
            response = client.post("/webhook/jobber", json=webhook)
    
    Args:
        quote_data: Quote data dict (from generate_mock_quote_for_graphql)
        job_id: Mock job ID to return
        visit_id: Mock visit ID to return
        create_visit_error: Exception to raise when creating visit
    
    Returns:
        Context manager that patches JobberClient
    """
    mock_client = create_mock_jobber_client(quote_data, job_id, visit_id, create_visit_error)
    return patch('src.webapp.JobberClient', return_value=mock_client)

