# Jobber Webhook Setup Guide

This guide explains how to configure real communication between your application and Jobber's API.

## Prerequisites

1. **Jobber Developer Account**: You need a Jobber account with developer access
2. **App Registration**: Your app must be registered in Jobber's Developer Center
3. **OAuth Credentials**: You'll receive `CLIENT_ID` and `CLIENT_SECRET` after app registration
4. **Public Webhook URL**: Your webhook endpoint must be publicly accessible (HTTPS required)

## Step 1: Configure Environment Variables

Create or update your `.env` file:

```env
# Disable test mode to use real Jobber API
TEST_MODE=False

# OAuth Credentials (from Jobber Developer Center)
JOBBER_CLIENT_ID=your_client_id_here
JOBBER_CLIENT_SECRET=your_client_secret_here

# OAuth Callback URL (must match registered URL in Developer Center)
JOBBER_REDIRECT_URI=https://yourdomain.com/oauth/callback

# Weather API (still required)
OPENWEATHER_API_KEY=your_weather_key_here
```

**Important**: The `JOBBER_REDIRECT_URI` must exactly match the callback URL registered in Jobber's Developer Center.

## Step 2: Complete OAuth Authorization

1. **Start the OAuth flow**:
   - Navigate to: `https://yourdomain.com/auth`
   - Or: `http://localhost:8000/auth` (for local testing with ngrok)

2. **Authorize the app**:
   - You'll be redirected to Jobber's authorization page
   - Log in with your Jobber admin account
   - Review and approve the requested permissions (scopes)
   - Click "Allow Access"

3. **Receive tokens**:
   - After authorization, you'll be redirected back to your callback URL
   - The app automatically exchanges the authorization code for access and refresh tokens
   - Tokens are stored in the database (`oauth_tokens` table)

4. **Verify connection**:
   - Check application logs for: `"OAuth successful - Account: [Account Name]"`
   - The access token is valid for 60 minutes and will auto-refresh

## Step 3: Configure Webhooks in Jobber

1. **Log into Jobber Developer Center**
2. **Navigate to your app settings**
3. **Configure Webhook URL**:
   - Webhook URL: `https://yourdomain.com/webhook/jobber`
   - Must use HTTPS (not HTTP)
   - Must be publicly accessible

4. **Select Webhook Topics**:
   - Required: `QUOTE_APPROVED` (for automatic booking)
   - Recommended: `QUOTE_UPDATE` (for quote changes)
   - Required for Marketplace: `APP_DISCONNECT` (for disconnect handling)

5. **Save webhook configuration**

## Step 4: Test Webhook Delivery

### Using ngrok (for local development):

1. **Start ngrok**:
   ```bash
   ngrok http 8000
   ```

2. **Update webhook URL in Jobber**:
   - Use the ngrok HTTPS URL: `https://xxxx-xx-xx-xx-xx.ngrok.io/webhook/jobber`

3. **Test webhook**:
   - Create a test quote in Jobber
   - Approve the quote
   - Check your application logs for webhook processing

### Production Testing:

1. **Use a test Jobber account** (if available)
2. **Create and approve a test quote**
3. **Monitor logs** for:
   - Webhook signature verification
   - Quote processing
   - Job creation in Jobber
   - Visit scheduling

## Step 5: Verify Token Refresh

Access tokens expire after 60 minutes. The application automatically refreshes them:

1. **Automatic refresh**: Happens when token expires or is about to expire (within 5 minutes)
2. **On 401 errors**: If a request fails with 401, the app attempts token refresh
3. **Refresh token rotation**: If enabled in Jobber, new refresh tokens are stored automatically

## Troubleshooting

### OAuth Issues

**Problem**: "Not authorized - please complete OAuth flow at /auth"
- **Solution**: Navigate to `/auth` and complete the OAuth flow

**Problem**: "State parameter mismatch"
- **Solution**: This is a security check. Try the OAuth flow again from the beginning

**Problem**: "Token exchange failed"
- **Solution**: 
  - Verify `JOBBER_CLIENT_ID` and `JOBBER_CLIENT_SECRET` are correct
  - Ensure `JOBBER_REDIRECT_URI` matches exactly what's registered in Developer Center
  - Check that the authorization code hasn't expired (codes expire quickly)

### Webhook Issues

**Problem**: "Invalid webhook signature"
- **Solution**: 
  - Verify `JOBBER_CLIENT_SECRET` matches the secret in Developer Center
  - Ensure the webhook payload hasn't been modified
  - Check that you're using the correct secret (not the client ID)

**Problem**: "Invalid appId in webhook"
- **Solution**: 
  - Verify `JOBBER_CLIENT_ID` matches your app's client ID
  - Some older webhooks may not include appId (this is OK, signature verification is primary)

**Problem**: Webhooks not being received
- **Solution**:
  - Verify webhook URL is publicly accessible
  - Check that HTTPS is used (HTTP is not allowed)
  - Ensure webhook topics are enabled in Developer Center
  - Check firewall/network settings

### Token Refresh Issues

**Problem**: "Token refresh failed"
- **Solution**:
  - Refresh tokens may have expired (requires re-authorization)
  - App may have been disconnected in Jobber (check for APP_DISCONNECT webhook)
  - Client secret may have been rotated (requires re-authorization)

**Problem**: "No refresh token available"
- **Solution**: Complete OAuth flow again at `/auth`

## App Disconnect Handling

The application automatically handles app disconnects:

1. **User disconnects in Jobber**: 
   - Jobber sends `APP_DISCONNECT` webhook
   - Application clears all stored tokens
   - Future API calls will require re-authorization

2. **App disconnects from your system**:
   - Call the `appDisconnect` GraphQL mutation
   - This notifies Jobber and invalidates tokens
   - Example code:
     ```python
     client = JobberClient(access_token)
     await client.disconnect_app()
     ```

## Security Best Practices

1. **Never commit secrets**: Keep `.env` file out of version control
2. **Use HTTPS**: Always use HTTPS for webhooks and OAuth callbacks
3. **Validate webhooks**: Always verify webhook signatures
4. **Rotate secrets**: If `JOBBER_CLIENT_SECRET` is compromised, rotate it in Developer Center
5. **Monitor logs**: Watch for unauthorized access attempts or token refresh failures

## Next Steps

After setup is complete:

1. **Monitor logs** for successful webhook processing
2. **Test with real quotes** in a test Jobber account
3. **Verify job creation** in Jobber after quote approval
4. **Check visit scheduling** matches your business rules
5. **Set up alerts** for token expiration or webhook failures

## Support

For issues with:
- **Jobber API**: Check [Jobber API Documentation](https://developer.getjobber.com/)
- **This Application**: Check application logs and error messages
- **OAuth Flow**: Verify all environment variables and registered URLs match exactly

