# src/api/jobber_client.py
#
#   handles all interactions with Jobber’s GraphQL API
#   now accepts access_token dynamically for OAuth

import os  # Added for TEST_MODE
from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport
from config.settings import JOBBER_API_BASE, JOBBER_API_KEY
import asyncio
from datetime import datetime
from testing.mock_data import generate_mock_quote  # Added for mocks in TEST_MODE

TEST_MODE = os.getenv("TEST_MODE", "False").lower() == "true"  # Added to toggle mock mode

# Mock setup (replace with real OAuth token and API base when available)
ACCESS_TOKEN = "mock_token"  # From TOKENS in webapp.py
transport = RequestsHTTPTransport(
    url=JOBBER_API_BASE + '/graphql',
    headers={'Authorization': f'Bearer {ACCESS_TOKEN}'}
)

gql_client = Client(transport=transport, fetch_schema_from_transport=True)


async def create_job(title, start_slot, end_slot, access_token):
    """
    Create a job in the Jobber calendar with the scheduled info.
    Args:
        title (str): Job title.
        start_slot (str): ISO 8601 start time.
        end_slot (str): ISO 8601 end time.
        access_token (str): OAuth token for authentication.
    Returns:
        dict: Mock response with job details based on Job type.
    """
    mutation = gql("""
        mutation CreateJob($input: JobCreateInput!) {
            jobCreate(input: $input) {
                job {
                    id
                    title
                    startAt
                    endAt
                    client {
                        id
                        name
                    }
                    property {
                        id
                    }
                }
                userErrors { message }
            }
        }
    """)
    # Mock input data (replace with real client/property IDs later)
    input_data = {
        "input": {
            "title": title,
            "startAt": start_slot,
            "endAt": end_slot,
            "clientId": "C123",  # Mock client ID
            "propertyId": "P123"  # Mock property ID
        }
    }
    if TEST_MODE:
        # Simulate API call in test mode
        await asyncio.sleep(0.1)  # Mock delay
        return {
            "data": {
                "jobCreate": {
                    "job": {
                        "id": f"J{title.replace(' ', '_')}",
                        "title": title,
                        "startAt": start_slot,
                        "endAt": end_slot,
                        "client": {"id": "C123", "name": "Test Client"},
                        "property": {"id": "P123"}
                    },
                    "userErrors": []
                }
            }
        }
    else:
        # Real API call (uncomment and use when approved)
        # result = await gql_client.execute_async(mutation, variable_values=input_data)
        # return result
        raise NotImplementedError("Real Jobber API not available yet - set TEST_MODE=True")

async def notify_team(job_id, message, access_token):
    """
    Notify the team via Jobber messaging.
    Args:
        job_id (str): ID of the job to notify about.
        message (str): Message content.
        access_token (str): OAuth token for authentication.
    Returns:
        dict: Mock response indicating success.
    """
    # Mock GraphQL mutation (real schema TBD)
    mutation = gql("""
        mutation NotifyTeam($input: NotifyInput!) {
            notifyTeam(input: $input) {
                success
                message
            }
        }
    """)
    input_data = {"input": {"jobId": job_id, "message": message}}
    if TEST_MODE:
        await asyncio.sleep(0.1)  # Mock delay
        return {"success": True, "message": f"Team notified for job {job_id}"}
    else:
        # Real API call (uncomment when approved)
        # result = await gql_client.execute_async(mutation, variable_values=input_data)
        # return result
        raise NotImplementedError("Real Jobber API not available yet - set TEST_MODE=True")

async def notify_client(job_id, message, access_token):
    """
    Notify the client via Jobber messaging.
    Args:
        job_id (str): ID of the job to notify about.
        message (str): Message content.
        access_token (str): OAuth token for authentication.
    Returns:
        dict: Mock response indicating success.
    """
    # Mock GraphQL mutation (real schema TBD)
    mutation = gql("""
        mutation NotifyClient($input: NotifyInput!) {
            notifyClient(input: $input) {
                success
                message
            }
        }
    """)
    input_data = {"input": {"jobId": job_id, "message": message}}
    if TEST_MODE:
        await asyncio.sleep(0.1)  # Mock delay
        return {"success": True, "message": f"Client notified for job {job_id}"}
    else:
        # Real API call (uncomment when approved)
        # result = await gql_client.execute_async(mutation, variable_values=input_data)
        # return result
        raise NotImplementedError("Real Jobber API not available yet - set TEST_MODE=True")