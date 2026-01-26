# weather.py
#
#   OpenWeatherMap API using One Call API 3.0 for 4-day hourly forecasts

import requests
from datetime import datetime, timedelta
from config.settings import OPENWEATHER_API_KEY


def get_hourly_forecast(city, days_ahead=2):
    """
    Get weather forecast using free 5-day/3-hour forecast API.
    Reduced to 2 days for better accuracy (shorter-term forecasts are more reliable).
    Returns forecast data with 3-hour intervals.
    Args:
        city (str): City name
        days_ahead (int): Number of days to forecast (default 2 for better accuracy)
    Returns:
        dict: Weather forecast data with list of 3-hour forecasts
    """
    # Default to Saskatoon, SK, CA
    state_code = "SK"
    country_code = "CA"

    query = f"{city},{state_code},{country_code}"
    geo_url = "http://api.openweathermap.org/geo/1.0/direct"
    geo_params = {"q": query, "limit": 1, "appid": OPENWEATHER_API_KEY}

    try:
        geo_resp = requests.get(geo_url, params=geo_params, timeout=5).json()
        if not geo_resp:
            return None
        lat, lon = geo_resp[0]["lat"], geo_resp[0]["lon"]
    except Exception as e:
        print(f"Geocoding error: {e}")
        return None

    # Use free 5-day/3-hour forecast API
    forecast_url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric"
    }

    try:
        forecast = requests.get(forecast_url, params=params, timeout=10).json()
        return forecast
    except Exception as e:
        print(f"Forecast API error: {e}")
        return None


def check_weather(city, date, start_hour=8, end_hour=20):
    """
    Check if weather conditions are suitable for a job on a given date and time range.
    Uses free forecast API with 3-hour intervals (2-day window for accuracy).
    Returns True if suitable (pop < 50% and no severe weather), False otherwise.
    Args:
        city (str): City name
        date (datetime): Date to check
        start_hour (int): Start hour (default 8 AM)
        end_hour (int): End hour (default 8 PM)
    """
    forecast = get_hourly_forecast(city, days_ahead=2)
    if not forecast or 'list' not in forecast:
        # If weather API fails, be conservative and allow booking
        return True

    target_date = date.date()

    # Check 3-hourly forecast data
    for item in forecast['list']:
        forecast_time = datetime.fromtimestamp(item["dt"]).replace(tzinfo=None)

        # Check if this forecast falls within our date and time range
        if (forecast_time.date() == target_date and
                start_hour <= forecast_time.hour < end_hour):

            weather_main = item["weather"][0]["main"]
            pop = item.get("pop", 0)  # probability of precipitation (0-1)

            # Check for severe weather conditions
            if weather_main in ["Snow", "Thunderstorm"] or pop > 0.5:
                return False

    return True


