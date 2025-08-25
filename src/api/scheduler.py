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

# 30-minute grace period between bookings
WORK_START = 9  # 9 am
WORK_END = 17  # 5 pm
grace_period = timedelta(minutes=30)

def is_workday(d):
    """
    Return True if the given date is a weekday (Mon–Fri) and not a holiday.
    """
    weekday = d.weekday()  # monday = 0, sunday = 6 ( will I ever get use to it? )
    date_str = d.strftime("%Y-%m-%d")

    is_weekday = weekday < 5   # cause 5 and 6 are sat and sun !

    return is_weekday

def estimate_time(quote_cost: float):
    """
    Estimate job time based on quote cost.
    Rules:
      - Full day = $1440 = 8 hours
      - 4-hour chunk = $720
      - Hourly crew rate = $180
    """
    if quote_cost <= 0:
        return -1  # invalid quote

    # try to use full days
    days = quote_cost // 1440
    remainder = quote_cost % 1440

    # try 4-hour chunks
    chunks = remainder // 720
    remainder = remainder % 720

    # hourly
    hours = remainder / 180   # remainder should always be divisible by 180 cleanly

    return timedelta(days=int(days), hours=int(chunks * 4 + hours))

def check_availability(visits, start_time, duration):
    """
    Check if a time slot is available, considering grace periods.
    visits = list of dicts with 'startAt' and 'endAt' in ISO 8601 format.
    """
    end_time = start_time + duration
    for visit in visits:
        visit_start = datetime.fromisoformat(visit['startAt']) - grace_period
        visit_end = datetime.fromisoformat(visit['endAt']) + grace_period
        if not (end_time <= visit_start or start_time >= visit_end):
            return False
    return True

def auto_book(visits, start_date, duration, city):
    """
    Find the next available time slot for a job, checking weather conditions.
    Returns dict with ISO strings for start and end.
    """
    d = start_date.replace(hour=WORK_START, minute=0, second=0, microsecond=0)

    while True:
        if is_workday(d):
            if check_weather(city, d, WORK_START, WORK_END):
                day_start = d.replace(hour=WORK_START, minute=0)
                day_end = d.replace(hour=WORK_END, minute=0)

                slot = day_start
                while slot + duration <= day_end:
                    if check_availability(visits, slot, duration):
                        return {
                            "startAt": slot.isoformat(),
                            "endAt": (slot + duration).isoformat(),
                        }
                    slot += timedelta(minutes=30)

        d = (d + timedelta(days=1)).replace(hour=WORK_START, minute=0, second=0, microsecond=0)