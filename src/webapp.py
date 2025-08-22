# src/webapp.py
# FastAPI server for 24/7 job scheduling using a service token

import os
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import httpx
from api.schedular import auto_book

app = FastAPI()
VISITS = []  # in-memory list of scheduled jobs

JOBBER_API_KEY = os.getenv("JOBBER_API_KEY")
GQL_URL = "https://api.getjobber.com/api/graphql"

if not JOBBER_API_KEY:
    raise RuntimeError("JOBBER_API_KEY is missing !")

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


@app.post("/book-job")
async def book_job_endpoint(request: Request):
    """
    Schedule a job automatically when a quote is approved.
    Payload:
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

    duration = timedelta(hours=int(duration_hours), minutes=(duration_hours % 1) * 60)

    # scheduler picks the next available slot automatically
    start_slot_iso = auto_book(VISITS, duration, job_type)
    end_slot_iso = (datetime.fromisoformat(start_slot_iso) + duration).isoformat()

    # record when its scheduled
    VISITS.append({"startAt": start_slot_iso, "endAt": end_slot_iso})

    # send back to Jobber
    async with httpx.AsyncClient(timeout=30) as client:
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