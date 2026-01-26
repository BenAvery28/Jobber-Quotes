import os  # Added for TEST_MODE
import asyncio
import sqlite3
import json
from urllib.parse import parse_qs, unquote
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse, RedirectResponse
import httpx
from datetime import datetime, timedelta
import logging
from src.timezone_utils import now as tz_now

logger = logging.getLogger(__name__)
from src.api.scheduler import auto_book, is_workday, estimate_time
from src.api.jobber_client import create_job, notify_team, notify_client, JobberClient
from src.api.rescheduler import cancel_appointment, run_daily_weather_check, compact_schedule, \
    check_weather_impact_on_schedule, recheck_tentative_bookings
from src.api.job_classifier import classify_job_tag, get_crew_for_tag
from src.api.recurring_jobs import create_recurring_job, generate_bookings_from_recurring_job, \
    book_entire_summer
from src.api.webhook_verify import verify_jobber_webhook, parse_webhook_payload, QUOTE_TOPICS, validate_webhook_app_id
from src.db import get_recurring_jobs, deactivate_recurring_job
from config.settings import JOBBER_CLIENT_ID, JOBBER_CLIENT_SECRET, JOBBER_API_KEY
import secrets
from fastapi.responses import HTMLResponse
from testing.mock_data import generate_mock_webhook
from src.db import init_db, get_visits, add_visit, get_processed_quote, mark_quote_processed, save_token, get_token
from src.logging_config import setup_logging

# Initialize logging
setup_logging()



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
BOOK_LOCK = asyncio.Lock()  # Lock to prevent double-booking races

JOBBER_CLIENT_ID = os.getenv("JOBBER_CLIENT_ID")
JOBBER_CLIENT_SECRET = os.getenv("JOBBER_CLIENT_SECRET")
REDIRECT_URI = os.getenv("JOBBER_REDIRECT_URI", "http://localhost:8000/oauth/callback")
GQL_URL = "https://api.getjobber.com/api/graphql"

if not JOBBER_CLIENT_ID:
    raise RuntimeError("JOBBER_CLIENT_ID is required!")
if not JOBBER_CLIENT_SECRET:
    raise RuntimeError("JOBBER_CLIENT_SECRET is required!")

STATE = {"value": None}

# Helper functions for token management
def get_access_token():
    """Get access token from database, with fallback for test mode."""
    if in_test_mode():
        return "mock_access_token"
    token_data = get_token("access_token")
    if token_data and token_data.get("token"):
        return token_data["token"]
    return None

def set_access_token(token: str, expires_at: str = None):
    """Save access token to database."""
    save_token("access_token", token, expires_at)


# -------------------
# HELPER FUNCTIONS
# -------------------
def ceil_to_30(dt: datetime) -> datetime:
    """
    Round up datetime to the next 30-minute boundary.
    Examples:
        - 10:15 -> 10:30
        - 10:30 -> 10:30 (no change)
        - 10:31 -> 11:00
        - 10:00 -> 10:00 (no change)
    """
    # If minutes are already 0 or 30, return as-is
    if dt.minute == 0 or dt.minute == 30:
        return dt.replace(second=0, microsecond=0)
    
    # Round up to next 30-minute boundary
    if dt.minute < 30:
        return dt.replace(minute=30, second=0, microsecond=0)
    else:
        # Round up to next hour
        return (dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))


