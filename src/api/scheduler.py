# scheduler.py
#
# Full scheduling system:
# - Checks availability
# - Finds next open slot (Mon–Thu, 8–8)
# - Respects holidays and grace periods
# - Books jobs and updates visit list
# - Prepares data to send to Jobber
# - Cascading Job Size Scheduling: prioritizes large/medium jobs and preserves capacity

from datetime import datetime, timedelta
from src.api.weather import check_weather, check_weather_with_confidence
from src.db import get_visits, add_visit
from enum import Enum

# 30-minute grace period between bookings
WORK_START = 8  # 8 am
WORK_END = 20  # 8 pm
grace_period = timedelta(minutes=30)

# Job size categories for cascading scheduling
class JobSize(Enum):
    LARGE = "large"   # 8 hours (full day)
    MEDIUM = "medium" # 4 hours (half day)
    SMALL = "small"   # < 4 hours

# List of holidays that will NEVER be booked (format: "YYYY-MM-DD")
# Add dates like: "2026-06-28", "2026-12-25", etc.
HOLIDAYS = [
    # Example: "2026-06-28",
    # Add more holidays as needed
]


def is_workday(d, allow_friday=False):
    """
    Return True if the given date is a weekday (Mon–Thu, optionally Friday) and not a holiday.
    Fridays are excluded as buffer days for rain/touchups, but can be used for reschedules.
    
    Args:
        d: datetime to check
        allow_friday: If True, Friday is allowed (for reschedules). Default False (new bookings skip Friday).
    """
    weekday = d.weekday()  # monday = 0, sunday = 6
    
    # Exclude weekends (Saturday=5, Sunday=6)
    # For new bookings: exclude Friday (weekday < 4)
    # For reschedules: allow Friday (weekday < 5)
    if allow_friday:
        is_weekday = weekday < 5  # Monday=0 through Friday=4
    else:
        is_weekday = weekday < 4  # Monday=0 through Thursday=3
    
    if not is_weekday:
        return False
    
    # Check if date is in holidays list
    date_str = d.strftime("%Y-%m-%d")
    if date_str in HOLIDAYS:
        return False
    
    return True


def estimate_time(quote_cost: float):
    """
    Estimate job time based on cost.
    Rules:
      - Full day = $1440 = 8 hours
      - 4-hour chunk = $720
      - Hourly crew rate = $180
      Returns:
       time delta: estimated job completion time frame
       -1: invalid input
    """
    if quote_cost <= 0:
        return -1  # invalid quote

    # try to use full days first
    days = quote_cost // 1440
    remainder = quote_cost % 1440

    # try 4-hour chunks next
    chunks = remainder // 720
    remainder = remainder % 720

    # remaining hours at $180/hour
    hours = remainder / 180  # remainder should always be divisible by 180 cleanly

    total_hours = int(days) * 8 + int(chunks) * 4 + hours
    return timedelta(hours=total_hours)


def categorize_job_size(duration: timedelta) -> JobSize:
    """
    Categorize job by duration for cascading scheduling.
    Args:
        duration: Job duration as timedelta
    Returns:
        JobSize enum: LARGE (8h), MEDIUM (4h), or SMALL (<4h)
    """
    hours = duration.total_seconds() / 3600
    
    if hours >= 8:
        return JobSize.LARGE
    elif hours >= 4:
        return JobSize.MEDIUM
    else:
        return JobSize.SMALL


def check_availability(start_time, duration, visits):
    """
    Check if a time slot is available.
    Args:
        start_time (datetime): Start of the slot.
        duration (timedelta): Duration of the job.
        visits (list): List of booked visits.
    Returns:
        bool: True if slot is free, False otherwise.
    """

    end_time = start_time + duration
    for visit in visits:  # Use passed visits instead of get_visits()
        visit_start = datetime.fromisoformat(visit['startAt']) - grace_period
        visit_end = datetime.fromisoformat(visit['endAt']) + grace_period
        if not (end_time <= visit_start or start_time >= visit_end):
            return False
    return True


def _get_day_free_blocks(day_date: datetime, visits: list) -> list:
    """
    Get free time blocks for a given day, accounting for grace periods.
    Returns list of (start, end) tuples for free blocks.
    """
    day_start = day_date.replace(hour=WORK_START, minute=0, second=0, microsecond=0)
    day_end = day_date.replace(hour=WORK_END, minute=0, second=0, microsecond=0)
    
    # Get all booked slots for this day with grace periods
    booked_slots = []
    for visit in visits:
        visit_start = datetime.fromisoformat(visit['startAt']) - grace_period
        visit_end = datetime.fromisoformat(visit['endAt']) + grace_period
        
        # Only consider slots on the same day
        if visit_start.date() == day_date.date():
            booked_slots.append((visit_start, visit_end))
    
    # Sort by start time
    booked_slots.sort(key=lambda x: x[0])
    
    # Find free blocks
    free_blocks = []
    current_start = day_start
    
    for booked_start, booked_end in booked_slots:
        if current_start < booked_start:
            # Free block before this booking
            free_blocks.append((current_start, booked_start))
        current_start = max(current_start, booked_end)
    
    # Add final free block if any
    if current_start < day_end:
        free_blocks.append((current_start, day_end))
    
    return free_blocks


