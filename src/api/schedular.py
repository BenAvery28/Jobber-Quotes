# scheduler.py
#
# Full scheduling system:
# - Checks availability
# - Finds next open slot (Mon–Fri, 9–5)
# - Respects holidays and grace periods
# - Books jobs and updates visit list
# - Prepares data to send to Jobber

from datetime import datetime, timedelta
import random

# tags representing job types (residential/commercial/other)
job_tags = ['res', 'com', 'other']

# 30-minute grace period between bookings
WORK_START = 9  # 9 am
WORK_END = 17  # 5 pm
grace_period = timedelta(minutes=30)

holidays = {
    "2025-01-01": "New Year's Day",
    "2025-07-01": "Canada Day",
    "2025-12-25": "Christmas Day"
}

def is_workday(d):
    """
    Return True if the given date is a weekday (Mon–Fri) and not a holiday.
    """
    weekday = d.weekday()  # monday = 0, sunday = 6 ( will I ever get use to it? )
    date_str = d.strftime("%Y-%m-%d")

    is_weekday = weekday < 5   # cause 5 and 6 are sat and sun !
    not_holiday = date_str not in holidays

    return is_weekday and not_holiday

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

def auto_book(visits, start_date, duration, job_type="res"):
    """
    Find the next available time slot for a job and return it as a string (ISO format).
    - visits: list of dicts with 'startAt' and 'endAt' (ISO strings)
    - start_date: datetime to begin searching from
    - duration: timedelta for job length
    - job_type: 'res', 'com', or 'other' (future flexibility)
    """

    # step through each day from start_date onward
    d = start_date.replace(hour=WORK_START, minute=0, second=0, microsecond=0)

    while True:
        # valid workday
        if is_workday(d):
            day_start = d.replace(hour=WORK_START, minute=0)
            day_end = d.replace(hour=WORK_END, minute=0)

            # start at 9am and move in 30-minute increments
            slot = day_start
            while slot + duration <= day_end:
                if check_availability(visits, slot, duration):
                    # found a valid slot → return as ISO string
                    return slot.isoformat()

                slot += timedelta(minutes=30)  # try next half-hour slot

        # move to the next day 9 am
        d = (d + timedelta(days=1)).replace(hour=WORK_START, minute=0, second=0, microsecond=0)