# -------------------
# AUTH ENDPOINTS
# -------------------
@app.get("/auth")
async def start_auth():
    """Start OAuth flow by redirecting to Jobber login page"""
    if in_test_mode():
        set_access_token("mock_access_token")
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
        client_data = data.get("client", {})
        client_id = client_data.get("id", "C123")  # Extract client ID
        client_name = client_data.get("name", "")
        
        # Extract address information for job classification
        properties = client_data.get("properties", [])
        address = ""
        if properties and len(properties) > 0:
            # Try to get address from first property
            prop = properties[0]
            address_parts = []
            if prop.get("address"):
                address_parts.append(prop.get("address"))
            if prop.get("address2"):
                address_parts.append(prop.get("address2"))
            if prop.get("city"):
                address_parts.append(prop.get("city"))
            address = ", ".join(address_parts)

        if not quote_id:
            raise HTTPException(status_code=400, detail="Missing Quote ID")
        if not status:
            raise HTTPException(status_code=400, detail="Missing Quote Status")
        if cost is None:
            raise HTTPException(status_code=400, detail="Missing Cost")
        
        # Classify job tag (commercial vs residential)
        job_tag = classify_job_tag(address=address, client_name=client_name, quote_amount=cost)
        crew_assignment = get_crew_for_tag(job_tag)

        existing = get_processed_quote(quote_id)
        if existing:
            return JSONResponse({
                "status": f"Quote {quote_id} already scheduled",
                "scheduled_start": existing["start_at"],
                "scheduled_end": existing["end_at"],
                "job_id": existing["job_id"],
                "client_id": existing["client_id"],
                "idempotent": True
            })

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
                    client_data = data.get("client", {})
                    client_id = client_data.get("id", "C123")
                    client_name = client_data.get("name", "")
                    properties = client_data.get("properties", [])
                    address = ""
                    if properties and len(properties) > 0:
                        prop = properties[0]
                        address_parts = []
                        if prop.get("address"):
                            address_parts.append(prop.get("address"))
                        if prop.get("city"):
                            address_parts.append(prop.get("city"))
                        address = ", ".join(address_parts)
                    # Classify job tag
                    job_tag = classify_job_tag(address=address, client_name=client_name, quote_amount=cost)
                    crew_assignment = get_crew_for_tag(job_tag)
                else:
                    raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {e}")
            except:
                raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")
        else:
            raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")

    # ----------------------
    # Step 2: Authentication check
    # ----------------------
    access = get_access_token()
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

    # find the next available slot - start from now rounded up to next 30-min boundary
    city = "Saskatoon"
    
    # Use lock to prevent double-booking races
    async with BOOK_LOCK:
        # Start from now, rounded up to next 30-minute boundary
        start_datetime = ceil_to_30(tz_now())
        
        # If rounded time is before 8am, set to 8am
        if start_datetime.hour < 8:
            start_datetime = start_datetime.replace(hour=8, minute=0, second=0, microsecond=0)
        # If rounded time is at or after 8pm, move to next day at 8am
        elif start_datetime.hour >= 20:
            start_datetime = (start_datetime + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
        
        # Advance to next workday if needed (Mon-Thu, excluding Fridays and holidays)
        while not is_workday(start_datetime):
            start_datetime = (start_datetime + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)

        visits = get_visits()
        slot = auto_book(visits, start_datetime, estimated_duration, city, client_id, allow_tentative=True)
        if not slot:
            raise HTTPException(status_code=400, detail="No available slot")

        start_slot = slot["startAt"]
        end_slot = slot["endAt"]
        booking_status = slot.get("booking_status", "confirmed")
        weather_confidence = slot.get("weather_confidence", "unknown")

    # Pass client_id, job_tag, and booking_status to add_visit
        add_visit(start_slot, end_slot, client_id, job_tag, booking_status)

    job_response = await create_job(f"Quote {quote_id}", start_slot, end_slot,
                                    access_token=access or "mock_access_token")
    job_id = job_response["data"]["jobCreate"]["job"]["id"]

    try:
        mark_quote_processed(quote_id, client_id, job_id, start_slot, end_slot)
    except sqlite3.IntegrityError:
        # Another worker processed it first. Return idempotent response.
        existing = get_processed_quote(quote_id)
        return JSONResponse({
            "status": f"Quote {quote_id} already scheduled",
            "scheduled_start": existing["start_at"],
            "scheduled_end": existing["end_at"],
            "job_id": existing["job_id"],
            "client_id": existing["client_id"],
            "idempotent": True
        })

    await notify_team(job_id, f"Job scheduled: Quote {quote_id} for client {client_id} at {start_slot} (crew: {crew_assignment})",
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
        "client_id": client_id,
        "job_tag": job_tag,
        "crew_assignment": crew_assignment,
        "booking_status": booking_status,
        "weather_confidence": weather_confidence
    })


