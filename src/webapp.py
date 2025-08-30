import os  # Added for TEST_MODE
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
import httpx
from datetime import datetime, timedelta
from src.api.scheduler import auto_book, is_workday, estimate_time
from src.api.jobber_client import create_job, notify_team, notify_client
from src.api.rescheduler import cancel_appointment, run_daily_weather_check, compact_schedule, \
    check_weather_impact_on_schedule
from config.settings import JOBBER_CLIENT_ID, JOBBER_CLIENT_SECRET, JOBBER_API_KEY
import secrets
from fastapi.responses import HTMLResponse
from testing.mock_data import generate_mock_webhook  # Already there
from src.db import init_db, get_visits, add_visit  # Already there


# -------------------
# TEST MODE (dynamic)
# -------------------
def in_test_mode() -> bool:
    return os.getenv("TEST_MODE", "False").lower() == "true"


init_db()

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
    if in_test_mode():
        TOKENS["access_token"] = "mock_access_token"
        return JSONResponse({"status": "Mock auth successful"})
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


# -------------------
# BOOK JOB ENDPOINT
# -------------------
@app.post("/book-job")
async def book_job_endpoint(request: Request):
    """
    Event-driven webhook for quote approvals.
    Payload example:
    {
        "id": "Q123",
        "quoteStatus": "APPROVED",
        "amounts": {"totalPrice": 500.00},
        "client": {"id": "C123", "properties": [{"city": "Saskatoon"}]}
    }
    """
    # ----------------------
    # Step 1: Validate payload first
    # ----------------------
    try:
        # Always try to read the actual request data first
        data = await request.json()

        # Validate required fields immediately
        if not data or not isinstance(data, dict):
            raise HTTPException(status_code=400, detail="Empty or invalid payload")

        quote_id = data.get("id")
        status = data.get("quoteStatus")
        cost = data.get("amounts", {}).get("totalPrice")
        client_id = data.get("client", {}).get("id", "C123")  # Extract client ID

        if not quote_id:
            raise HTTPException(status_code=400, detail="Missing Quote ID")
        if not status:
            raise HTTPException(status_code=400, detail="Missing Quote Status")
        if cost is None:
            raise HTTPException(status_code=400, detail="Missing Cost")

    except HTTPException:
        raise
    except Exception as e:
        # Only use mock data if we can't parse JSON AND we're in test mode
        # AND the request body is completely empty
        if in_test_mode():
            try:
                request_body = await request.body()
                if not request_body:  # Only use mock for truly empty requests
                    data = generate_mock_webhook()["data"]
                    quote_id = data.get("id")
                    status = data.get("quoteStatus")
                    cost = data.get("amounts", {}).get("totalPrice")
                    client_id = data.get("client", {}).get("id", "C123")
                else:
                    raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {e}")
            except:
                raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")
        else:
            raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")

    # ----------------------
    # Step 2: Authentication check
    # ----------------------
    access = TOKENS.get("access_token")
    if not access and not in_test_mode():
        raise HTTPException(status_code=401, detail="Not authorized")

    # ----------------------
    # Step 3: Business logic
    # ----------------------
    if status != "APPROVED":
        return JSONResponse({"status": "Ignored - Not an approved quote"})

    # estimate duration based on cost
    estimated_duration = estimate_time(cost) if cost is not None and cost > 0 else timedelta(hours=2)
    if estimated_duration == -1:
        raise HTTPException(status_code=400, detail="Invalid quote cost")

    # find the next available slot
    start_datetime = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    while not is_workday(start_datetime):
        start_datetime += timedelta(days=1)

    city = "Saskatoon"

    visits = get_visits()
    slot = auto_book(visits, start_datetime, estimated_duration, city, client_id)
    if not slot:
        raise HTTPException(status_code=400, detail="No available slot")

    start_slot = slot["startAt"]
    end_slot = slot["endAt"]

    # Pass client_id to add_visit
    add_visit(start_slot, end_slot, client_id)

    job_response = await create_job(f"Quote {quote_id}", start_slot, end_slot,
                                    access_token=access or "mock_access_token")
    job_id = job_response["data"]["jobCreate"]["job"]["id"]
    await notify_team(job_id, f"Job scheduled: Quote {quote_id} for client {client_id} at {start_slot}",
                      access_token=access or "mock_access_token")
    await notify_client(job_id, f"Your job is booked for {start_slot} to {end_slot}",
                        access_token=access or "mock_access_token")

    return JSONResponse({
        "status": f"Quote {quote_id} approved and scheduled",
        "scheduled_start": start_slot,
        "scheduled_end": end_slot,
        "visits_count": len(get_visits()),
        "cost": cost,
        "job_id": job_id,
        "client_id": client_id
    })


