# Local Testing Setup Guide (No Domain Required)

This guide shows you how to test the Jobber integration locally using ngrok, which creates a public HTTPS URL that tunnels to your local server.

## Prerequisites

1. **ngrok** installed ([download here](https://ngrok.com/download))
2. **Jobber Developer Account** with your app registered
3. **CLIENT_ID** and **CLIENT_SECRET** from Jobber Developer Center

## Step 1: Install and Set Up ngrok

### Install ngrok:
```bash
# macOS (using Homebrew)
brew install ngrok

# Or download from https://ngrok.com/download
```

### Create ngrok account (free):
1. Sign up at https://dashboard.ngrok.com/signup
2. Get your authtoken from the dashboard
3. Configure ngrok:
   ```bash
   ngrok config add-authtoken YOUR_AUTHTOKEN
   ```

## Step 2: Start Your Local Server

In one terminal, start your FastAPI application:

```bash
cd /Users/benkrysak/Projects/ShimmerShine
uvicorn src.webapp:app --host 0.0.0.0 --port 8000 --reload
```

Your app should now be running at `http://localhost:8000`

## Step 3: Start ngrok Tunnel

In a **second terminal**, start ngrok:

```bash
ngrok http 8000
```

You'll see output like:
```
Session Status                online
Account                       Your Name (Plan: Free)
Version                       3.x.x
Region                        United States (us)
Latency                       -
Web Interface                 http://127.0.0.1:4040
Forwarding                    https://abc123xyz.ngrok-free.app -> http://localhost:8000
```

**Important**: Copy the HTTPS URL (e.g., `https://abc123xyz.ngrok-free.app`)

**Note**: The free ngrok plan gives you a random URL each time. For testing, this is fine. If you need a stable URL, consider the paid plan.

## Step 4: Configure Your .env File

Update your `.env` file with:

```env
# Disable test mode
TEST_MODE=False

# Your Jobber credentials
JOBBER_CLIENT_ID=your_client_id_here
JOBBER_CLIENT_SECRET=your_client_secret_here

# Use your ngrok URL as the callback
JOBBER_REDIRECT_URI=https://abc123xyz.ngrok-free.app/oauth/callback

# Weather API (still needed)
OPENWEATHER_API_KEY=your_weather_key_here
```

**Important**: Replace `abc123xyz.ngrok-free.app` with your actual ngrok URL.

## Step 5: Register Callback URL in Jobber Developer Center

1. **Log into Jobber Developer Center**: https://developer.getjobber.com/
2. **Navigate to your app settings**
3. **Find "Redirect URI" or "Callback URL" field**
4. **Enter your ngrok callback URL**: `https://abc123xyz.ngrok-free.app/oauth/callback`
5. **Save the changes**

**Critical**: The callback URL in Jobber Developer Center must **exactly match** the `JOBBER_REDIRECT_URI` in your `.env` file, including:
- The protocol (`https://`)
- The domain (`abc123xyz.ngrok-free.app`)
- The path (`/oauth/callback`)
- No trailing slashes

## Step 6: Test the OAuth Flow

1. **Make sure both servers are running**:
   - Your FastAPI app on port 8000
   - ngrok tunnel

2. **Start OAuth flow**:
   - Open browser: `https://abc123xyz.ngrok-free.app/auth`
   - Or: `http://localhost:8000/auth` (if ngrok is forwarding correctly)

3. **You'll be redirected to Jobber**:
   - Log in with your Jobber admin account
   - Review the permissions (scopes)
   - Click "Allow Access"

4. **You'll be redirected back**:
   - Jobber redirects to: `https://abc123xyz.ngrok-free.app/oauth/callback?code=AUTHORIZATION_CODE&state=STATE`
   - Your app exchanges the code for tokens
   - You should see: "Authorization Successful! You can close this window."

5. **Verify tokens are stored**:
   - Check your application logs for: `"OAuth successful - Account: [Account Name]"`
   - Tokens are stored in your SQLite database (`oauth_tokens` table)

## Step 7: Test Webhook Delivery (Optional)

If you want to test webhooks locally:

1. **In Jobber Developer Center**, configure webhook URL:
   - Webhook URL: `https://abc123xyz.ngrok-free.app/webhook/jobber`
   - Enable topics: `QUOTE_APPROVED`, `APP_DISCONNECT`

2. **Create a test quote in Jobber**:
   - Create a quote
   - Approve the quote
   - Check your application logs for webhook processing

3. **Monitor ngrok dashboard**:
   - Visit: `http://127.0.0.1:4040` (ngrok web interface)
   - See all incoming requests and responses

## Troubleshooting

### Problem: "State parameter mismatch"
- **Cause**: OAuth state validation failed
- **Solution**: Start the OAuth flow fresh from `/auth` endpoint

### Problem: "Token exchange failed"
- **Cause**: Callback URL mismatch or invalid credentials
- **Solution**: 
  - Verify `JOBBER_REDIRECT_URI` in `.env` exactly matches Jobber Developer Center
  - Check that `JOBBER_CLIENT_ID` and `JOBBER_CLIENT_SECRET` are correct
  - Ensure ngrok is still running

### Problem: "Connection refused" when accessing ngrok URL
- **Cause**: Local server not running or ngrok not forwarding
- **Solution**:
  - Verify FastAPI is running on port 8000
  - Check ngrok is forwarding to `http://localhost:8000`
  - Restart ngrok if needed

### Problem: ngrok URL changes every time
- **Cause**: Free ngrok plan uses random URLs
- **Solution**: 
  - Update `.env` and Jobber Developer Center with new URL each time
  - Or upgrade to ngrok paid plan for static domain

### Problem: "Invalid webhook signature"
- **Cause**: Webhook secret mismatch
- **Solution**: Verify `JOBBER_CLIENT_SECRET` matches the secret in Developer Center

## Quick Test Checklist

- [ ] ngrok installed and configured
- [ ] FastAPI app running on port 8000
- [ ] ngrok tunnel active (check HTTPS URL)
- [ ] `.env` file has correct `JOBBER_REDIRECT_URI` (ngrok URL + `/oauth/callback`)
- [ ] Jobber Developer Center has matching callback URL
- [ ] OAuth flow completes successfully
- [ ] Tokens stored in database
- [ ] Can make API calls to Jobber

## Alternative: Using ngrok with Custom Domain (Paid)

If you upgrade to ngrok paid plan, you can:
1. Reserve a static domain (e.g., `your-app.ngrok.io`)
2. Use this domain in both `.env` and Jobber Developer Center
3. No need to update URLs each time you restart ngrok

## Next Steps After Local Testing

Once local testing works:
1. Deploy to a server (Heroku, AWS, DigitalOcean, etc.)
2. Update `JOBBER_REDIRECT_URI` to your production domain
3. Update callback URL in Jobber Developer Center
4. Test OAuth flow on production
5. Configure production webhook URL

