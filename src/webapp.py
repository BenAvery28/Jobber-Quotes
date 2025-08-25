# src/webapp.py
#
#   FastAPI server for 24/7 job scheduling using Jobber OAuth

import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
import httpx
from datetime import datetime, timedelta
from src.api.scheduler import auto_book, is_workday, estimate_time
from src.api.jobber_client import create_job, notify_team, notify_client
from config.settings import JOBBER_CLIENT_ID, JOBBER_CLIENT_SECRET, JOBBER_API_KEY
import secrets
from fastapi.responses import HTMLResponse
from testing.mock_data import generate_mock_webhook


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
            "quoteStatus": "APPROVED",
            "amounts": {"totalPrice": 500.00}
        }
    }
    """
    # we dont have this for testing cause the oauth flow isnt setup so commenteds out for now
    access = TOKENS.get("access_token")
    #if not access:
        #raise HTTPException(status_code=401, detail="Not authorized")

    try:
        payload = await request.json()
        webhook_data = generate_mock_webhook()  # generating mock data for testing

        quote_id = webhook_data.get('data', {}).get('id')
        status = webhook_data.get('data', {}).get('quoteStatus')
        cost = webhook_data.get('data', {}).get('amounts', {}).get('totalPrice')

        # checks
        if not quote_id:
            raise ValueError("Missing quote ID")
        elif not status:
            raise ValueError("Missing status")
        elif not cost:
            raise ValueError("Missing Cost")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")

    # debugging
    #print("Webhook received request")

    if status != "APPROVED":
        return JSONResponse({"status": "Ignored - Not an approved quote"})

    # mock quote data for now until real API access
    quote = generate_mock_webhook(quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail=f"Quote {quote_id} not found")

    # estimate duration based on cost using scheduler's function
    estimated_duration = estimate_time(cost) if cost is not None and cost > 0 else timedelta(hours=2)
    if estimated_duration == -1:
        raise HTTPException(status_code=400, detail="Invalid quote cost")

    # find the next available slot with weather check
    start_datetime = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    while not is_workday(start_datetime):
        start_datetime += timedelta(days=1)

    # lol
    city = "Saskatoon"

    slot = auto_book(VISITS, start_datetime, estimated_duration, city)
    if not slot:
        raise HTTPException(status_code=400, detail="No available slot")

    start_slot = slot["startAt"]
    end_slot = slot["endAt"]
    VISITS.append({"startAt": start_slot, "endAt": end_slot})

    # create job in jobber  calendar and notify team + client
    job_response = await create_job(f"Quote {quote_id}", start_slot, end_slot, access_token=access)
    job_id = job_response["data"]["jobCreate"]["job"]["id"]
    await notify_team(job_id, f"Job scheduled: Quote {quote_id} at {start_slot}", access_token=access)
    await notify_client(job_id, f"Your job is booked for {start_slot} to {end_slot}", access_token=access)

    return JSONResponse({
        "status": f"Quote {quote_id} approved and scheduled",
        "scheduled_start": start_slot,
        "scheduled_end": end_slot,
        "visits_count": len(VISITS),
        "cost": cost,
        "job_id": job_id
    })