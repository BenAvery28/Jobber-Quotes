# weather.py
#
#   OpenWeatherMap API to check weather conditions

import requests
from datetime import datetime
from config.settings import OPENWEATHER_API_KEY


def check_weather(city, date, start_hour=9, end_hour=17):
    """
    Check if weather conditions are suitable for a job on a given date and time range.
    Uses OpenWeather hourly forecast API: checks probability of precipitation (pop).
    Returns True if suitable (pop < 50% and no snow/thunder) for all hours, False otherwise.
    Args:
        city (str): City name.
        date (datetime): Date to check.
        start_hour (int): Start hour (default 9 AM).
        end_hour (int): End hour (default 5 PM).
    """
    # DEbug
    # print(f"Checking weather for {city} on {date.date()} from {start_hour}:00 to {end_hour}:00")

    # Default to Saskatoon, SK, CA
    state_code = "SK"
    country_code = "CA"

    query = f"{city},{state_code},{country_code}"
    geo_url = "http://api.openweathermap.org/geo/1.0/direct"
    geo_params = {"q": query, "limit": 1, "appid": OPENWEATHER_API_KEY}

    try:
        geo_resp = requests.get(geo_url, params=geo_params, timeout=5).json()

        # debug
        # print(f"Geocoding response: {geo_resp}")

        if not geo_resp:
            # print("No geocoding data found")
            return False
        lat, lon = geo_resp[0]["lat"], geo_resp[0]["lon"]
    except Exception as e:
        # print(f"Geocoding error: {e}")
        return False

    hourly_url = "https://pro.openweathermap.org/data/2.5/forecast/hourly"
    params = {"lat": lat, "lon": lon, "appid": OPENWEATHER_API_KEY, "units": "metric"}
    try:
        forecast = requests.get(hourly_url, params=params, timeout=5).json()
        # print(f"Hourly forecast response: {forecast}")  # Debug
        target_date = date.date()
        for item in forecast.get("list", []):
            forecast_time = datetime.fromtimestamp(item["dt"]).replace(tzinfo=None)  # Remove tz for comparison
            if forecast_time.date() == target_date and start_hour <= forecast_time.hour < end_hour:
                weather = item["weather"][0]["main"]
                pop = item.get("pop", 0)  # probability of precipitation (0–1)
                # print(f"Hour {forecast_time.hour}: Weather: {weather}, POP: {pop}")
                if weather in ["Snow", "Thunderstorm"] or pop > 0.5:
                    return False
        # print("All hours suitable or no data for range")
        return True
    except Exception as e:
        # print(f"Forecast error: {e}")
        return False