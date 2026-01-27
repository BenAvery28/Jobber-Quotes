# Quick Start: Testing Without a Domain

## The Problem
You need a public HTTPS URL for OAuth callbacks, but you don't have a domain.

## The Solution: ngrok (Free)

ngrok creates a public HTTPS tunnel to your local server. Perfect for testing!

## 3-Step Setup

### Step 1: Install ngrok
```bash
# macOS
brew install ngrok

# Or download from: https://ngrok.com/download
```

### Step 2: Start ngrok
```bash
# In a terminal, run:
ngrok http 8000
```

You'll see something like:
```
Forwarding  https://abc123xyz.ngrok-free.app -> http://localhost:8000
```

**Copy that HTTPS URL!** (e.g., `https://abc123xyz.ngrok-free.app`)

### Step 3: Configure Your App

1. **Update your `.env` file**:
```env
TEST_MODE=False
JOBBER_CLIENT_ID=your_client_id
JOBBER_CLIENT_SECRET=your_client_secret
JOBBER_REDIRECT_URI=https://abc123xyz.ngrok-free.app/oauth/callback
OPENWEATHER_API_KEY=your_weather_key
```

2. **In Jobber Developer Center**:
   - Go to your app settings
   - Set "Redirect URI" or "Callback URL" to: `https://abc123xyz.ngrok-free.app/oauth/callback`
   - **Must match exactly!**

3. **Start your app**:
```bash
uvicorn src.webapp:app --host 0.0.0.0 --port 8000
```

4. **Test OAuth**:
   - Open: `https://abc123xyz.ngrok-free.app/auth`
   - Complete the Jobber authorization
   - Done! Tokens are stored automatically.

## Important Notes

- **ngrok URL changes** each time you restart (free plan)
- **Update both** `.env` and Jobber Developer Center when URL changes
- **Keep ngrok running** while testing
- **Both servers needed**: Your app (port 8000) + ngrok tunnel

## Troubleshooting

**"State parameter mismatch"** → Start OAuth flow fresh from `/auth`

**"Token exchange failed"** → Check that callback URL matches exactly in both places

**Can't access ngrok URL** → Make sure your app is running on port 8000

## Full Guide

See `docs/local_testing_setup.md` for detailed instructions.

