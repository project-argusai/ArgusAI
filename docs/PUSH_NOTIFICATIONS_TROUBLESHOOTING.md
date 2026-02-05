# Push Notifications Troubleshooting Guide

**Related Issues**: #351 (Push Notifications Bug), #373 (Investigation findings)

This guide helps diagnose and fix push notification delivery issues in ArgusAI.

---

## Quick Diagnostic

Run the diagnostic tools:

```bash
# Bash script (quick checks)
bash scripts/diagnose-push-notifications-enhanced.sh

# Or Python diagnostic (database checks)
python3 scripts/test-push-notifications.py diagnose
```

---

## Common Symptoms & Causes

### ❌ "Push notifications not working at all"

**Root Causes** (in order of likelihood):
1. **HTTPS not configured** - Push requires valid SSL/TLS
2. **Service Worker not registered** - Browser console errors
3. **Browser permission denied** - User blocked notification permission
4. **Database not persisting subscriptions** - Subscription data not saved

**Fix Process**:
1. Check HTTPS: `bash scripts/diagnose-push-notifications-enhanced.sh`
2. Open DevTools (F12) → Console → look for errors
3. Check browser notification permissions in Settings
4. Verify subscriptions in database: `python3 scripts/test-push-notifications.py subscriptions`

---

### ❌ "Notifications subscribed but not delivered"

**Root Causes**:
1. **Push service endpoint invalid** - Subscription expired or corrupted
2. **Quiet hours blocking** - Notifications filtered by time
3. **Camera/type preferences filtering** - Notification preferences blocking events
4. **WebPush library exception** - Backend error sending to push service

**Diagnosis**:
```python
# Run Python diagnostic
python3 scripts/test-push-notifications.py test-send  # Test delivery

# Check preferences
python3 scripts/test-push-notifications.py preferences
```

**Solutions**:
1. Hard reload and re-subscribe: Ctrl+Shift+R then browser will re-subscribe
2. Check quiet hours aren't active: Settings → Notifications → Quiet Hours
3. Check camera is enabled in preferences: Settings → Notifications → Cameras
4. Check backend logs: `tail -f logs/backend.log | grep -i push`

---

### ❌ "Service Worker registration fails"

**Browser Console Error**: `TypeError: Failed to register ServiceWorker`

**Root Causes**:
1. **HTTPS certificate invalid** - Self-signed cert for non-localhost domain
2. **Certificate chain incomplete** - Missing intermediate certificates
3. **Mixed HTTP/HTTPS content** - Some resources load over HTTP
4. **Service Worker script 404** - sw.js file not found or wrong path

**Fixes**:

**For localhost (development)**:
```bash
# Self-signed cert is fine for localhost, just ensure HTTPS works
curl -k https://localhost:3000/api/v1/push/vapid-public-key
```

**For custom domain (production)**:
```bash
# Use Let's Encrypt instead of self-signed
certbot certonly --standalone -d argusai.yourdomain.com

# Copy certificates to backend/certs/
cp /etc/letsencrypt/live/argusai.yourdomain.com/fullchain.pem backend/certs/cert.pem
cp /etc/letsencrypt/live/argusai.yourdomain.com/privkey.pem backend/certs/key.pem

# Restart server to use new certificates
```

**Check Service Worker registration**:
1. DevTools → Application tab
2. Expand "Service Workers" section
3. Should see: `https://your-domain/sw.js` with status "activated"
4. If it says "installing" or has error, click for details

---

### ❌ "WebPush HTTP 410 error"

**Symptom**: Backend logs show `HTTP 410 Gone` when sending notification

**Cause**: Push service endpoint has expired or been revoked

**Why it happens**:
- Browser unsubscribed from push service
- Push service credentials rotated
- Subscription too old (>~1 year)
- Multiple registrations with same credentials

**Fix**:
1. Clear browser site data:
   - Settings → Privacy → Clear browsing data → Cookies/Site data
   - Check "Hosted app data"
2. Hard reload: Ctrl+Shift+R
3. Browser will automatically re-subscribe
4. New subscription will work