# -------------------
# RESCHEDULING ENDPOINTS
# -------------------
@app.post("/cancel-appointment")
async def cancel_appointment_endpoint(request: Request):
    """
    Cancel an appointment and trigger automatic rescheduling
    Payload: {"client_id": "C123", "reason": "Customer requested cancellation"}
    """
    try:
        data = await request.json()
        client_id = data.get("client_id")
        reason = data.get("reason", "Customer cancellation")

        if not client_id:
            raise HTTPException(status_code=400, detail="Missing client_id")

        result = cancel_appointment(client_id, reason)

        # Notify about rescheduled jobs if any
        if result.get("rescheduled_jobs"):
            access_token = TOKENS.get("access_token", "mock_access_token")
            from src.api.rescheduler import notify_rescheduled_jobs
            await notify_rescheduled_jobs(result["rescheduled_jobs"], access_token)

        return JSONResponse(result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cancellation failed: {e}")


@app.get("/weather-check")
async def run_weather_check():
    """
    Manual trigger for weather-based rescheduling check
    """
    try:
        result = run_daily_weather_check("Saskatoon")

        # Notify about rescheduled jobs if any
        if result.get("rescheduled_jobs"):
            access_token = TOKENS.get("access_token", "mock_access_token")
            from src.api.rescheduler import notify_rescheduled_jobs
            await notify_rescheduled_jobs(result["rescheduled_jobs"], access_token)

        return JSONResponse(result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Weather check failed: {e}")


@app.post("/optimize-schedule")
async def optimize_schedule():
    """
    Compact and optimize the current schedule
    """
    try:
        result = compact_schedule()
        return JSONResponse(result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Schedule optimization failed: {e}")


@app.get("/weather-forecast/{city}")
async def get_weather_forecast(city: str):
    """
    Get 4-day weather forecast for a city
    """
    try:
        from src.api.weather import get_hourly_forecast
        forecast = get_hourly_forecast(city, days_ahead=4)

        if not forecast:
            raise HTTPException(status_code=404, detail=f"Weather data not available for {city}")

        return JSONResponse({
            "city": city,
            "forecast": forecast,
            "hourly_available": "hourly" in forecast,
            "daily_available": "daily" in forecast
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Weather forecast failed: {e}")


@app.get("/schedule-status")
async def get_schedule_status():
    """
    Get current schedule status and weather impact analysis
    """
    try:
        visits = get_visits()

        # Check weather impact on current schedule
        weather_affected = check_weather_impact_on_schedule(visits, "Saskatoon")

        # Separate future and past visits
        now = datetime.now()
        future_visits = [v for v in visits if datetime.fromisoformat(v['startAt']) > now]
        past_visits = [v for v in visits if datetime.fromisoformat(v['startAt']) <= now]

        return JSONResponse({
            "total_appointments": len(visits),
            "future_appointments": len(future_visits),
            "completed_appointments": len(past_visits),
            "weather_affected_jobs": len(weather_affected),
            "weather_affected_details": weather_affected,
            "schedule": visits
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Schedule status failed: {e}")


@app.get("/")
async def root():
    """
    Root endpoint with API overview
    """
    return JSONResponse({
        "service": "Shimmer & Shine - Jobber Quotes AI Scheduler",
        "version": "2.0",
        "features": [
            "Automatic quote approval processing",
            "Weather-based scheduling",
            "Client cancellation handling",
            "Automatic rescheduling",
            "4-day weather forecasts",
            "Schedule optimization"
        ],
        "endpoints": {
            "booking": "/book-job",
            "cancellation": "/cancel-appointment",
            "weather_check": "/weather-check",
            "optimize": "/optimize-schedule",
            "forecast": "/weather-forecast/{city}",
            "status": "/schedule-status"
        }
    })