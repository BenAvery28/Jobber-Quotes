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

##  Project Structure


│   .env
│   .gitignore
│   README.md
│   requirements.txt
│   run.py
│
├───.idea
│   │   .gitignore
│   │   Jobber Quotes.iml
│   │   misc.xml
│   │   modules.xml
│   │   vcs.xml
│   │   workspace.xml
│   │
│   └───inspectionProfiles
│           profiles_settings.xml
│
├───config
│   │   settings.py
│   │   __init__.py
│   │
│   └───__pycache__
│           settings.cpython-39.pyc
│           __init__.cpython-39.pyc
│
├───docker
│       docker-compose.yml
│       Dockerfile
│
├───docs
│       index.html
│       privacy-policy.html
│       terms-of-service.html
│
├───src
│   │   main.py
│   │   webapp.py
│   │   __init__.py
│   │
│   ├───api
│   │   │   jobber_client.py
│   │   │   scheduler.py
│   │   │   weather.py
│   │   │   __init__.py
│   │   │
│   │   └───__pycache__
│   │           jobber_client.cpython-39.pyc
│   │           scheduler.cpython-39.pyc
│   │           __init__.cpython-39.pyc
│   │
│   └───__pycache__
│           main.cpython-39.pyc
│           webapp.cpython-39.pyc
│           __init__.cpython-39.pyc
│
└───testing
        __init__.py

---

##  Tech Stack  

- **Language:** Python 3.9.13
- **Frameworks/Libraries:** (to be confirmed — likely FastAPI/Flask + httpx/requests)  
- **Dev Tools:** Git, PyCharm  
- **Hosting:** TBD (ngrok/local for dev, cloud for prod)  

---

##  Jobber API Integration  

This app uses the **Jobber Public API** via OAuth 2.0.  
- Callback URL is set in `/docs` for testing (ngrok during dev).  
- Requires approved API credentials from Jobber.  

---

##  Legal Pages  

For compliance, the app includes:  
- [Privacy Policy](https://benavery28.github.io/Jobber-Quotes/privacy-policy.html)  
- [Terms of Service](https://benavery28.github.io/Jobber-Quotes/terms-of-service.html)  

---

For support or questions, email: sales@shimmershine.org