def check_weather_with_confidence(city, date, start_hour=8, end_hour=20):
    """
    Check weather conditions with confidence levels for better decision making.
    Returns dict with 'suitable', 'confidence', and 'reason'.
    
    Confidence levels:
    - 'high' (100%): Clear weather, pop < 20%, no severe weather
    - 'medium' (80%): Some uncertainty, pop 20-40%, mild conditions
    - 'low' (uncertain): pop 40-50%, or forecast unavailable
    - 'bad': pop > 50% or severe weather
    
    Args:
        city (str): City name
        date (datetime): Date to check
        start_hour (int): Start hour (default 8 AM)
        end_hour (int): End hour (default 8 PM)
    
    Returns:
        dict: {
            'suitable': bool,
            'confidence': str ('high', 'medium', 'low', 'bad'),
            'reason': str,
            'max_pop': float (max precipitation probability),
            'severe_weather': bool
        }
    """
    forecast = get_hourly_forecast(city, days_ahead=2)
    
    # If forecast unavailable, return uncertain (allow booking but mark as tentative)
    if not forecast or 'list' not in forecast:
        return {
            'suitable': True,
            'confidence': 'low',
            'reason': 'Forecast unavailable - booking tentatively',
            'max_pop': None,
            'severe_weather': False
        }
    
    target_date = date.date()
    max_pop = 0.0
    has_severe_weather = False
    weather_types = []
    
    # Check 3-hourly forecast data for the time window
    for item in forecast['list']:
        forecast_time = datetime.fromtimestamp(item["dt"]).replace(tzinfo=None)
        
        if (forecast_time.date() == target_date and
                start_hour <= forecast_time.hour < end_hour):
            
            weather_main = item["weather"][0]["main"]
            pop = item.get("pop", 0)
            
            max_pop = max(max_pop, pop)
            weather_types.append(weather_main)
            
            # Check for severe weather
            if weather_main in ["Snow", "Thunderstorm"]:
                has_severe_weather = True
    
    # Determine confidence level
    if has_severe_weather or max_pop > 0.5:
        return {
            'suitable': False,
            'confidence': 'bad',
            'reason': f'Severe weather or high precipitation ({max_pop*100:.0f}%)',
            'max_pop': max_pop,
            'severe_weather': has_severe_weather
        }
    elif max_pop < 0.2:
        return {
            'suitable': True,
            'confidence': 'high',
            'reason': f'Clear weather, low precipitation risk ({max_pop*100:.0f}%)',
            'max_pop': max_pop,
            'severe_weather': False
        }
    elif max_pop < 0.4:
        return {
            'suitable': True,
            'confidence': 'medium',
            'reason': f'Moderate conditions, some precipitation risk ({max_pop*100:.0f}%)',
            'max_pop': max_pop,
            'severe_weather': False
        }
    else:  # 0.4 <= max_pop < 0.5
        return {
            'suitable': True,
            'confidence': 'low',
            'reason': f'Uncertain weather, moderate precipitation risk ({max_pop*100:.0f}%)',
            'max_pop': max_pop,
            'severe_weather': False
        }


def get_next_suitable_weather_slot(city, start_datetime, duration_hours):
    """
    Find the next suitable weather window for a job using free forecast API
    Args:
        city (str): City name
        start_datetime (datetime): Earliest possible start time
        duration_hours (float): Job duration in hours
    Returns:
        dict: {"start": datetime, "end": datetime} or None if no suitable slot
    """
    forecast = get_hourly_forecast(city, days_ahead=4)
    if not forecast or 'list' not in forecast:
        return None

    # Check 3-hourly forecast data
    for item in forecast['list']:
        forecast_time = datetime.fromtimestamp(item["dt"]).replace(tzinfo=None)

        # Skip times before our start time or outside work hours (8am-8pm)
        if forecast_time < start_datetime or forecast_time.hour < 8 or forecast_time.hour >= 20:
            continue

        # Check if this time has suitable weather
        weather_main = item["weather"][0]["main"]
        pop = item.get("pop", 0)

        if weather_main not in ["Snow", "Thunderstorm"] and pop <= 0.5:
            # For 3-hour intervals, we'll assume the weather is good for the duration
            slot_end = forecast_time + timedelta(hours=duration_hours)

            return {
                "start": forecast_time,
                "end": slot_end,
                "pop": pop,
                "weather": weather_main
            }

    return None


def _check_weather_window(hourly_data, start_time, end_time):
    """
    Check if a specific time window has suitable weather
    Args:
        hourly_data (list): Hourly forecast data
        start_time (datetime): Window start
        end_time (datetime): Window end
    Returns:
        bool: True if entire window has suitable weather
    """
    for item in hourly_data:
        forecast_time = datetime.fromtimestamp(item["dt"]).replace(tzinfo=None)

        # Check if this forecast time falls within our window
        if start_time <= forecast_time <= end_time:
            weather_main = item["weather"][0]["main"]
            pop = item.get("pop", 0)

            if weather_main in ["Snow", "Thunderstorm"] or pop > 0.5:
                return False

    return True