---

### ❌ "WebPush HTTP 401/403 error"

**Symptom**: Backend logs show authentication failure to push service

**Causes**:
1. VAPID keys invalid or corrupted
2. VAPID key format wrong (not valid PEM)
3. Push service key mismatch

**Diagnosis**:
```bash
# Check VAPID keys are generated
python3 scripts/test-push-notifications.py vapid

# Output should show valid public key
```

**Fix**:
```bash
# Regenerate VAPID keys in database
cd backend && python3 -c "
from app.utils.vapid import ensure_vapid_keys, delete_vapid_keys
from app.core.database import SessionLocal

db = SessionLocal()
# Delete old keys
delete_vapid_keys(db)
# Regenerate
private_key, public_key = ensure_vapid_keys(db)
print(f'VAPID keys regenerated: {public_key[:50]}...')
db.close()
"
```

---

### ❌ "Quiet hours blocking all notifications"

**Symptom**: Notifications work sometimes but not during certain hours

**Root Cause**: Quiet hours preference enabled

**Check & Fix**:
```bash
# Check notification preferences
python3 scripts/test-push-notifications.py preferences

# Look for:
# - "Quiet Hours: ✓" - quiet hours enabled
# - "Time: 22:00 - 06:00" - specific time range

# To disable:
# 1. Open ArgusAI web interface
# 2. Settings → Notifications → Quiet Hours
# 3. Toggle OFF or adjust time range
```

---

### ❌ "Notifications filtered by camera/type"

**Symptom**: Some events trigger notifications, others don't

**Root Cause**: Notification preferences filtering by camera or detection type

**Check which are enabled**:
```bash
# View preferences
python3 scripts/test-push-notifications.py preferences

# Or check database directly:
# SELECT * FROM notification_preference
# WHERE subscription_id = '...'
```

**Fix**:
1. Settings → Notifications
2. Under "Cameras" section - ensure cameras are checked
3. Under "Detection Types" - ensure types you want are checked
4. Click Save

---

## Step-by-Step Troubleshooting

### Step 1: Verify HTTPS is Working

```bash
# Test HTTPS endpoint
curl -k https://localhost:3000/api/v1/push/vapid-public-key

# Should return JSON with public_key field
# If using custom domain, remove -k flag and ensure cert is valid
```

**If HTTPS fails**:
- Check `backend/certs/cert.pem` and `backend/certs/key.pem` exist
- Verify certificate is not expired: `openssl x509 -in backend/certs/cert.pem -noout -dates`
- If self-signed for custom domain: Use Let's Encrypt instead

---

### Step 2: Check Browser Service Worker

1. Open DevTools (F12)
2. Go to **Application** tab
3. Click **Service Workers** (left sidebar)
4. Look for entry with path `/sw.js`

**Expected states**:
- ✓ **activated and running** - OK
- ⏳ **installing** - Wait a moment, then reload
- ❌ **error with red X** - Service Worker registration failed

**If registration failed**:
1. Click the error to see details
2. Check **Console** tab for JavaScript errors
3. Most common: Certificate not trusted or sw.js not found

---

### Step 3: Check Browser Notifications Permission

1. Click **🔒 Lock icon** in address bar
2. Find **Notifications** permission
3. If it says **Block** → Click and change to **Ask**
4. Reload page
5. Click **Allow** when prompted

**If "Block" option grayed out**:
- Settings → Privacy → Site permissions → Notifications
- Find your site and remove it
- Reload page and grant permission again

---

### Step 4: Verify Subscription in Database

```bash
# List all subscriptions
python3 scripts/test-push-notifications.py subscriptions

# Should show:
# - ID (UUID)
# - Endpoint (push service URL)
# - Created date
# - Last used date
```

**If no subscriptions**:
- Subscriptions created when user clicks "Subscribe" in UI
- Check UI has subscription button
- Open browser console during subscription attempt
- Look for errors like "NotAllowedError: permission denied"

---

### Step 5: Send Test Notification

