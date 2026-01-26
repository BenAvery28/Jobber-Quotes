# src/api/jobber_client.py
#
#   Handles all interactions with Jobber's GraphQL API
#   Uses OAuth access tokens for authentication

import os
import asyncio
import httpx
from datetime import datetime
from config.settings import JOBBER_GRAPHQL_URL, JOBBER_CLIENT_SECRET
from src.api.retry import retry_with_backoff
import logging

logger = logging.getLogger(__name__)

TEST_MODE = os.getenv("TEST_MODE", "False").lower() == "true"


class JobberClient:
    """
    Client for interacting with Jobber's GraphQL API.
    All requests go to https://api.getjobber.com/api/graphql
    """
    
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
    
    async def _execute_query(self, query: str, variables: dict = None) -> dict:
        """Execute a GraphQL query/mutation against Jobber API with retry logic."""
        if TEST_MODE:
            return self._mock_response(query, variables)
        
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        
        async def _make_request():
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    JOBBER_GRAPHQL_URL,
                    json=payload,
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
        
        # Retry with exponential backoff for network errors and 5xx errors
        return await retry_with_backoff(
            _make_request,
            max_retries=3,
            initial_delay=1.0,
            max_delay=30.0,
            exceptions=(httpx.HTTPError, httpx.HTTPStatusError),
            on_retry=lambda attempt, error, delay: logger.warning(
                f"Jobber API request failed (attempt {attempt}), retrying in {delay}s: {error}"
            )
        )
    
    def _mock_response(self, query: str, variables: dict = None) -> dict:
        """Return mock responses for testing."""
        # Detect query type and return appropriate mock
        if "quote(" in query.lower() or "quotes" in query.lower():
            return self._mock_quote_response(variables)
        elif "jobcreate" in query.lower():
            return self._mock_job_create_response(variables)
        elif "visitcreate" in query.lower():
            return self._mock_visit_create_response(variables)
        return {"data": {}}
    
    def _mock_quote_response(self, variables: dict = None) -> dict:
        """Mock quote query response."""
        return {
            "data": {
                "quote": {
                    "id": variables.get("id", "Q123") if variables else "Q123",
                    "quoteNumber": 1001,
                    "quoteStatus": "approved",
                    "title": "Window Cleaning Service",
                    "amounts": {
                        "totalPrice": 500.00,
                        "subtotal": 500.00,
                    },
                    "client": {
                        "id": "C123",
                        "name": "John Doe",
                        "isCompany": False,
                        "firstName": "John",
                        "lastName": "Doe",
                        "companyName": None,
                        "billingAddress": {
                            "city": "Saskatoon",
                            "street": "123 Main St",
                            "postalCode": "S7K 1A1",
                            "province": "SK",
                        },
                        "clientProperties": {
                            "nodes": [
                                {
                                    "id": "P123",
                                    "address": {
                                        "city": "Saskatoon",
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
                            {"address": "john.doe@example.com", "primary": True}
                        ],
                    },
                    "property": {
                        "id": "P123",
                        "address": {
                            "city": "Saskatoon",
                            "street": "123 Main St",
                            "postalCode": "S7K 1A1",
                            "province": "SK",
                        },
                    },
                }
            }
        }
    
    def _mock_job_create_response(self, variables: dict = None) -> dict:
        """Mock job create mutation response."""
        input_data = variables.get("input", {}) if variables else {}
        return {
            "data": {
                "jobCreate": {
                    "job": {
                        "id": f"J{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        "title": input_data.get("title", "New Job"),
                        "jobNumber": 2001,
                        "jobStatus": "requires_invoicing",
                        "client": {
                            "id": input_data.get("clientId", "C123"),
                        },
                    },
                    "userErrors": []
                }
            }
        }
    
    def _mock_visit_create_response(self, variables: dict = None) -> dict:
        """Mock visit create mutation response."""
        input_data = variables.get("input", {}) if variables else {}
        return {
            "data": {
                "visitCreate": {
                    "visit": {
                        "id": f"V{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        "startAt": input_data.get("startAt"),
                        "endAt": input_data.get("endAt"),
                        "title": input_data.get("title", "Scheduled Visit"),
                    },
                    "userErrors": []
                }
            }
        }
    
    # ==================
    # QUERIES
    # ==================
    
    async def get_quote(self, quote_id: str) -> dict:
        """
        Fetch quote details by ID.
        
        Args:
            quote_id: The Jobber quote ID (from webhook itemId)
            
        Returns:
            Quote data including client, property, amounts
        """
        query = """
        query GetQuote($id: EncodedId!) {
            quote(id: $id) {
                id
                quoteNumber
                quoteStatus
                title
                amounts {
                    totalPrice
                    subtotal
                }
                client {
                    id
                    name
                    isCompany
                    firstName
                    lastName
                    companyName
                    billingAddress {
                        city
                        street
                        postalCode
                        province
                    }
                    clientProperties {
                        nodes {
                            id
                            address {
                                city
                                street
                                postalCode
                                province
                            }
                        }
                    }
                    phones {
                        number
                        primary
                    }
                    emails {
                        address
                        primary
                    }
                }
                property {
                    id
                    address {
                        city
                        street
                        postalCode
                        province
                    }
                }
            }
        }
        """
        result = await self._execute_query(query, {"id": quote_id})
        return result.get("data", {}).get("quote")
    
    async def get_client(self, client_id: str) -> dict:
        """Fetch client details by ID."""
        query = """
        query GetClient($id: EncodedId!) {
            client(id: $id) {
                id
                name
                isCompany
                firstName
                lastName
                companyName
                billingAddress {
                    city
                    street
                    postalCode
                    province
                }
                clientProperties {
                    nodes {
                        id
                        address {
                            city
                            street
                            postalCode
                            province
                        }
                    }
                }
                phones {
                    number
                    primary
                }
                emails {
                    address
                    primary
                }
            }
        }
        """
        result = await self._execute_query(query, {"id": client_id})
        return result.get("data", {}).get("client")
    
    # ==================
    # MUTATIONS
    # ==================
    
    async def create_job(self, title: str, client_id: str, property_id: str = None) -> dict:
        """
        Create a job in Jobber.
        
        Args:
            title: Job title
            client_id: Jobber client ID
            property_id: Jobber property ID (optional)
            
        Returns:
            Created job data
        """
        mutation = """
        mutation CreateJob($input: JobCreateInput!) {
            jobCreate(input: $input) {
                job {
                    id
                    title
                    jobNumber
                    jobStatus
                    client {
                        id
                    }
                }
                userErrors {
                    message
                    path
                }
            }
        }
        """
        input_data = {
            "title": title,
            "clientId": client_id,
        }
        if property_id:
            input_data["propertyId"] = property_id
        
        result = await self._execute_query(mutation, {"input": input_data})
        
        # Check for errors
        job_create = result.get("data", {}).get("jobCreate", {})
        if job_create.get("userErrors"):
            errors = job_create["userErrors"]
            raise ValueError(f"Jobber API errors: {errors}")
        
        return job_create.get("job")
    
    async def create_visit(
        self,
        job_id: str,
        start_at: str,
        end_at: str,
        title: str = None,
        instructions: str = None,
        team_member_ids: list = None
    ) -> dict:
        """
        Create a scheduled visit for a job.
        
        Args:
            job_id: Jobber job ID
            start_at: ISO 8601 start datetime
            end_at: ISO 8601 end datetime
            title: Visit title (optional)
            instructions: Instructions for the team (optional)
            team_member_ids: List of team member IDs to assign (optional)
            
        Returns:
            Created visit data
        """
        # Note: The exact mutation structure depends on Jobber's schema
        # This is our best guess based on their patterns
        mutation = """
        mutation CreateVisit($input: VisitCreateInput!) {
            visitCreate(input: $input) {
                visit {
                    id
                    startAt
                    endAt
                    title
                }
                userErrors {
                    message
                    path
                }
            }
        }
        """
        input_data = {
            "jobId": job_id,
            "startAt": start_at,
            "endAt": end_at,
        }
        if title:
            input_data["title"] = title
        if instructions:
            input_data["instructions"] = instructions
        if team_member_ids:
            input_data["assignedUserIds"] = team_member_ids
        
        result = await self._execute_query(mutation, {"input": input_data})
        
        visit_create = result.get("data", {}).get("visitCreate", {})
        if visit_create.get("userErrors"):
            errors = visit_create["userErrors"]
            raise ValueError(f"Jobber API errors: {errors}")
        
        return visit_create.get("visit")
    
    async def reschedule_visit(
        self,
        visit_id: str,
        start_at: str,
        end_at: str
    ) -> dict:
        """
        Reschedule an existing visit.
        
        Args:
            visit_id: Jobber visit ID
            start_at: New ISO 8601 start datetime
            end_at: New ISO 8601 end datetime
            
        Returns:
            Updated visit data
        """
        mutation = """
        mutation RescheduleVisit($visitId: EncodedId!, $input: VisitRescheduleInput!) {
            visitReschedule(visitId: $visitId, input: $input) {
                visit {
                    id
                    startAt
                    endAt
                }
                userErrors {
                    message
                    path
                }
            }
        }
        """
        result = await self._execute_query(mutation, {
            "visitId": visit_id,
            "input": {
                "startAt": start_at,
                "endAt": end_at,
            }
        })
        
        visit_reschedule = result.get("data", {}).get("visitReschedule", {})
        if visit_reschedule.get("userErrors"):
            errors = visit_reschedule["userErrors"]
            raise ValueError(f"Jobber API errors: {errors}")
        
        return visit_reschedule.get("visit")


# ==================
# LEGACY FUNCTIONS (for backward compatibility)
# ==================

async def create_job(title, start_slot, end_slot, access_token):
    """
    Legacy function - creates a job with a visit.
    Maintained for backward compatibility with existing code.
    """
    client = JobberClient(access_token)
    
    if TEST_MODE:
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
    
    # In production, we'd create a job then a visit
    # For now, raise an error until we have real API access
    raise NotImplementedError("Real Jobber API not available yet - set TEST_MODE=True")


async def notify_team(job_id, message, access_token):
    """
    Notify the team about a job.
    Note: Jobber's actual notification mechanism may differ.
    """
    if TEST_MODE:
        await asyncio.sleep(0.1)
        return {"success": True, "message": f"Team notified for job {job_id}"}
    
    raise NotImplementedError("Real Jobber API not available yet - set TEST_MODE=True")


async def notify_client(job_id, message, access_token):
    """
    Notify the client about a job.
    Note: Jobber's actual notification mechanism may differ.
    """
    if TEST_MODE:
        await asyncio.sleep(0.1)
        return {"success": True, "message": f"Client notified for job {job_id}"}
    
    raise NotImplementedError("Real Jobber API not available yet - set TEST_MODE=True")
