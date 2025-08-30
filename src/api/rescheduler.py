# src/api/rescheduler.py
#
# Handles automatic rescheduling when:
# 1. Customer cancels appointment
# 2. Weather changes and makes scheduled jobs unsuitable
# 3. Shifts all affected jobs to next available suitable slots

from datetime import datetime, timedelta
from src.db import get_visits, remove_visit_by_name, add_visit, clear_visits
from src.api.weather import check_weather, get_next_suitable_weather_slot
from src.api.scheduler import is_workday, WORK_START, WORK_END
from src.api.jobber_client import create_job, notify_team, notify_client
import asyncio


def cancel_appointment(client_id, reason="Customer cancellation"):
    """
    Cancel an appointment and reschedule all subsequent jobs if needed
    Args:
        client_id (str): Client ID to cancel
        reason (str): Reason for cancellation
    Returns:
        dict: Summary of cancellation and rescheduling actions
    """
    # Remove the cancelled appointment
    removed_count = remove_visit_by_name(client_id)

    if removed_count == 0:
        return {"error": f"No appointments found for client {client_id}"}

    # Get remaining visits after cancellation
    remaining_visits = get_visits()

    # Check if rescheduling is needed for weather-affected jobs
    weather_affected = check_weather_impact_on_schedule(remaining_visits)

    result = {
        "cancelled_client": client_id,
        "cancelled_appointments": removed_count,
        "reason": reason,
        "remaining_appointments": len(remaining_visits),
        "weather_rescheduling_triggered": len(weather_affected) > 0,
        "rescheduled_jobs": []
    }

    # If weather rescheduling is needed, do it
    if weather_affected:
        reschedule_result = reschedule_weather_affected_jobs(weather_affected)
        result["rescheduled_jobs"] = reschedule_result.get("rescheduled_jobs", [])

    return result


def check_weather_impact_on_schedule(visits=None, city="Saskatoon"):
    """
    Check current schedule for weather-affected jobs
    Args:
        visits (list): List of visits to check (default: get from DB)
        city (str): City for weather checking
    Returns:
        list: Jobs that are affected by bad weather
    """
    if visits is None:
        visits = get_visits()

    affected_jobs = []

    for visit in visits:
        start_time = datetime.fromisoformat(visit['startAt'])

        # Only check jobs in the future
        if start_time <= datetime.now():
            continue

        # Check if weather is suitable for this job
        if not check_weather(city, start_time, start_time.hour, start_time.hour + 2):
            affected_jobs.append({
                "client_id": visit['client_id'],
                "original_start": visit['startAt'],
                "original_end": visit['endAt'],
                "date": visit['date']
            })

    return affected_jobs


def reschedule_weather_affected_jobs(affected_jobs, city="Saskatoon"):
    """
    Reschedule jobs affected by bad weather to next suitable slots
    Args:
        affected_jobs (list): List of weather-affected jobs
        city (str): City for weather checking
    Returns:
        dict: Summary of rescheduling actions
    """
    result = {
        "total_affected": len(affected_jobs),
        "successfully_rescheduled": 0,
        "failed_to_reschedule": 0,
        "rescheduled_jobs": []
    }

    for job in affected_jobs:
        # Remove the old booking
        remove_visit_by_name(job["client_id"])

        # Calculate job duration
        original_start = datetime.fromisoformat(job["original_start"])
        original_end = datetime.fromisoformat(job["original_end"])
        duration = (original_end - original_start).total_seconds() / 3600  # hours

        # Find next suitable weather slot
        search_start = original_start + timedelta(hours=1)  # Start search from 1 hour after original
        new_slot = get_next_suitable_weather_slot(city, search_start, duration)

        if new_slot:
            # Check availability against existing bookings
            current_visits = get_visits()
            if _is_slot_available(new_slot["start"], new_slot["end"], current_visits):
                # Book the new slot
                add_visit(
                    new_slot["start"].isoformat(),
                    new_slot["end"].isoformat(),
                    job["client_id"]
                )

                result["successfully_rescheduled"] += 1
                result["rescheduled_jobs"].append({
                    "client_id": job["client_id"],
                    "old_start": job["original_start"],
                    "new_start": new_slot["start"].isoformat(),
                    "new_end": new_slot["end"].isoformat(),
                    "weather_reason": f"POP: {new_slot.get('pop', 0):.1%}, {new_slot.get('weather', 'Unknown')}"
                })
            else:
                result["failed_to_reschedule"] += 1
        else:
            result["failed_to_reschedule"] += 1

    return result


