# src/webapp.py
#
#   FastAPI server for 24/7 job scheduling using Jobber OAuth

import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
import httpx
from datetime import datetime, timedelta
from src.api.scheduler import auto_book
from src.api.jobber_client import create_job, notify_team, notify_client
from config.settings import JOBBER_CLIENT_ID, JOBBER_CLIENT_SECRET, JOBBER_API_KEY
import secrets
from fastapi.responses import HTMLResponse

# -------------------
# CONFIG / GLOBALS
# -------------------
app = FastAPI()
VISITS = []  # in-memory booked jobs list

JOBBER_CLIENT_ID = os.getenv("JOBBER_CLIENT_ID")
JOBBER_CLIENT_SECRET = os.getenv("JOBBER_CLIENT_SECRET")
REDIRECT_URI = "https://e7f222e9c2c7.ngrok-free.app/oauth/callback"  # your ngrok URL
GQL_URL = "https://api.getjobber.com/api/graphql"

if not JOBBER_CLIENT_ID:
    raise RuntimeError("JOBBER_CLIENT_ID is required!")
if not JOBBER_CLIENT_SECRET:
    raise RuntimeError("JOBBER_CLIENT_SECRET is required!")

STATE = {"value": None}
TOKENS = {}

# -------------------
# AUTH ENDPOINTS
# -------------------
@app.get("/auth")
async def start_auth():
    """Start OAuth flow by redirecting to Jobber login page"""
    STATE["value"] = secrets.token_urlsafe(24)
    url = httpx.URL(
        "https://api.getjobber.com/api/oauth/authorize",
        params={
            "client_id": JOBBER_CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "state": STATE["value"],
        },
    )
    return RedirectResponse(str(url))


@app.get("/oauth/callback")
async def oauth_callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        return HTMLResponse("<h1>No code received</h1>")

    # Exchange the code for a token
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://secure.getjobber.com/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": JOBBER_CLIENT_ID,
                "client_secret": JOBBER_CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
            },
        )
        token_data = r.json()
        TOKENS.update(token_data)
    return HTMLResponse(f"<h1>Access Token</h1><pre>{token_data}</pre>")


# -------------------
# HELPER ENDPOINTS
# -------------------
@app.get("/whoami")
async def whoami():
    """Check which Jobber account the token has access to"""
    access = TOKENS.get("access_token")
    if not access:
        raise HTTPException(status_code=401, detail="Not authorized")

    query = """query { viewer { account { id name } } }"""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            GQL_URL,
            json={"query": query},
            headers={"Authorization": f"Bearer {access}"},
        )
    return JSONResponse(r.json())


# -------------------
# MAIN WEBHOOK ENDPOINT
# -------------------
@app.post("/webhook")
async def webhook(request: Request):
    """
    Handle webhook events from Jobber, detecting approved quotes and starting the flow.
    Expected payload example (based on Jobber webhook schema):
    {
        "data": {
            "id": "Q123",
            "quoteStatus": "APPROVED"
        }
    }
    """
    access = TOKENS.get("access_token")
    if not access:
        raise HTTPException(status_code=401, detail="Not authorized")

    try:
        payload = await request.json()
        quote_id = payload.get('data', {}).get('id')
        status = payload.get('data', {}).get('quoteStatus')
        if not quote_id or not status:
            raise ValueError("Missing quote ID or status")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")

    if status != "APPROVED":
        return JSONResponse({"status": "Ignored - Not an approved quote"})

    # Mock quote data for now (replace with real get_quote later)
    quote = generate_mock_quote(quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail=f"Quote {quote_id} not found")

    # Approve the quote (mocked for now)
    approval_result = approve_quote(quote_id)
    if approval_result.get('quoteApprove', {}).get('userErrors'):
        raise HTTPException(status_code=500, detail=f"Approval failed: {approval_result['quoteApprove']['userErrors']}")

    # Extract estimated duration from quote (mocked)
    estimated_duration = quote.get('estimatedDuration', timedelta(hours=2))
    start_slot = auto_book(VISITS, datetime.now(), estimated_duration)
    if not start_slot:
        raise HTTPException(status_code=400, detail="No available slot")

    end_slot = (datetime.fromisoformat(start_slot) + estimated_duration).isoformat()
    VISITS.append({"startAt": start_slot, "endAt": end_slot})

    # Notify team and client (mocked for now, awaiting real API)
    # await notify_team(quote_id, f"Job scheduled: Quote {quote_id} at {start_slot}", access_token=access)
    # await notify_client(quote_id, f"Your job is booked for {start_slot} to {end_slot}", access_token=access)

    return JSONResponse({
        "status": f"Quote {quote_id} approved and scheduled",
        "scheduled_start": start_slot,
        "scheduled_end": end_slot,
        "visits_count": len(VISITS)
    })