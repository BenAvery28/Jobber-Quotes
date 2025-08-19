# Shimmer & Shine – Jobber Quotes AI Scheduler  

This project is an internal tool for **Shimmer & Shine Window Cleaning Ltd.**. It integrates with the **Jobber API** to automate the workflow from approved quotes to confirmed bookings — saving time and improving customer communication.  

---

## 🚀 Features  

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
  - Rinse and repeat — no manual touch required.  

---

## 📂 Project Structure  
Jobber-Quotes/
├─ config/ # Configuration files (API keys, settings, environment)
├─ src/ # Application source code
├─ docs/ # Public legal pages for API compliance
│ ├─ privacy-policy.html
│ └─ terms-of-service.html
├─ README.md # Project documentation
└─ requirements.txt # Python dependencies


---

## ⚙️ Tech Stack  

- **Language:** Python 3.x  
- **Frameworks/Libraries:** (to be confirmed — likely FastAPI/Flask + httpx/requests)  
- **Dev Tools:** Git, PyCharm  
- **Hosting:** TBD (ngrok/local for dev, cloud for prod)  

---

## 🔑 Jobber API Integration  

This app uses the **Jobber Public API** via OAuth 2.0.  
- Callback URL is set in `/docs` for testing (ngrok during dev).  
- Requires approved API credentials from Jobber.  

---

## 📜 Legal Pages  

For compliance, the app includes:  
- [Privacy Policy](https://benavery28.github.io/Jobber-Quotes/privacy-policy.html)  
- [Terms of Service](https://benavery28.github.io/Jobber-Quotes/terms-of-service.html)  

---

For support or questions, email: sales@shimmershine.org