def _is_slot_available(start_time, end_time, existing_visits, grace_period=timedelta(minutes=30)):
    """
    Check if a time slot is available considering existing bookings
    Args:
        start_time (datetime): Proposed start time
        end_time (datetime): Proposed end time
        existing_visits (list): Current bookings
        grace_period (timedelta): Buffer time between jobs
    Returns:
        bool: True if slot is available
    """
    for visit in existing_visits:
        visit_start = datetime.fromisoformat(visit['startAt']) - grace_period
        visit_end = datetime.fromisoformat(visit['endAt']) + grace_period

        # Check for overlap
        if not (end_time <= visit_start or start_time >= visit_end):
            return False

    return True


async def notify_rescheduled_jobs(rescheduled_jobs, access_token="mock_access_token"):
    """
    Send notifications for all rescheduled jobs
    Args:
        rescheduled_jobs (list): List of rescheduled job details
        access_token (str): OAuth token for Jobber API
    """
    for job in rescheduled_jobs:
        client_id = job["client_id"]
        new_start = job["new_start"]
        new_end = job["new_end"]
        reason = job.get("weather_reason", "Weather conditions")

        try:
            # Create new job in Jobber
            job_response = await create_job(
                f"Rescheduled Job - {client_id}",
                new_start,
                new_end,
                access_token
            )

            job_id = job_response["data"]["jobCreate"]["job"]["id"]

            # Notify team
            await notify_team(
                job_id,
                f"Job rescheduled for {client_id} due to weather. New time: {new_start}",
                access_token
            )

            # Notify client
            await notify_client(
                job_id,
                f"Your appointment has been rescheduled due to weather conditions. New time: {new_start} to {new_end}",
                access_token
            )

        except Exception as e:
            print(f"Failed to notify for rescheduled job {client_id}: {e}")


def run_daily_weather_check(city="Saskatoon"):
    """
    Daily check for weather impact on schedule
    Should be run as a scheduled task (cron job)
    Args:
        city (str): City to check weather for
    Returns:
        dict: Summary of any rescheduling actions taken
    """
    print(f"Running daily weather check for {city}...")

    # Get all future appointments
    all_visits = get_visits()
    future_visits = [
        visit for visit in all_visits
        if datetime.fromisoformat(visit['startAt']) > datetime.now()
    ]

    # Check for weather impact
    affected_jobs = check_weather_impact_on_schedule(future_visits, city)

    if not affected_jobs:
        return {
            "message": "No weather-related rescheduling needed",
            "total_jobs_checked": len(future_visits),
            "affected_jobs": 0
        }

    # Reschedule affected jobs
    reschedule_result = reschedule_weather_affected_jobs(affected_jobs, city)

    print(f"Weather check complete. Rescheduled {reschedule_result['successfully_rescheduled']} jobs.")

    return reschedule_result


def compact_schedule():
    """
    Compact the schedule by moving jobs earlier when slots become available
    Useful after cancellations to optimize the schedule
    Returns:
        dict: Summary of schedule optimization
    """
    visits = get_visits()
    if not visits:
        return {"message": "No visits to optimize"}

    # Sort visits by start time
    visits.sort(key=lambda x: x['startAt'])

    optimized_jobs = []

    for i, visit in enumerate(visits):
        start_time = datetime.fromisoformat(visit['startAt'])
        end_time = datetime.fromisoformat(visit['endAt'])
        duration = end_time - start_time

        # Try to find an earlier slot
        search_start = datetime.now().replace(hour=WORK_START, minute=0, second=0, microsecond=0)
        while search_start < start_time:
            if is_workday(search_start):
                # Check if this earlier slot is available
                proposed_end = search_start + duration

                # Make sure it's within work hours
                if proposed_end.hour <= WORK_END and _is_slot_available(
                        search_start, proposed_end, visits[:i] + visits[i + 1:]
                ):
                    # Check weather for the new slot
                    if check_weather("Saskatoon", search_start, search_start.hour, proposed_end.hour):
                        # Move the job to the earlier slot
                        remove_visit_by_name(visit['client_id'])
                        add_visit(
                            search_start.isoformat(),
                            proposed_end.isoformat(),
                            visit['client_id']
                        )

                        optimized_jobs.append({
                            "client_id": visit['client_id'],
                            "old_start": visit['startAt'],
                            "new_start": search_start.isoformat(),
                            "time_saved": str(start_time - search_start)
                        })
                        break

            search_start += timedelta(minutes=30)

    return {
        "total_optimized": len(optimized_jobs),
        "optimized_jobs": optimized_jobs
    }