def _calculate_fragmentation_score(day_date: datetime, visits: list, proposed_slot_start: datetime, 
                                   proposed_slot_end: datetime) -> float:
    """
    Calculate fragmentation score for placing a job in a slot.
    Lower score is better (less fragmentation).
    
    Penalties:
    - Small gaps (< 90 minutes) are penalized heavily
    - Eliminating last 4h block on day is penalized heavily
    - Eliminating ability to place 8h block is penalized heavily
    
    Args:
        day_date: The day being evaluated
        visits: Current bookings
        proposed_slot_start: Start of proposed slot
        proposed_slot_end: End of proposed slot
    Returns:
        float: Fragmentation score (lower is better)
    """
    # Create hypothetical visits list with proposed slot
    hypothetical_visits = visits.copy()
    hypothetical_visits.append({
        'startAt': proposed_slot_start.isoformat(),
        'endAt': proposed_slot_end.isoformat()
    })
    
    # Get free blocks after placing this job
    free_blocks = _get_day_free_blocks(day_date, hypothetical_visits)
    
    score = 0.0
    
    # Penalize small gaps (unusable fragments)
    for block_start, block_end in free_blocks:
        block_duration = (block_end - block_start).total_seconds() / 3600  # hours
        if block_duration < 1.5:  # Less than 90 minutes
            score += 100.0 * (1.5 - block_duration)  # Heavier penalty for smaller gaps
    
    # Check if we can still place a 4h block
    can_place_4h = any(
        (block_end - block_start).total_seconds() >= 4 * 3600 + grace_period.total_seconds() * 2
        for block_start, block_end in free_blocks
    )
    if not can_place_4h:
        score += 200.0  # Heavy penalty for eliminating last 4h block
    
    # Check if we can still place an 8h block
    can_place_8h = any(
        (block_end - block_start).total_seconds() >= 8 * 3600 + grace_period.total_seconds() * 2
        for block_start, block_end in free_blocks
    )
    if not can_place_8h:
        score += 300.0  # Very heavy penalty for eliminating 8h block capability
    
    # Count number of gaps (more gaps = more fragmentation)
    score += len(free_blocks) * 10.0
    
    return score


def _get_medium_job_preferred_blocks(day_date: datetime) -> list:
    """
    Get preferred block-aligned start times for medium (4h) jobs.
    Preferred blocks:
    - 8:00-12:00 (4h)
    - 12:30-16:30 (4h, accounting for 30min grace)
    - 16:00-20:00 (4h)
    """
    day_start = day_date.replace(hour=WORK_START, minute=0, second=0, microsecond=0)
    
    preferred = [
        day_start,  # 8:00
        day_start + timedelta(hours=4, minutes=30),  # 12:30 (4h + 30min grace)
        day_start + timedelta(hours=8),  # 16:00
    ]
    
    return preferred


