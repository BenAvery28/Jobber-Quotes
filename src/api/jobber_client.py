# src/api/jobber_client.py
#
#   handles all interactions with Jobber’s GraphQL API
#   now accepts access_token dynamically for OAuth

import httpx

GQL_URL = "https://api.getjobber.com/api/graphql"

async def create_job(title, start_iso, end_iso, access_token):
    """
    Create a new job in Jobber
    """
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
            }
        }
    }

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            GQL_URL,
            json=mutation,
            headers={"Authorization": f"Bearer {access_token}"}
        )
    return r.json()



async def notify_team(job_id, message, access_token):
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
            headers={"Authorization": f"Bearer {access_token}"}
        )
    return r.json()


# there is already a pre-made message in jobber we just have to trigger it through API
async def notify_client(job_id, message, access_token):
    """Send a custom message to the client"""
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
            headers={"Authorization": f"Bearer {access_token}"}
        )
    return r.json()



async def get_quote(quote_id, access_token):
    """Fetch a quote by ID"""
    query = """
    query GetQuote($id: ID!) {
        quote(id: $id) {
            id
            client { emails { address } properties { city } }
            amounts { totalPrice }
        }
    }
    """
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            GQL_URL,
            json={"query": query, "variables": {"id": quote_id}},
            headers={"Authorization": f"Bearer {access_token}"}
        )
    return r.json()


