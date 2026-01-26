# src/api/rescheduler.py
#
# Handles automatic rescheduling when:
# 1. Customer cancels appointment
# 2. Weather changes and makes scheduled jobs unsuitable
# 3. Shifts all affected jobs to next available suitable slots

from datetime import datetime, timedelta
from src.db import get_visits, remove_visit_by_name, add_visit, clear_visits, get_tentative_bookings, update_booking_status
from src.api.weather import check_weather, get_next_suitable_weather_slot, check_weather_with_confidence
from src.api.scheduler import is_workday, WORK_START, WORK_END, auto_book, estimate_time
from src.api.jobber_client import create_job, notify_team, notify_client
from src.api.job_classifier import get_crew_for_tag
from src.api.route_optimizer import optimize_visit_order
from src.timezone_utils import now as tz_now
import asyncio
import logging

logger = logging.getLogger(__name__)


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
        if start_time <= tz_now():
            continue

        # Check if weather is suitable for this job
        if not check_weather(city, start_time, start_time.hour, start_time.hour + 2):
            affected_jobs.append({
                "client_id": visit['client_id'],
                "original_start": visit['startAt'],
                "original_end": visit['endAt'],
                "date": visit['date'],
                "job_tag": visit.get("job_tag", "residential")
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
                    job["client_id"],
                    job.get("job_tag", "residential")
                )

                result["successfully_rescheduled"] += 1
                result["rescheduled_jobs"].append({
                    "client_id": job["client_id"],
                    "old_start": job["original_start"],
                    "new_start": new_slot["start"].isoformat(),
                    "new_end": new_slot["end"].isoformat(),
                    "weather_reason": f"POP: {new_slot.get('pop', 0):.1%}, {new_slot.get('weather', 'Unknown')}",
                    "job_tag": job.get("job_tag", "residential")
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
        job_tag = job.get("job_tag", "residential")
        crew_assignment = get_crew_for_tag(job_tag)

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
                f"Job rescheduled for {client_id} due to weather. New time: {new_start} (crew: {crew_assignment})",
                access_token
            )

            # Notify client
            await notify_client(
                job_id,
                f"Your appointment has been rescheduled due to weather conditions. New time: {new_start} to {new_end}",
                access_token
            )

        except Exception as e:
            logger.error(f"Failed to notify for rescheduled job {client_id}: {e}", exc_info=True)


def run_daily_weather_check(city="Saskatoon"):
    """
    Daily check for weather impact on schedule
    Should be run as a scheduled task (cron job)
    Args:
        city (str): City to check weather for
    Returns:
        dict: Summary of any rescheduling actions taken
    """
    logger.info(f"Running daily weather check for {city}...")

    # Get all future appointments
    all_visits = get_visits()
    future_visits = [
        visit for visit in all_visits
        if datetime.fromisoformat(visit['startAt']) > tz_now()
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

    logger.info(f"Weather check complete. Rescheduled {reschedule_result['successfully_rescheduled']} jobs.")

    return reschedule_result


def recheck_tentative_bookings(city="Saskatoon"):
    """
    Recheck tentative bookings and upgrade to confirmed if weather improves,
    or reshuffle if weather deteriorates. This is the pseudo-reshuffler.
    
    Args:
        city (str): City for weather checking
    Returns:
        dict: Summary of reshuffling actions
    """
    tentative_bookings = get_tentative_bookings()
    
    if not tentative_bookings:
        return {
            "checked": 0,
            "upgraded_to_confirmed": 0,
            "reshuffled": 0,
            "no_change": 0,
            "details": []
        }
    
    result = {
        "checked": len(tentative_bookings),
        "upgraded_to_confirmed": 0,
        "reshuffled": 0,
        "no_change": 0,
        "details": []
    }
    
    # Get all visits (including confirmed) for availability checking
    all_visits = get_visits(include_tentative=False)  # Only confirmed for conflict checking
    
    for booking in tentative_bookings:
        client_id = booking['client_id']
        start_time = datetime.fromisoformat(booking['startAt'])
        end_time = datetime.fromisoformat(booking['endAt'])
        duration = end_time - start_time
        
        # Only check bookings that are still in the future
        if start_time <= tz_now():
            continue
        
        # Recheck weather with confidence
        weather_check = check_weather_with_confidence(city, start_time, start_time.hour, end_time.hour)
        
        if weather_check['confidence'] == 'high' or weather_check['confidence'] == 'medium':
            # Weather improved - upgrade to confirmed
            update_booking_status(client_id, booking['startAt'], 'confirmed')
            result["upgraded_to_confirmed"] += 1
            result["details"].append({
                "client_id": client_id,
                "action": "upgraded_to_confirmed",
                "reason": f"Weather improved: {weather_check['reason']}"
            })
        elif weather_check['confidence'] == 'bad':
            # Weather deteriorated - try to reshuffle
            # Remove tentative booking
            remove_visit_by_name(client_id)
            
            # Try to find a better slot (allow Friday for reschedules)
            new_slot = auto_book(
                all_visits,
                tz_now(),
                duration,
                city,
                client_id,
                allow_tentative=True,
                allow_friday=True  # Allow Friday for reschedules
            )
            
            if new_slot:
                # Add new booking (could be tentative or confirmed)
                from src.db import get_visits as get_all_visits
                all_visits_updated = get_all_visits(include_tentative=False)
                add_visit(
                    new_slot["startAt"],
                    new_slot["endAt"],
                    client_id,
                    booking.get('job_tag', 'residential'),
                    new_slot.get("booking_status", "confirmed")
                )
                result["reshuffled"] += 1
                result["details"].append({
                    "client_id": client_id,
                    "action": "reshuffled",
                    "old_start": booking['startAt'],
                    "new_start": new_slot["startAt"],
                    "new_status": new_slot.get("booking_status", "confirmed")
                })
            else:
                # Couldn't find better slot - keep original (re-add it)
                add_visit(
                    booking['startAt'],
                    booking['endAt'],
                    client_id,
                    booking.get('job_tag', 'residential'),
                    'tentative'
                )
                result["no_change"] += 1
                result["details"].append({
                    "client_id": client_id,
                    "action": "no_change",
                    "reason": "No better slot available"
                })
        else:
            # Still low confidence - keep as tentative
            result["no_change"] += 1
    
    return result


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
        search_start = tz_now().replace(hour=WORK_START, minute=0, second=0, microsecond=0)
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

    route_optimization = optimize_visit_order(get_visits())

    return {
        "total_optimized": len(optimized_jobs),
        "optimized_jobs": optimized_jobs,
        "route_optimization": route_optimization
    }