def auto_book(visits, start_date, duration, city, client_id=None, allow_tentative=True, allow_friday=False):
    """
    Find the next available slot for a job using Cascading Job Size Scheduling.
    
    Cascading Placement Priority:
    1. LARGE (8h) jobs: Prefer 8:00 AM starts on earliest Mon-Thu day, contiguous placement
    2. MEDIUM (4h) jobs: Prefer block-aligned half-day chunks (8-12, 12:30-16:30, 16-20)
    3. SMALL (<4h) jobs: Place in gaps but preserve capacity for at least one 8h or 4h block
    
    - Only books on weekdays (Mon–Thu by default, optionally Friday for reschedules)
    - Checks weather with confidence levels before booking
    - Creates tentative bookings for uncertain weather (can be reshuffled later)
    - Uses fragmentation scoring to preserve capacity
    - Stops searching after 30 days
    
    Args:
        visits (list): Current bookings
        start_date (datetime): Starting point to search
        duration (timedelta): Job length
        city (str): City (for weather check)
        client_id (str): Client ID from Jobber (optional)
        allow_tentative (bool): If True, allow tentative bookings for uncertain weather
        allow_friday (bool): If True, allow Friday bookings (for reschedules only). Default False.
    Returns:
        dict: {"startAt": str, "endAt": str, "booking_status": str, "weather_confidence": str}
        None: No slot found
    """
    job_size = categorize_job_size(duration)
    d = start_date.replace(hour=WORK_START, minute=0, second=0, microsecond=0)

    # Safety limit to prevent infinite loops
    max_days_to_check = 30
    days_checked = 0
    
    # Track best slots by weather confidence
    best_confirmed_slot = None
    best_tentative_slot = None
    best_slot_score = float('inf')  # Lower is better for fragmentation

    while days_checked < max_days_to_check:
        if is_workday(d, allow_friday=allow_friday):
            # Check weather with confidence levels
            weather_check = check_weather_with_confidence(city, d, WORK_START, WORK_END)
            
            # Only proceed if weather is suitable (even if uncertain)
            if weather_check['suitable']:
                candidate_slots = []
                
                # Generate candidate slots based on job size
                if job_size == JobSize.LARGE:
                    # LARGE jobs: Prefer 8:00 AM start, contiguous placement
                    preferred_start = d.replace(hour=WORK_START, minute=0, second=0, microsecond=0)
                    if check_availability(preferred_start, duration, visits):
                        candidate_slots.append(preferred_start)
                    
                    # Also check other 30-min increments if preferred doesn't work
                    day_start = d.replace(hour=WORK_START, minute=0, second=0, microsecond=0)
                    day_end = d.replace(hour=WORK_END, minute=0, second=0, microsecond=0)
                    slot = day_start
                    while slot + duration <= day_end:
                        if slot != preferred_start and check_availability(slot, duration, visits):
                            candidate_slots.append(slot)
                        slot += timedelta(minutes=30)
                
                elif job_size == JobSize.MEDIUM:
                    # MEDIUM jobs: Prefer block-aligned half-day chunks
                    preferred_starts = _get_medium_job_preferred_blocks(d)
                    
                    # Try preferred blocks first
                    for preferred_start in preferred_starts:
                        if preferred_start + duration <= d.replace(hour=WORK_END, minute=0, second=0, microsecond=0):
                            if check_availability(preferred_start, duration, visits):
                                candidate_slots.append(preferred_start)
                    
                    # Also check other 30-min increments
                    day_start = d.replace(hour=WORK_START, minute=0, second=0, microsecond=0)
                    day_end = d.replace(hour=WORK_END, minute=0, second=0, microsecond=0)
                    slot = day_start
                    while slot + duration <= day_end:
                        if slot not in preferred_starts and check_availability(slot, duration, visits):
                            candidate_slots.append(slot)
                        slot += timedelta(minutes=30)
                
                else:  # SMALL jobs
                    # SMALL jobs: Check all available slots, but score by fragmentation
                    day_start = d.replace(hour=WORK_START, minute=0, second=0, microsecond=0)
                    day_end = d.replace(hour=WORK_END, minute=0, second=0, microsecond=0)
                    slot = day_start
                    while slot + duration <= day_end:
                        if check_availability(slot, duration, visits):
                            candidate_slots.append(slot)
                        slot += timedelta(minutes=30)
                
                # Evaluate candidate slots
                for slot_start in candidate_slots:
                    slot_end = slot_start + duration
                    
                    # Calculate fragmentation score (only for small jobs)
                    if job_size == JobSize.SMALL:
                        frag_score = _calculate_fragmentation_score(d, visits, slot_start, slot_end)
                    else:
                        frag_score = 0.0  # Large/medium jobs don't need fragmentation scoring
                    
                    # Determine booking status based on weather confidence
                    slot_data = {
                        "startAt": slot_start.isoformat(),
                        "endAt": slot_end.isoformat(),
                        "frag_score": frag_score,
                        "slot_start": slot_start
                    }
                    
                    if weather_check['confidence'] == 'high':
                        slot_data["booking_status"] = "confirmed"
                        slot_data["weather_confidence"] = "high"
                        # For confirmed slots, prefer earlier dates and lower fragmentation
                        if best_confirmed_slot is None or (slot_start < best_confirmed_slot["slot_start"] and frag_score < best_slot_score):
                            best_confirmed_slot = slot_data
                            best_slot_score = frag_score
                    elif weather_check['confidence'] == 'medium':
                        slot_data["booking_status"] = "confirmed"
                        slot_data["weather_confidence"] = "medium"
                        # For confirmed slots, prefer earlier dates and lower fragmentation
                        if best_confirmed_slot is None or (slot_start < best_confirmed_slot["slot_start"] and frag_score < best_slot_score):
                            best_confirmed_slot = slot_data
                            best_slot_score = frag_score
                    elif allow_tentative and weather_check['confidence'] == 'low':
                        slot_data["booking_status"] = "tentative"
                        slot_data["weather_confidence"] = "low"
                        # Store best tentative slot
                        if best_tentative_slot is None or frag_score < best_slot_score:
                            best_tentative_slot = slot_data
                            best_slot_score = frag_score

        d = (d + timedelta(days=1)).replace(hour=WORK_START, minute=0, second=0, microsecond=0)
        days_checked += 1

    # Return best confirmed slot if found
    if best_confirmed_slot:
        return {
            "startAt": best_confirmed_slot["startAt"],
            "endAt": best_confirmed_slot["endAt"],
            "booking_status": best_confirmed_slot["booking_status"],
            "weather_confidence": best_confirmed_slot["weather_confidence"]
        }
    
    # Return best tentative slot if no confirmed slot and tentative allowed
    if best_tentative_slot and allow_tentative:
        return {
            "startAt": best_tentative_slot["startAt"],
            "endAt": best_tentative_slot["endAt"],
            "booking_status": best_tentative_slot["booking_status"],
            "weather_confidence": best_tentative_slot["weather_confidence"]
        }

    # No slot found
    return None


def auto_debook(client_id):
    """
    Remove a booking by client ID.
    Args:
        client_id (str): Client ID to remove bookings for
    Returns:
        int: Number of bookings removed
    """
    from src.db import remove_visit_by_name
    return remove_visit_by_name(client_id)