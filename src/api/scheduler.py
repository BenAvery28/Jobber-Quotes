# scheduler.py
#
# Full scheduling system:
# - Checks availability
# - Finds next open slot (Mon–Fri, 9–5)
# - Respects holidays and grace periods
# - Books jobs and updates visit list
# - Prepares data to send to Jobber

from datetime import datetime, timedelta
from src.api.weather import check_weather
from src.db import get_visits, add_visit

# 30-minute grace period between bookings
WORK_START = 8  # 8 am
WORK_END = 20  # 8 pm (20:00)
grace_period = timedelta(minutes=30)

# List of holidays that will NEVER be booked (format: "YYYY-MM-DD")
# Add dates like: "2026-06-28", "2026-12-25", etc.
HOLIDAYS = [
    # Example: "2026-06-28",
    # Add more holidays as needed
]


def is_workday(d):
    """
    Return True if the given date is a weekday (Mon–Thu, excluding Fridays) and not a holiday.
    Fridays are excluded as buffer days for rain/touchups.
    """
    weekday = d.weekday()  # monday = 0, sunday = 6
    
    # Exclude weekends (Saturday=5, Sunday=6) and Fridays (Friday=4)
    # Only Monday-Thursday are bookable (0-3)
    is_weekday = weekday < 4  # Monday=0, Tuesday=1, Wednesday=2, Thursday=3
    
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


def auto_book(visits, start_date, duration, city, client_id=None):
    """
    Find the next available slot for a job.
    - Only books on weekdays (Mon–Thu, excluding Fridays)
    - Checks weather before booking
    - Uses 30-min increments within 8am–8pm
    - Stops searching after 30 days
    Args:
        visits (list): Current bookings
        start_date (datetime): Starting point to search
        duration (timedelta): Job length
        city (str): City (for weather check)
        client_id (str): Client ID from Jobber (optional)
    Returns:
        dict: {"startAt": str, "endAt": str}
        None: No slot found
    """

    d = start_date.replace(hour=WORK_START, minute=0, second=0, microsecond=0)

    # add a safety limit to prevent infinite loops
    max_days_to_check = 30
    days_checked = 0

    while days_checked < max_days_to_check:
        if is_workday(d):
            if check_weather(city, d, WORK_START, WORK_END):
                day_start = d.replace(hour=WORK_START, minute=0)
                day_end = d.replace(hour=WORK_END, minute=0)
                slot = day_start
                while slot + duration <= day_end:
                    if check_availability(slot, duration, visits):  # Pass visits
                        start_at = slot.isoformat()
                        end_at = (slot + duration).isoformat()
                        # Note: add_visit is called from webapp.py with client_id
                        return {"startAt": start_at, "endAt": end_at}
                    slot += timedelta(minutes=30)

        d = (d + timedelta(days=1)).replace(hour=WORK_START, minute=0, second=0, microsecond=0)
        days_checked += 1

    # return none if no slot found after max days
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