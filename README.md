# Shimmer & Shine – Jobber Quotes AI Scheduler  

This project is an internal tool for **Shimmer & Shine Window Cleaning Ltd.**. It integrates with the **Jobber API** to automate the workflow from approved quotes to confirmed bookings, saving time and improving customer communication.  

---

##  Features  

- **Quote Approval Flow**  
  - When a quote is approved, the app sends an automatic thank-you message.  

- **Scheduling Logic**  
  - Checks Jobber availability to find an open slot.  
  - Estimates the correct job duration (hours for small jobs, multiple days for big ones).  
  - Accounts for weather conditions before booking.  

- **Automation**  
  - Books the job into Jobber’s calendar.  
  - Notifies the assigned crew members.  
  - Confirms the tentative/confirmed date and time with the customer.  
  - Rinse and repeat; no manual touch is required.  

---

## Project Structure
### This is the organized layout of the repository, showcasing all files and directories used in the project.


- 📁 **Root Directory**
  - `.env` (Environment variables)
  - `.gitignore` (Ignored files)
  - `README.md` (You're here!)
  - `requirements.txt` (Dependencies)
  - `run.py` (Run script)
  - 📁 **config** (Configuration files)
    - `settings.py`
    - `init.py`
  - 📁 **docker** (Docker setup)
    - `docker-compose.yml`
    - `Dockerfile`
  - 📁 **docs** (Documentation and legal pages)
    - `index.html`
    - `privacy-policy.html`
    - `terms-of-service.html`
  - 📁 **src** (Source code)
    - `main.py`
    - `db.py`
    - `webapp.py`
    - `__init__.py`
    - 📁 **api** (API modules)
      - `jobber_client.py`
      - `scheduler.py`
      - `weather.py`
      - `__init__.py`
  - 📁 **testing** (Test files)
    - `__init__.py`
    - `mock_data.py`
    - `test_book_job.py`
---

##  Tech Stack  

- **Language:** Python 3.9.13
- **Frameworks/Libraries:** (to be confirmed — likely FastAPI/Flask + httpx/requests + SQLite)  
- **Dev Tools:** Git, PyCharm, Pytest, Vim, Emacs 
- **Hosting:** TBD (ngrok/local for dev, cloud for prod)  

---

##  Jobber API Integration  

This app uses the **Jobber Public API** via OAuth 2.0.  
- Callback URL is set in `/docs` for testing (ngrok during dev).  
- Requires approved API credentials from Jobber.  

---

##  Testing
To test without Jobber API approval:
- testing uses automatic testing through pytest, to automatically test (independent of api availability) follow steps below
- Set `TEST_MODE=True` in `.env` with mock Jobber keys (`JOBBER_CLIENT_ID`, `JOBBER_CLIENT_SECRET`).
- Ensure `OPENWEATHER_API_KEY` is valid in `.env` for real weather checks.
- Install dependencies: `pip install -r requirements.txt`
- Run tests: `python -m pytest testing\`
- Tests in `testing\test_book_job.py` use `mock_data.py` for Jobber responses and real weather data.
- If weather causes failures, check Saskatoon weather or mock `check_weather` in `weather.py`.

---

##  Legal Pages  

For compliance, the app includes:  
- [Privacy Policy](https://benavery28.github.io/Jobber-Quotes/privacy-policy.html)  
- [Terms of Service](https://benavery28.github.io/Jobber-Quotes/terms-of-service.html)  

---

For support or questions, email: sales@shimmershine.org
