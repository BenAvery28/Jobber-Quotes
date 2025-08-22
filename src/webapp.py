# src/webapp.py
# FastAPI server for 24/7 job scheduling using a service token

import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import httpx
from datetime import datetime, timedelta
from api.scheduler import auto_book  # refactor schedular file to correct spelling

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
        "job_type": "res"
    }
    """
    try:
        data = await request.json()
        title = data["title"]
        duration_hours = float(data["duration_hours"])
        job_type = data.get("job_type", "res")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")

    # scheduler determines start time automatically
    duration = timedelta(hours=int(duration_hours), minutes=(duration_hours % 1) * 60)
    start_slot_iso = auto_book(VISITS, duration, job_type)  # <- auto_book picks next available slot
    end_slot_iso = (datetime.fromisoformat(start_slot_iso) + duration).isoformat()

    # record the visit in-memory
    VISITS.append({"startAt": start_slot_iso, "endAt": end_slot_iso})

    # push the booking to Jobber
    mutation = {
        "query": """
        mutation CreateJob($input: CreateJobInput!) {
          jobCreate(input: $input) {
            job { id title startAt endAt }
          }
        }
        """,
        "variables": {
            "input": {
                "title": title,
                "startAt": start_slot_iso,
                "endAt": end_slot_iso,
                "notes": f"Auto-scheduled. Type: {job_type}"
            }
        }
    }

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            GQL_URL,
            json=mutation,
            headers={"Authorization": f"Bearer {JOBBER_API_KEY}"}
        )

    return JSONResponse({
        "scheduled_start": start_slot_iso,
        "scheduled_end": end_slot_iso,
        "visits_count": len(VISITS),
        "jobber_response": r.json()
    })
