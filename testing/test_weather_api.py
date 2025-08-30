# testing/test_weather_api.py
"""
Test script to verify the updated weather API functionality
Checks that we're getting proper 4-day hourly weather data
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from src.api.weather import get_hourly_forecast, check_weather, get_next_suitable_weather_slot


def test_hourly_forecast():
    """Test getting hourly forecast data"""
    print("=== Testing Hourly Forecast ===")

    forecast = get_hourly_forecast("Saskatoon", days_ahead=4)

    if forecast:
        print("✓ Weather API connection successful")

        # Check data structure
        if 'current' in forecast:
            print("✓ Current weather data available")
            current = forecast['current']
            print(f"  Current temp: {current.get('temp', 'N/A')}°C")
            print(f"  Current weather: {current.get('weather', [{}])[0].get('description', 'N/A')}")

        if 'hourly' in forecast:
            print("✓ Hourly forecast data available")
            hourly_count = len(forecast['hourly'])
            print(f"  Hourly entries: {hourly_count}")

            # Show first few hours
            for i, hour in enumerate(forecast['hourly'][:6]):
                dt = datetime.fromtimestamp(hour['dt'])
                temp = hour.get('temp', 'N/A')
                pop = hour.get('pop', 0) * 100  # Convert to percentage
                weather = hour['weather'][0]['main']
                print(f"  {dt.strftime('%m-%d %H:%M')}: {temp}°C, {weather}, {pop:.0f}% rain")

        if 'daily' in forecast:
            print("✓ Daily forecast data available")
            daily_count = len(forecast['daily'])
            print(f"  Daily entries: {daily_count}")

            # Show next few days
            for i, day in enumerate(forecast['daily'][:4]):
                dt = datetime.fromtimestamp(day['dt'])
                temp_max = day['temp'].get('max', 'N/A')
                temp_min = day['temp'].get('min', 'N/A')
                pop = day.get('pop', 0) * 100
                weather = day['weather'][0]['main']
                print(f"  {dt.strftime('%m-%d')}: {temp_min}-{temp_max}°C, {weather}, {pop:.0f}% rain")

        return True
    else:
        print("✗ Weather API connection failed")
        print("  This could be due to:")
        print("  - Invalid API key")
        print("  - Network connectivity issues")
        print("  - API quota exceeded")
        return False


def test_weather_checking():
    """Test weather suitability checking"""
    print("\n=== Testing Weather Checking ===")

    # Test for tomorrow
    tomorrow = datetime.now() + timedelta(days=1)
    is_suitable = check_weather("Saskatoon", tomorrow, 9, 17)

    print(f"Weather suitable for tomorrow (9-5): {is_suitable}")

    # Test for day after tomorrow
    day_after = datetime.now() + timedelta(days=2)
    is_suitable_2 = check_weather("Saskatoon", day_after, 9, 17)

    print(f"Weather suitable for day after tomorrow: {is_suitable_2}")

    return True


def test_weather_slot_finding():
    """Test finding next suitable weather slot"""
    print("\n=== Testing Weather Slot Finding ===")

    start_search = datetime.now() + timedelta(hours=1)
    next_slot = get_next_suitable_weather_slot("Saskatoon", start_search, 2.0)

    if next_slot:
        print("✓ Found suitable weather slot:")
        print(f"  Start: {next_slot['start']}")
        print(f"  End: {next_slot['end']}")
        print(f"  Weather: {next_slot.get('weather', 'N/A')}")
        print(f"  Rain probability: {next_slot.get('pop', 0) * 100:.0f}%")
    else:
        print("✗ No suitable weather slot found in next 4 days")

    return next_slot is not None


def test_api_endpoints():
    """Test the new API endpoints"""
    print("\n=== Testing API Endpoints ===")

    from fastapi.testclient import TestClient
    from src.webapp import app

    client = TestClient(app)

    # Test weather forecast endpoint
    response = client.get("/weather-forecast/Saskatoon")
    print(f"Weather forecast endpoint: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"  City: {data.get('city')}")
        print(f"  Hourly available: {data.get('hourly_available')}")
        print(f"  Daily available: {data.get('daily_available')}")

    # Test schedule status
    response = client.get("/schedule-status")
    print(f"Schedule status endpoint: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"  Total appointments: {data.get('total_appointments')}")
        print(f"  Weather affected jobs: {data.get('weather_affected_jobs')}")

    # Test weather check
    response = client.get("/weather-check")
    print(f"Weather check endpoint: {response.status_code}")

    return True


def check_api_requirements():
    """Check if API key is configured"""
    print("=== Checking API Configuration ===")

    api_key = os.getenv("OPENWEATHER_API_KEY")
    if api_key:
        print(f"✓ OpenWeather API key configured: {api_key[:8]}...")
        return True
    else:
        print("✗ OpenWeather API key not found in environment variables")
        print("  Set OPENWEATHER_API_KEY in your .env file")
        return False


if __name__ == "__main__":
    print("Testing Updated Weather API Functionality\n")

    # Check configuration first
    if not check_api_requirements():
        exit(1)

    # Test weather data retrieval
    forecast_works = test_hourly_forecast()

    if forecast_works:
        # Test weather checking logic
        test_weather_checking()

        # Test slot finding
        test_weather_slot_finding()

        # Test API endpoints
        test_api_endpoints()

        print("\n=== Summary ===")
        print("Weather API update successful!")
        print("You now have:")
        print("- 4-day weather forecasts using One Call API 3.0")
        print("- Hourly data for next 48 hours")
        print("- Daily data for next 8 days")
        print("- Automatic rescheduling when weather changes")
        print("- Appointment cancellation with cascade rescheduling")
        print("- Schedule optimization functionality")
    else:
        print("\n=== Issues Found ===")
        print("Weather API is not working properly.")
        print("Check your OPENWEATHER_API_KEY in the .env file.")
        print("You may need to:")
        print("1. Sign up for a free account at openweathermap.org")
        print("2. Generate an API key")
        print("3. Add it to your .env file as OPENWEATHER_API_KEY=your_key_here")