# -------------------
# BACKGROUND TASK FOR WEBHOOK PROCESSING
# -------------------
async def process_webhook_background(
    item_id: str,
    quote_id: str,
    client_id: str,
    client_name: str,
    company_name: str,
    address: str,
    city: str,
    cost: float,
    property_id: str,
    job_tag: str,
    crew_assignment: str,
    estimated_duration: timedelta,
    access_token: str
):
    """
    Background task to process webhook after returning 202 to Jobber.
    This prevents webhook timeouts and allows proper retry handling.
    
    Note: Jobber requires webhook responses within 1 second, so we return 202
    immediately and process asynchronously. This also handles at-least-once
    delivery semantics (webhooks may be sent multiple times).
    """
    try:
        logger.info(f"Processing webhook in background for quote {quote_id}")
        
        # Re-check idempotency (race condition protection)
        existing = get_processed_quote(quote_id)
        if existing:
            logger.info(f"Quote {quote_id} already processed (idempotent check)")
            return
        
        # Book the job
        async with BOOK_LOCK:
            start_datetime = ceil_to_30(tz_now())
            
            if start_datetime.hour < 8:
                start_datetime = start_datetime.replace(hour=8, minute=0, second=0, microsecond=0)
            elif start_datetime.hour >= 20:
                start_datetime = (start_datetime + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
            
            while not is_workday(start_datetime):
                start_datetime = (start_datetime + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
            
            visits = get_visits()
            slot = auto_book(visits, start_datetime, estimated_duration, city, client_id, allow_tentative=True)
            
            if not slot:
                logger.error(f"No available slot found for quote {quote_id}")
                return
            
            start_slot = slot["startAt"]
            end_slot = slot["endAt"]
            booking_status = slot.get("booking_status", "confirmed")
            weather_confidence = slot.get("weather_confidence", "unknown")
            
            add_visit(start_slot, end_slot, client_id, job_tag, booking_status)
        
        # Create job in Jobber
        client = JobberClient(access_token or "mock_access_token")
        job_title = f"Quote {quote_id}"
        job = await client.create_job(job_title, client_id, property_id)
        job_id = job.get("id", f"J_{quote_id}")
        
        # Create visit in Jobber - must succeed before marking as processed
        try:
            visit = await client.create_visit(
                job_id=job_id,
                start_at=start_slot,
                end_at=end_slot,
                title=job_title
            )
            visit_id = visit.get("id") if visit else None
        except Exception as e:
            # Visit creation failed - rollback local booking
            from src.db import remove_visit_by_name
            remove_visit_by_name(client_id)
            logger.error(f"Could not create visit in Jobber: {e}. Local booking rolled back.", exc_info=True)
            raise
        
        # Mark as processed (with idempotency check)
        try:
            mark_quote_processed(quote_id, client_id, job_id, start_slot, end_slot)
        except sqlite3.IntegrityError:
            # Another worker processed it first
            logger.info(f"Quote {quote_id} already processed by another worker")
            return
        
        # Notify team and client
        await notify_team(job_id, f"Job scheduled: {job_title} for {client_name or company_name} at {start_slot} (crew: {crew_assignment})",
                          access_token=access_token or "mock_access_token")
        await notify_client(job_id, f"Your job is booked for {start_slot} to {end_slot}",
                            access_token=access_token or "mock_access_token")
        
        logger.info(f"Successfully processed webhook for quote {quote_id}, job {job_id}")
        
    except Exception as e:
        logger.error(f"Error processing webhook for quote {quote_id}: {e}", exc_info=True)
        # Don't re-raise - we've already returned 202 to Jobber
        # The error is logged for monitoring/alerting


# -------------------
# JOBBER WEBHOOK ENDPOINT (Production)
# -------------------
@app.post("/webhook/jobber")
async def jobber_webhook_endpoint(request: Request, background_tasks: BackgroundTasks):
    """
    Production webhook endpoint for Jobber events.
    
    IMPORTANT: Jobber requires webhook responses within 1 second. This endpoint
    returns 202 Accepted immediately and processes the webhook asynchronously
    in a background task to meet this requirement.
    
    Jobber webhook format:
    {
        "data": {
            "webHookEvent": {
                "topic": "QUOTE_APPROVED",
                "appId": "...",
                "accountId": "...",
                "itemId": "...",  # The quote/job/client ID
                "occurredAt": "2021-08-12T16:31:36-06:00"  # or "occuredAt" for older apps
            }
        }
    }
    
    Supports both:
    - application/json (newer apps, after Apr 11, 2022)
    - application/x-www-form-urlencoded (older apps, before Apr 11, 2022)
    
    Handles at-least-once delivery: webhooks may be sent multiple times, so
    idempotency checks are performed before processing.
    
    We then query the Jobber API to get full details.
    """
    # ----------------------
    # Step 1: Get raw body for signature verification (must be done before parsing)
    # ----------------------
    raw_body = await request.body()
    
    # ----------------------
    # Step 2: Verify webhook signature
    # ----------------------
    if not in_test_mode():
        signature = request.headers.get("X-Jobber-Hmac-SHA256", "")
        
        if not verify_jobber_webhook(raw_body, signature):
            logger.warning("Invalid webhook signature - rejecting request")
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
    
    # ----------------------
    # Step 3: Parse webhook payload (handle both JSON and form-urlencoded)
    # ----------------------
    content_type = request.headers.get("content-type", "").lower()
    
    try:
        if "application/json" in content_type:
            # Newer apps (after Apr 11, 2022) send JSON
            data = json.loads(raw_body.decode('utf-8'))
        elif "application/x-www-form-urlencoded" in content_type:
            # Older apps (before Apr 11, 2022) send form-urlencoded
            form_data = parse_qs(raw_body.decode('utf-8'))
            # Jobber sends the payload in a 'data' field as a JSON string
            if 'data' in form_data and form_data['data']:
                data_str = unquote(form_data['data'][0])
                data = json.loads(data_str)
            else:
                raise HTTPException(status_code=400, detail="Missing 'data' field in form-urlencoded payload")
        else:
            # Try JSON as fallback (for unknown content types)
            data = json.loads(raw_body.decode('utf-8'))
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.error(f"Failed to parse webhook payload: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Invalid webhook payload: {e}")
    
    webhook_event = parse_webhook_payload(data)
    topic = webhook_event.get("topic")
    item_id = webhook_event.get("item_id")
    app_id = webhook_event.get("app_id")
    
    if not topic or not item_id:
        raise HTTPException(status_code=400, detail="Missing topic or itemId in webhook")
    
    # Optional: Validate app_id matches our client ID (additional security layer)
    if not validate_webhook_app_id(app_id):
        raise HTTPException(status_code=401, detail="Invalid appId in webhook")
    
    # ----------------------
    # Step 3: Handle different webhook topics
    # ----------------------
    
    # Only process quote-related topics
    if topic not in QUOTE_TOPICS:
        return JSONResponse({
            "status": "ignored",
            "reason": f"Topic {topic} not handled",
            "topic": topic
        })
    
    # Early idempotency check with item_id (before API call)
    existing = get_processed_quote(item_id)
    if existing:
        return JSONResponse({
            "status": f"Quote {item_id} already scheduled",
            "scheduled_start": existing["start_at"],
            "scheduled_end": existing["end_at"],
            "job_id": existing["job_id"],
            "client_id": existing["client_id"],
            "idempotent": True
        })
    
    # ----------------------
    # Step 4: Get access token and fetch quote details
    # ----------------------
    access = get_access_token()
    if not access and not in_test_mode():
        raise HTTPException(status_code=401, detail="Not authorized - no access token")
    
    # Fetch full quote details from Jobber API
    client = JobberClient(access or "mock_access_token")
    quote = await client.get_quote(item_id)
    
    if not quote:
        raise HTTPException(status_code=404, detail=f"Quote {item_id} not found in Jobber")
    
    # ----------------------
    # Step 5: Extract booking data from quote
    # ----------------------
    quote_id = quote.get("id", item_id)
    quote_status = quote.get("quoteStatus", "").lower()
    
    # Re-check idempotency with actual quote_id (in case item_id != quote_id)
    if quote_id != item_id:
        existing = get_processed_quote(quote_id)
        if existing:
            return JSONResponse({
                "status": f"Quote {quote_id} already scheduled",
                "scheduled_start": existing["start_at"],
                "scheduled_end": existing["end_at"],
                "job_id": existing["job_id"],
                "client_id": existing["client_id"],
                "idempotent": True
            })
    cost = quote.get("amounts", {}).get("totalPrice", 0)
    
    client_data = quote.get("client", {})
    client_id = client_data.get("id", "C123")
    client_name = client_data.get("name") or f"{client_data.get('firstName', '')} {client_data.get('lastName', '')}".strip()
    company_name = client_data.get("companyName", "")
    
    # Get address from quote property, client property, or billing address
    property_data = quote.get("property", {}) or {}
    if not property_data:
        client_properties = client_data.get("clientProperties", {}).get("nodes", [])
        if client_properties:
            property_data = client_properties[0]
    property_id = property_data.get("id")
    address_data = property_data.get("address", {}) or client_data.get("billingAddress", {})
    
    address = ", ".join(filter(None, [
        address_data.get("street"),
        address_data.get("city"),
        address_data.get("province"),
        address_data.get("postalCode")
    ]))
    city = address_data.get("city", "Saskatoon")
    
    # Only process approved quotes
    if quote_status != "approved":
        return JSONResponse({
            "status": "ignored",
            "reason": f"Quote status is {quote_status}, not approved",
            "quote_id": quote_id
        })
    
    # ----------------------
    # Step 6: Classify job and prepare for background processing
    # ----------------------
    job_tag = classify_job_tag(
        address=address,
        client_name=client_name or company_name,
        quote_amount=cost
    )
    crew_assignment = get_crew_for_tag(job_tag)
    
    estimated_duration = estimate_time(cost) if cost > 0 else timedelta(hours=2)
    if estimated_duration == -1:
        raise HTTPException(status_code=400, detail="Invalid quote cost")
    
    # ----------------------
    # Step 7: Queue background task and return 202 immediately
    # ----------------------
    background_tasks.add_task(
        process_webhook_background,
        item_id=item_id,
        quote_id=quote_id,
        client_id=client_id,
        client_name=client_name,
        company_name=company_name,
        address=address,
        city=city,
        cost=cost,
        property_id=property_id,
        job_tag=job_tag,
        crew_assignment=crew_assignment,
        estimated_duration=estimated_duration,
        access_token=access or "mock_access_token"
    )
    
    logger.info(f"Webhook accepted for quote {quote_id}, processing in background")
    
    # Return 202 Accepted immediately (Jobber requires response within 1 second)
    # Background task will handle the actual processing asynchronously
    return JSONResponse(
        {
            "status": "accepted",
            "message": f"Quote {quote_id} queued for processing",
            "quote_id": quote_id
        },
        status_code=202
    )


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
            access_token = get_access_token() or "mock_access_token"
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
            access_token = get_access_token() or "mock_access_token"
            from src.api.rescheduler import notify_rescheduled_jobs
            await notify_rescheduled_jobs(result["rescheduled_jobs"], access_token)

        return JSONResponse(result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Weather check failed: {e}")


@app.get("/recheck-tentative-bookings")
async def recheck_tentative():
    """
    Recheck tentative bookings and reshuffle if weather improves or deteriorates.
    This is the pseudo-reshuffler endpoint.
    """
    try:
        result = recheck_tentative_bookings("Saskatoon")
        return JSONResponse(result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tentative booking recheck failed: {e}")


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
        now = tz_now()
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


@app.post("/recurring-jobs")
async def create_recurring_job_endpoint(request: Request):
    """
    Create a recurring job template and optionally book the entire summer.
    Payload:
    {
        "client_id": "C123",
        "day_of_week": 0,  # 0=Monday, 1=Tuesday, 2=Wednesday, 3=Thursday
        "start_time": "10:00",  # HH:MM format
        "duration_hours": 2.0,
        "start_date": "2025-06-01",  # YYYY-MM-DD (optional, defaults to first Monday of month)
        "end_date": "2025-08-31",  # YYYY-MM-DD (optional, defaults to Aug 31)
        "job_tag": "residential",  # optional
        "book_now": true  # If true, immediately generate all bookings
    }
    """
    try:
        data = await request.json()
        
        client_id = data.get("client_id")
        day_of_week = data.get("day_of_week")
        start_time = data.get("start_time")
        duration_hours = data.get("duration_hours")
        start_date = data.get("start_date")
        end_date = data.get("end_date")
        job_tag = data.get("job_tag", "residential")
        book_now = data.get("book_now", False)
        
        if not client_id:
            raise HTTPException(status_code=400, detail="Missing client_id")
        if day_of_week is None:
            raise HTTPException(status_code=400, detail="Missing day_of_week")
        if not start_time:
            raise HTTPException(status_code=400, detail="Missing start_time")
        if duration_hours is None:
            raise HTTPException(status_code=400, detail="Missing duration_hours")
        
        if day_of_week not in [0, 1, 2, 3]:
            raise HTTPException(status_code=400, detail="day_of_week must be 0-3 (Mon-Thu)")
        
        # Create recurring job
        recurring_job_id = create_recurring_job(
            client_id, day_of_week, start_time, duration_hours,
            start_date or None, end_date or None, job_tag
        )
        
        result = {
            "recurring_job_id": recurring_job_id,
            "client_id": client_id,
            "day_of_week": day_of_week,
            "start_time": start_time,
            "duration_hours": duration_hours,
            "job_tag": job_tag
        }
        
        # If book_now is True, generate all bookings immediately
        if book_now:
            booking_result = generate_bookings_from_recurring_job(
                recurring_job_id, city="Saskatoon", check_weather=True, skip_conflicts=True
            )
            result["bookings_generated"] = booking_result
        
        return JSONResponse(result)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create recurring job: {e}")


@app.get("/recurring-jobs")
async def list_recurring_jobs(client_id: str = None, active_only: bool = True):
    """
    List recurring job templates.
    Query params:
        client_id: Filter by client ID (optional)
        active_only: Only show active recurring jobs (default True)
    """
    try:
        recurring_jobs = get_recurring_jobs(client_id=client_id, active_only=active_only)
        return JSONResponse({
            "count": len(recurring_jobs),
            "recurring_jobs": recurring_jobs
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list recurring jobs: {e}")


@app.post("/recurring-jobs/{recurring_job_id}/generate-bookings")
async def generate_bookings_endpoint(recurring_job_id: int):
    """
    Generate individual bookings from a recurring job template.
    Books all occurrences between start_date and end_date.
    """
    try:
        result = generate_bookings_from_recurring_job(
            recurring_job_id, city="Saskatoon", check_weather=True, skip_conflicts=True
        )
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate bookings: {e}")


@app.post("/recurring-jobs/{recurring_job_id}/deactivate")
async def deactivate_recurring_job_endpoint(recurring_job_id: int):
    """
    Deactivate a recurring job (soft delete).
    """
    try:
        updated = deactivate_recurring_job(recurring_job_id)
        if updated == 0:
            raise HTTPException(status_code=404, detail=f"Recurring job {recurring_job_id} not found")
        return JSONResponse({
            "recurring_job_id": recurring_job_id,
            "status": "deactivated"
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to deactivate recurring job: {e}")


@app.post("/recurring-jobs/book-summer")
async def book_entire_summer_endpoint(request: Request):
    """
    Convenience endpoint to create a recurring job and book the entire summer in one call.
    Payload:
    {
        "client_id": "C123",
        "day_of_week": 0,  # 0=Monday, 1=Tuesday, 2=Wednesday, 3=Thursday
        "start_time": "10:00",  # HH:MM format
        "duration_hours": 2.0,
        "job_tag": "residential",  # optional
        "start_date": "2025-06-01",  # optional
        "end_date": "2025-08-31"  # optional
    }
    """
    try:
        data = await request.json()
        
        client_id = data.get("client_id")
        day_of_week = data.get("day_of_week")
        start_time = data.get("start_time")
        duration_hours = data.get("duration_hours")
        job_tag = data.get("job_tag", "residential")
        start_date = data.get("start_date")
        end_date = data.get("end_date")
        
        if not client_id:
            raise HTTPException(status_code=400, detail="Missing client_id")
        if day_of_week is None:
            raise HTTPException(status_code=400, detail="Missing day_of_week")
        if not start_time:
            raise HTTPException(status_code=400, detail="Missing start_time")
        if duration_hours is None:
            raise HTTPException(status_code=400, detail="Missing duration_hours")
        
        if day_of_week not in [0, 1, 2, 3]:
            raise HTTPException(status_code=400, detail="day_of_week must be 0-3 (Mon-Thu)")
        
        result = book_entire_summer(
            client_id, day_of_week, start_time, duration_hours,
            job_tag, start_date, end_date
        )
        
        return JSONResponse(result)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to book summer: {e}")


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