# Production Readiness Checklist

Before switching `TEST_MODE=False`, ensure all these items are completed and tested.

## Environment Configuration

### Required Environment Variables
- [ ] `JOBBER_CLIENT_ID` - Your Jobber OAuth client ID
- [ ] `JOBBER_CLIENT_SECRET` - Your Jobber OAuth client secret  
- [ ] `OPENWEATHER_API_KEY` - Your OpenWeatherMap API key
- [ ] `TEST_MODE=False` - Switch to production mode

### Optional Environment Variables
- [ ] `JOBBER_REDIRECT_URI` - OAuth callback URL (defaults to localhost:8000)
- [ ] `PORTAL_BASE_URL` - Base URL for customer portal links

## API Access Verification

### Jobber API
- [ ] Jobber app approved and credentials provided
- [ ] OAuth scopes include necessary permissions:
  - Read clients and properties
  - Read and write jobs
  - Send client messages
- [ ] Test OAuth flow works with real credentials
- [ ] GraphQL queries return expected data structure

### Weather API  
- [ ] OpenWeatherMap account created
- [ ] API key has sufficient quota (1000 calls/day minimum)
- [ ] 5-day forecast endpoint returns expected data format
- [ ] Geocoding works for your service area cities

## Database Setup

### SQLite Databases
- [ ] `jobber_calendar.db` - Main scheduling database
- [ ] `tokens.db` - OAuth token storage
- [ ] Both databases have proper write permissions
- [ ] Backup strategy for production data

## API Endpoints Testing

### Core Functionality
- [ ] `POST /book-job` - Webhook processing
- [ ] `GET /auth` - OAuth initiation
- [ ] `GET /oauth/callback` - OAuth completion
- [ ] `GET /jobber-status` - Integration health check

### Weather Integration
- [ ] `GET /weather-check` - Weather-based rescheduling
- [ ] `GET /weather-forecast/{city}` - Forecast data retrieval
- [ ] Weather thresholds (>50% rain, thunderstorms) work correctly

### Schedule Management  
- [ ] `POST /cancel-appointment` - Cancellation handling
- [ ] `POST /optimize-schedule` - Schedule compaction
- [ ] `GET /schedule-status` - Current status overview

## Error Handling

### API Failures
- [ ] Graceful handling of Jobber API timeouts
- [ ] Weather API fallback behavior
- [ ] Token refresh on expiration
- [ ] Proper HTTP status codes returned

### Data Validation
- [ ] Invalid webhook payloads rejected
- [ ] Missing required fields handled
- [ ] Malformed dates/times caught
- [ ] Client ID validation

## Security Considerations

### Authentication
- [ ] OAuth state parameter validation
- [ ] Token storage encrypted/secure
- [ ] HTTPS enabled for production URLs
- [ ] Webhook signature verification (if required by Jobber)

### Data Protection
- [ ] Client data handling complies with privacy requirements
- [ ] No sensitive data logged
- [ ] Database access restricted
- [ ] Environment variables secured

## Deployment Infrastructure

### Server Requirements
- [ ] Python 3.9+ with all dependencies
- [ ] Persistent storage for databases
- [ ] Proper logging configuration
- [ ] Process monitoring/restart capability

### Network Configuration
- [ ] Webhook endpoint accessible to Jobber
- [ ] OAuth redirect URI matches registered URL
- [ ] Firewall allows necessary API connections
- [ ] SSL certificate valid

## Testing Protocol

### Pre-Deployment Tests
- [ ] Run `python testing/test_production_api_calls.py`
- [ ] All tests pass without errors
- [ ] Real API calls return expected data
- [ ] Token management works correctly

### Post-Deployment Verification
- [ ] Complete OAuth flow with Jobber
- [ ] Process at least one real webhook
- [ ] Verify job created in Jobber calendar
- [ ] Check weather data updates correctly
- [ ] Monitor logs for errors

## Monitoring Setup

### Health Checks
- [ ] `/jobber-status` endpoint monitoring
- [ ] Database connection health
- [ ] API quota usage tracking
- [ ] Weather API availability

### Alerting
- [ ] Failed webhook processing alerts
- [ ] Token expiration warnings  
- [ ] API quota threshold notifications
- [ ] Database error monitoring

## Documentation

### Operations Manual
- [ ] API endpoint documentation
- [ ] Error code reference
- [ ] Troubleshooting guide
- [ ] Backup/restore procedures

### Integration Guide
- [ ] Jobber webhook configuration steps
- [ ] OAuth app registration process
- [ ] Environment variable setup
- [ ] Deployment instructions

## Rollback Plan

### Immediate Rollback
- [ ] Set `TEST_MODE=True` to disable API calls
- [ ] Restart application with test configuration
- [ ] Verify test mode functionality
- [ ] Document issues encountered

### Data Recovery
- [ ] Database backup/restore procedure
- [ ] Token re-authentication process
- [ ] Schedule data verification
- [ ] Client notification plan

---

## Quick Production Test Command

Run this to verify production readiness:

```bash
# Set production mode temporarily
export TEST_MODE=False

# Run comprehensive test
python testing/test_production_api_calls.py

# Check specific endpoints
curl -X GET http://localhost:8000/jobber-status
curl -X GET http://localhost:8000/weather-forecast/Saskatoon

# Restore test mode
export TEST_MODE=True
```

## Common Issues and Solutions

### Token Issues
- **Problem**: 401 Unauthorized errors
- **Solution**: Re-run OAuth flow, check token expiration
- **Prevention**: Monitor token refresh logs

### Weather API Issues  
- **Problem**: Quota exceeded or API key invalid
- **Solution**: Check OpenWeatherMap account, upgrade plan if needed
- **Prevention**: Monitor API usage, implement caching

### Jobber API Issues
- **Problem**: GraphQL schema changes or permissions
- **Solution**: Update queries, request additional scopes
- **Prevention**: Subscribe to Jobber API announcements

### Database Issues
- **Problem**: Lock errors or corruption
- **Solution**: Restart application, restore from backup
- **Prevention**: Regular backups, proper connection handling