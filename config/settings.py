# config/settings.py
#
#   loading environment variables such as API keys from .env

import os
from dotenv import load_dotenv

#added print for testing purposes
print(str(load_dotenv()) + " environment var has been loaded (for testing)") # loads .env into environment


# loading jobber stuff
JOBBER_CLIENT_ID = os.getenv("JOBBER_CLIENT_ID")
JOBBER_CLIENT_SECRET = os.getenv("JOBBER_CLIENT_SECRET")
JOBBER_API_KEY = os.getenv("JOBBER_API_KEY")

# Jobber API endpoint (fixed per their docs)
JOBBER_API_BASE = "https://api.getjobber.com/api"
JOBBER_GRAPHQL_URL = f"{JOBBER_API_BASE}/graphql"

# checks
if not JOBBER_CLIENT_ID:
    raise RuntimeError("JOBBER_CLIENT_ID is required!")
if not JOBBER_CLIENT_SECRET:
    raise RuntimeError("JOBBER_CLIENT_SECRET is required!")
#if not JOBBER_API_KEY:
    #raise RuntimeError("JOBBER_API_KEY is required!")

# loading weather api key
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

# routing / optimization
# options: "none", "jobber", "external"
ROUTE_OPTIMIZATION_MODE = os.getenv("ROUTE_OPTIMIZATION_MODE", "none").lower()
EXTERNAL_ROUTE_API_KEY = os.getenv("EXTERNAL_ROUTE_API_KEY")



