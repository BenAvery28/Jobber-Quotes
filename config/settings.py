#
#
#
#   loading environment variables such as API keys from .env

import os
from dotenv import load_dotenv

load_dotenv()  # loads .env into environment

JOBBER_API_KEY = os.getenv("JOBBER_API_KEY")
JOBBER_API_BASE = "https://api.getjobber.com/api"
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")



