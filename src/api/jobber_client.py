# src/api/jobber_client.py
#
#   handles all interactions with Jobber’s GraphQL API

import os
import httpx
from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport
from config.settings import JOBBER_API_KEY, JOBBER_API_BASE

transport = RequestsHTTPTransport(
    url=JOBBER_API_BASE + '/graphql',
    headers={'Authorization': f'Bearer {JOBBER_API_KEY}'}
)
gql_client = Client(transport=transport, fetch_schema_from_transport=True)
GQL_URL = "https://api.getjobber.com/api/graphql"

def get_quote(quote_id):
    query = gql('''
    query GetQuote($id: ID!) {
        quote(id: $id) {
            id
            client { emails { address } properties { city } }
            amounts { totalPrice }
        }
    }
    ''')
    return gql_client.execute(query, variable_values={'id': quote_id})

def approve_quote(quote_id):
    mutation = gql('''
    mutation ApproveQuote($id: ID!) {
        quoteApprove(id: $id) {
            quote { id status }
            userErrors { message }
        }
    }
    ''')
    return gql_client.execute(mutation, variable_values={'id': quote_id})

async def create_job(title, start_iso, end_iso, job_type, notes=""):
    mutation = {
        "query": """
        mutation CreateJob($input: CreateJobInput!) {
          jobCreate(input: $input) {
            job { id title startAt endAt }
          }
        }""",
        "variables": {
            "input": {
                "title": title,
                "startAt": start_iso,
                "endAt": end_iso,
                "notes": notes
            }
        }
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            GQL_URL,
            json=mutation,
            headers={"Authorization": f"Bearer {JOBBER_API_KEY}"}
        )
    return r.json()


async def notify_team(job_id, message):
    """Send a message to assigned staff for a job"""
    mutation = {
        "query": """
        mutation JobUpdate($id: ID!, $input: UpdateJobInput!) {
          jobUpdate(id: $id, input: $input) {
            job { id notes }
          }
        }""",
        "variables": {"id": job_id, "input": {"notes": message}}
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            GQL_URL,
            json=mutation,
            headers={"Authorization": f"Bearer {JOBBER_API_KEY}"}
        )
    return r.json()


async def notify_client(job_id, message):
    """Send a custom message to the client"""
    # Jobber lets you update clientNotes or send messages via jobUpdate
    mutation = {
        "query": """
        mutation JobUpdate($id: ID!, $input: UpdateJobInput!) {
          jobUpdate(id: $id, input: $input) {
            job { id clientNotes }
          }
        }""",
        "variables": {"id": job_id, "input": {"clientNotes": message}}
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            GQL_URL,
            json=mutation,
            headers={"Authorization": f"Bearer {JOBBER_API_KEY}"}
        )
    return r.json()