```bash
# Send to first subscription
python3 scripts/test-push-notifications.py test-send

# Or test event notification
python3 scripts/test-push-notifications.py test-event

# Watch browser notification appear in bottom right
# Check browser notification settings - may be muted
```

**If test notification works but real notifications don't**:
- Real events may be filtered by preferences (quiet hours, camera, type)
- Check notification preferences: `python3 scripts/test-push-notifications.py preferences`

---

### Step 6: Check Backend Logs

```bash
# Search for push-related errors
tail -f logs/backend.log | grep -i "push\|notification\|webpush"

# Or search for specific subscription
tail -f logs/backend.log | grep "SUBSCRIPTION_ID"

# Common error patterns:
# - "HTTP 410" → subscription expired
# - "HTTP 401/403" → VAPID key issue  
# - "WebPushException" → push service error
```

---

## Advanced Debugging

### Enable Debug Logging

```bash
# Set log level to DEBUG
export LOG_LEVEL=DEBUG

# Restart backend
./scripts/deploy.sh  # or your startup script
```

**Debug output will show**:
- Each subscription being sent
- VAPID key validation
- Push service responses
- Preference filtering decisions

### Inspect Network Requests

1. DevTools → **Network** tab
2. Subscribe to push notifications
3. Look for requests to:
   - `/api/v1/push/vapid-public-key` - Should be 200 OK
   - `/api/v1/push/subscribe` - Should be 200 OK with subscription response

4. Check response headers for:
   - `Content-Type: application/json`
   - `Access-Control-Allow-Origin: *` (if CORS needed)

### Check Push Service Connectivity

```bash
# Extract endpoint from database
ENDPOINT=$(sqlite3 argusai.db "SELECT endpoint FROM push_subscription LIMIT 1;")

# Try to reach push service endpoint
curl -v "$ENDPOINT"

# Should get 405 Method Not Allowed or similar
# If connection times out → firewall/network issue
```

### Trace Service Worker Execution

In browser console (F12):

```javascript
// Register service worker with logging
navigator.serviceWorker.register('/sw.js')
  .then(reg => {
    console.log('✓ Service Worker registered:', reg);
    
    // Listen for push events
    navigator.serviceWorker.addEventListener('message', event => {
      console.log('Push received:', event.data);
    });
  })
  .catch(err => {
    console.error('✗ Service Worker failed:', err);
  });

// Subscribe to push
navigator.serviceWorker.ready
  .then(reg => {
    return reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: new Uint8Array([/* public_key_bytes */])
    });
  })
  .then(sub => {
    console.log('✓ Subscribed:', sub);
    console.log('Endpoint:', sub.endpoint);
  })
  .catch(err => {
    console.error('✗ Subscription failed:', err);
  });
```

---

## Database Queries for Debugging

### Check Subscription Status

```sql
-- Count subscriptions
SELECT COUNT(*) FROM push_subscription;

-- List subscriptions with creation and last use
SELECT id, endpoint, created_at, last_used_at 
FROM push_subscription 
ORDER BY created_at DESC;

-- Find subscriptions not used in 7 days (might be stale)
SELECT id, endpoint, last_used_at
FROM push_subscription
WHERE last_used_at < NOW() - INTERVAL '7 days' OR last_used_at IS NULL;
```

### Check Preferences

```sql
-- Get preferences for all subscriptions
SELECT 
  sub.id,
  pref.quiet_hours_enabled,
  pref.quiet_hours_start,
  pref.quiet_hours_end,
  pref.sound_enabled
FROM push_subscription sub
LEFT JOIN notification_preference pref ON sub.id = pref.subscription_id;

-- Check if quiet hours are currently active
SELECT CURRENT_TIME BETWEEN '22:00'::TIME AND '06:00'::TIME as in_quiet_hours;
```

### Check VAPID Keys

```sql
-- Verify VAPID keys in database
SELECT key, value FROM system_setting 
WHERE key LIKE '%vapid%';

-- Check when they were created
SELECT key, created_at FROM system_setting
WHERE key LIKE '%vapid%';
```

