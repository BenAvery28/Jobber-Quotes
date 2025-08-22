#
#
#
#   loading environment variables such as API keys from .env

import os
from dotenv import load_dotenv

load_dotenv()  # loads .env into environment

# loading jobber stuff
JOBBER_CLIENT_ID = os.getenv("JOBBER_CLIENT_ID")
JOBBER_CLIENT_SECRET = os.getenv("JOBBER_CLIENT_SECRET")
JOBBER_API_BASE = os.getenv("JOBBER_API_BASE")
JOBBER_API_KEY = os.getenv("JOBBER_API_KEY")
# loading weather api key
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")



