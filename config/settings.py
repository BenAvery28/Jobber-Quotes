import os
from dotenv import load_dotenv

load_dotenv()  # loads .env into environment

JOBBER_API_KEY = os.getenv("JOBBER_API_KEY")
JOBBER_API_BASE = "https://api.getjobber.com/api"




