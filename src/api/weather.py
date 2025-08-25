# weather.py
#
#   OpenWeatherMap API to check weather conditions

import requests
from datetime import datetime
from config.settings import OPENWEATHER_API_KEY

def check_weather(city, date):
    """
    Check if weather conditions are suitable for a job on a given date.
    Uses OpenWeather OneCall API: checks probability of precipitation (pop).
    Returns True if suitable (pop < 50% and no snow/thunder), False otherwise.
    """
    # get city coordinates (geocoding API)
    geo_url = "http://api.openweathermap.org/geo/1.0/direct"
    geo_params = {"q": city, "limit": 1, "appid": OPENWEATHER_API_KEY}
    geo_resp = requests.get(geo_url, params=geo_params, timeout=5).json()
    if not geo_resp:
        return False
    lat, lon = geo_resp[0]["lat"], geo_resp[0]["lon"]

    onecall_url = "https://api.openweathermap.org/data/2.5/onecall"
    params = {
        "lat": lat,
        "lon": lon,
        "exclude": "minutely,current,alerts",
        "appid": OPENWEATHER_API_KEY,
        "units": "metric"
    }
    forecast = requests.get(onecall_url, params=params, timeout=5).json()

    # daily forecast matching target date
    target_day = date.date()
    for day in forecast.get("daily", []):
        day_date = datetime.fromtimestamp(day["dt"]).date()
        if day_date == target_day:
            weather = day["weather"][0]["main"]
            pop = day.get("pop", 0)  # probability of precipitation (0–1)
            if weather in ["Snow", "Thunderstorm"] or pop > 0.5:
                return False
            return True
    return False
