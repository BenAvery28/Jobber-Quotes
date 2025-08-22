# src/webapp.py
# FastAPI server for 24/7 job scheduling using Jobber OAuth

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
@app.post("/book-job")
async def book_job_endpoint(request: Request):
    """
    Event-driven webhook for quote approvals.
    Payload example:
    {
        "title": "Window Cleaning",
        "duration_hours": 2.5,
    }
    """
    access = TOKENS.get("access_token")
    if not access:
        raise HTTPException(status_code=401, detail="Not authorized")

    try:
        data = await request.json()
        title = data["title"]
        duration_hours = float(data["duration_hours"])
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")

    # scheduler determines next start time
    duration = timedelta(hours=int(duration_hours), minutes=(duration_hours % 1) * 60)
    start_slot_iso = auto_book(VISITS, datetime.now(), duration)
    end_slot_iso = (datetime.fromisoformat(start_slot_iso) + duration).isoformat()

    # record the visit in-memory
    VISITS.append({"startAt": start_slot_iso, "endAt": end_slot_iso})

    # 1. create the Job in Jobber
    job_response = await create_job(title, start_slot_iso, end_slot_iso, access_token=access)
    try:
        job_id = job_response["data"]["jobCreate"]["job"]["id"]
    except KeyError:
        raise HTTPException(status_code=500, detail=f"Failed to create job: {job_response}")

    # 2. notify team
    await notify_team(job_id, f"Job scheduled: {title} at {start_slot_iso}", access_token=access)

    # 3. notify client
    await notify_client(job_id, f"Your job '{title}' is booked for {start_slot_iso} to {end_slot_iso}", access_token=access)

    return JSONResponse({
        "scheduled_start": start_slot_iso,
        "scheduled_end": end_slot_iso,
        "job_id": job_id,
        "visits_count": len(VISITS)
    })