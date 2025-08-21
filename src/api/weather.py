#
#
#
#   OpenWeatherMap API to check weather conditions

import requests
from datetime import datetime
from config.settings import OPENWEATHER_API_KEY

def check_weather(city, date):
    """
    Check if weather conditions are suitable for a job on a given date.
    Returns True if suitable (no rain, snow, or thunderstorms), False otherwise.
    """
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        'q': city,  # city is 99% saskatoon but will still pull from the quote.
        'appid': OPENWEATHER_API_KEY,
        'dt': int(date.timestamp()) if isinstance(date, datetime) else int(date)  # unix timestamp
    }
    try:
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        if data['cod'] != 200:
            return False
        weather = data['weather'][0]['main']
        bad_conditions = ['Rain', 'Snow', 'Thunderstorm']
        return weather not in bad_conditions
    except requests.exceptions.RequestException as e:
        print(f"Weather API error: {e}")
        return False



# a test fucntion
if __name__ == "__main__":
    result = check_weather("Saskatoon", datetime.now())
    print(f"Weather suitable: {result}")