---

## Performance Optimization

If sending notifications is slow:

### Check Subscription Count

```bash
python3 scripts/test-push-notifications.py subscriptions | wc -l
```

**If > 1000 subscriptions**:
- Batch notifications: Process in groups of 100
- Use database pagination
- Consider archiving old subscriptions

### Check WebPush Library Performance

```python
# Check retry counts in logs
tail logs/backend.log | grep "retries:" | sort | uniq -c

# High retry counts indicate:
# - Slow push service
# - Network latency
# - Consider increasing timeout
```

### Database Query Performance

```bash
# Check if notification preference queries are slow
# Enable EXPLAIN ANALYZE in logs
tail logs/backend.log | grep "EXPLAIN ANALYZE"
```

---

## Recovery & Reset

### Reset All Subscriptions

```bash
# WARNING: This removes all push subscriptions!
python3 -c "
from app.core.database import SessionLocal
from app.models.push_subscription import PushSubscription

db = SessionLocal()
count = db.query(PushSubscription).count()
db.query(PushSubscription).delete()
db.commit()
print(f'Deleted {count} subscriptions')
db.close()
"

# Users will need to re-subscribe in browser
```

### Clear Stale Subscriptions

```bash
# Delete subscriptions not used in 30 days
python3 -c "
from datetime import datetime, timezone, timedelta
from app.core.database import SessionLocal
from app.models.push_subscription import PushSubscription

db = SessionLocal()
cutoff = datetime.now(timezone.utc) - timedelta(days=30)
deleted = db.query(PushSubscription).filter(
    (PushSubscription.last_used_at < cutoff) |
    (PushSubscription.last_used_at == None)
).delete()
db.commit()
print(f'Deleted {deleted} stale subscriptions')
db.close()
"
```

### Regenerate VAPID Keys

```bash
python3 -c "
from app.core.database import SessionLocal
from app.models.system_setting import SystemSetting
from app.utils.vapid import delete_vapid_keys, ensure_vapid_keys

db = SessionLocal()

# Delete old keys
db.query(SystemSetting).filter(
    SystemSetting.key.like('%vapid%')
).delete()
db.commit()

# Generate new keys
private_key, public_key = ensure_vapid_keys(db)
print('VAPID keys regenerated')
print(f'Public key: {public_key[:50]}...')
"

# Note: Existing subscriptions will be invalid with new VAPID keys
# Clients will need to re-subscribe
```

---

## Health Check API

Add this to check push notification health:

```python
# GET /api/v1/push/health
@router.get("/health")
async def push_health(db: Session = Depends(get_db)):
    \"\"\"Check push notification system health.\"\"\"
    return {
        "vapid_configured": check_vapid_keys(db),
        "subscriptions": db.query(PushSubscription).count(),
        "active_preferences": db.query(NotificationPreference).count(),
        "https_required": True,
        "status": "healthy" if subscriptions > 0 else "no_subscriptions"
    }
```

---

## References

- **Code**: `backend/app/services/push_notification_service.py`
- **API**: `backend/app/api/v1/push.py`
- **Frontend**: `frontend/hooks/usePushNotifications.ts`
- **Schema**: `backend/app/models/push_subscription.py`
- **Issues**: #351 (Bug), #373 (Investigation)

---

## Getting Help

If troubleshooting doesn't resolve the issue:

1. Gather diagnostics:
   ```bash
   bash scripts/diagnose-push-notifications-enhanced.sh > diagnostics.txt
   python3 scripts/test-push-notifications.py diagnose >> diagnostics.txt
   ```

2. Check backend logs:
   ```bash
   tail -100 logs/backend.log > backend-logs.txt
   ```

3. Open issue with:
   - diagnostics.txt output
   - backend logs
   - Browser console errors (screenshot or paste)
   - OS and browser version
   - Description of what you've tried

---

**Last Updated**: 2025-02-03
**Maintainer**: ArgusAI Team
**Status**: Actively maintained for Issue #351
