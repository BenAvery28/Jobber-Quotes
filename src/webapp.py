# src/webapp.py
# FastAPI server for 24/7 job scheduling using a service token

import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import httpx
from datetime import datetime, timedelta
from api.scheduler import auto_book
from api.jobber_client import create_job, notify_team, notify_client
import asyncio

# -------------------
# CONFIG / GLOBALS
# -------------------
app = FastAPI()
VISITS = []  # in memory booked jobs list
JOBBER_API_KEY = os.getenv("JOBBER_API_KEY")
GQL_URL = "https://api.getjobber.com/api/graphql"

if not JOBBER_API_KEY:
    raise RuntimeError("JOBBER_API_KEY environment variable is required!")

# -------------------
# HELPER ENDPOINTS
# -------------------
@app.get("/whoami")
async def whoami():
    """Check which Jobber account the token has access to"""
    query = """query { viewer { account { id name } } }"""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            GQL_URL,
            json={"query": query},
            headers={"Authorization": f"Bearer {JOBBER_API_KEY}"}
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
    try:
        data = await request.json()
        title = data["title"]
        duration_hours = float(data["duration_hours"])
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")

    # scheduler determines next start time
    duration = timedelta(hours=int(duration_hours), minutes=(duration_hours % 1) * 60)
    start_slot_iso = auto_book(VISITS, duration)
    end_slot_iso = (datetime.fromisoformat(start_slot_iso) + duration).isoformat()

    # record the visit in-memory
    VISITS.append({"startAt": start_slot_iso, "endAt": end_slot_iso})

    # 1. create the Job in Jobber
    job_response = await create_job(title, start_slot_iso, end_slot_iso)
    try:
        job_id = job_response["data"]["jobCreate"]["job"]["id"]
    except KeyError:
        raise HTTPException(status_code=500, detail=f"Failed to create job: {job_response}")

    # 2. notify team
    await notify_team(job_id, f"Job scheduled: {title} at {start_slot_iso}")

    # 3. notify client
    await notify_client(job_id, f"Your job '{title}' is booked for {start_slot_iso} to {end_slot_iso}")

    return JSONResponse({
        "scheduled_start": start_slot_iso,
        "scheduled_end": end_slot_iso,
        "job_id": job_id,
        "visits_count": len(VISITS)
    })