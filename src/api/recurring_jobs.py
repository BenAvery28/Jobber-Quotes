# recurring_jobs.py
#
# Handles recurring job booking - books entire summer in advance
# Supports manual time/day selection

from datetime import datetime, timedelta
from src.db import create_recurring_job, get_recurring_jobs, add_visit, get_visits
from src.api.scheduler import is_workday, check_availability, WORK_START, WORK_END
from src.api.weather import check_weather_with_confidence
import sqlite3


def generate_bookings_from_recurring_job(recurring_job_id: int, city: str = "Saskatoon", 
                                         check_weather: bool = True, 
                                         skip_conflicts: bool = True):
    """
    Generate individual bookings from a recurring job template.
    Books all occurrences between start_date and end_date on the specified day_of_week.
    
    Args:
        recurring_job_id: ID of recurring job template
        city: City for weather checking
        check_weather: If True, check weather before booking (may create tentative bookings)
        skip_conflicts: If True, skip dates that already have bookings
    
    Returns:
        dict: {
            'recurring_job_id': int,
            'total_dates': int,
            'booked': int,
            'skipped_conflicts': int,
            'skipped_weather': int,
            'bookings': list of created booking dicts
        }
    """
    # Get recurring job details
    all_recurring = get_recurring_jobs(active_only=False)
    recurring_job = next((rj for rj in all_recurring if rj['id'] == recurring_job_id), None)
    
    if not recurring_job:
        return {
            'error': f'Recurring job {recurring_job_id} not found',
            'total_dates': 0,
            'booked': 0,
            'skipped_conflicts': 0,
            'skipped_weather': 0,
            'bookings': []
        }
    
    if not recurring_job['is_active']:
        return {
            'error': f'Recurring job {recurring_job_id} is not active',
            'total_dates': 0,
            'booked': 0,
            'skipped_conflicts': 0,
            'skipped_weather': 0,
            'bookings': []
        }
    
    # Parse dates and times
    start_date = datetime.strptime(recurring_job['start_date'], "%Y-%m-%d").date()
    end_date = datetime.strptime(recurring_job['end_date'], "%Y-%m-%d").date()
    day_of_week = recurring_job['day_of_week']
    start_time_str = recurring_job['start_time']  # HH:MM format
    duration_hours = recurring_job['duration_hours']
    client_id = recurring_job['client_id']
    job_tag = recurring_job['job_tag']
    
    # Parse start time
    hour, minute = map(int, start_time_str.split(':'))
    
    # Generate all dates for this day of week between start and end
    current_date = start_date
    result = {
        'recurring_job_id': recurring_job_id,
        'total_dates': 0,
        'booked': 0,
        'skipped_conflicts': 0,
        'skipped_weather': 0,
        'bookings': []
    }
    
    # Get existing visits for conflict checking
    existing_visits = get_visits(include_tentative=False) if skip_conflicts else []
    
    while current_date <= end_date:
        # Check if this date matches the day of week
        if current_date.weekday() == day_of_week:
            result['total_dates'] += 1
            
            # Create datetime for this occurrence
            job_datetime = datetime.combine(current_date, datetime.min.time().replace(hour=hour, minute=minute))
            end_datetime = job_datetime + timedelta(hours=duration_hours)
            
            # Check if it's a workday (Mon-Thu, not Friday, not holiday)
            if not is_workday(job_datetime):
                current_date += timedelta(days=1)
                continue
            
            # Check if within work hours
            if job_datetime.hour < WORK_START or end_datetime.hour > WORK_END:
                current_date += timedelta(days=1)
                continue
            
            # Check for conflicts
            if skip_conflicts:
                duration = timedelta(hours=duration_hours)
                if not check_availability(job_datetime, duration, existing_visits):
                    result['skipped_conflicts'] += 1
                    current_date += timedelta(days=1)
                    continue
            
            # Check weather if requested
            booking_status = "confirmed"
            if check_weather:
                weather_check = check_weather_with_confidence(
                    city, job_datetime, job_datetime.hour, end_datetime.hour
                )
                if not weather_check['suitable']:
                    result['skipped_weather'] += 1
                    current_date += timedelta(days=1)
                    continue
                elif weather_check['confidence'] == 'low':
                    booking_status = "tentative"
            
            # Create the booking
            try:
                add_visit(
                    job_datetime.isoformat(),
                    end_datetime.isoformat(),
                    client_id,
                    job_tag,
                    booking_status
                )
                result['booked'] += 1
                result['bookings'].append({
                    'date': current_date.strftime("%Y-%m-%d"),
                    'start_at': job_datetime.isoformat(),
                    'end_at': end_datetime.isoformat(),
                    'booking_status': booking_status
                })
                
                # Add to existing_visits for next iteration conflict checking
                if skip_conflicts:
                    existing_visits.append({
                        'startAt': job_datetime.isoformat(),
                        'endAt': end_datetime.isoformat(),
                        'client_id': client_id
                    })
            except sqlite3.IntegrityError:
                # Duplicate booking (shouldn't happen with skip_conflicts, but handle gracefully)
                result['skipped_conflicts'] += 1
        
        current_date += timedelta(days=1)
    
    return result


def book_entire_summer(client_id: str, day_of_week: int, start_time: str, duration_hours: float,
                      job_tag: str = "residential", start_date: str = None, end_date: str = None):
    """
    Convenience function to create a recurring job and book the entire summer.
    
    Args:
        client_id: Client ID
        day_of_week: Day of week (0=Monday, 1=Tuesday, ..., 3=Thursday)
        start_time: Start time in HH:MM format
        duration_hours: Duration in hours
        job_tag: Job classification
        start_date: Start date (YYYY-MM-DD). Defaults to first Monday of current month
        end_date: End date (YYYY-MM-DD). Defaults to end of summer (August 31)
    
    Returns:
        dict: Result from generate_bookings_from_recurring_job
    """
    # Default dates if not provided
    if not start_date:
        now = datetime.now()
        # Find first Monday of current month
        first_day = now.replace(day=1)
        days_until_monday = (0 - first_day.weekday()) % 7
        if days_until_monday == 7:
            days_until_monday = 0
        start_date = (first_day + timedelta(days=days_until_monday)).strftime("%Y-%m-%d")
    
    if not end_date:
        # Default to end of August (summer season)
        now = datetime.now()
        end_date = now.replace(month=8, day=31).strftime("%Y-%m-%d")
    
    # Create recurring job
    recurring_job_id = create_recurring_job(
        client_id, day_of_week, start_time, duration_hours, start_date, end_date, job_tag
    )
    
    # Generate all bookings
    return generate_bookings_from_recurring_job(recurring_job_id, check_weather=True, skip_conflicts=True)

