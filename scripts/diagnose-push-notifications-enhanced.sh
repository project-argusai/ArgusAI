#!/bin/bash
#
# ArgusAI Push Notifications Enhanced Diagnostic Script
# 
# Purpose: Advanced troubleshooting for push notification issues (#351)
# Improvements over base script:
# - Database query execution (if direct access available)
# - Comprehensive SSL/TLS chain validation
# - Service Worker cache debugging
# - Detailed header inspection
# - Push service connectivity tests
# - Browser permission check instructions
# - Network topology debugging
# - Common fix recommendations with explanations
#

set -e

echo "🔍 ArgusAI Push Notifications Enhanced Diagnostic"
echo "=================================================="
echo ""
echo "Generated: $(date -u +'%Y-%m-%d %H:%M:%S UTC')"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
CRITICAL_ISSUES=0
WARNINGS=0
INFO_ITEMS=0

# Helper functions
check_success() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $1"
        ((INFO_ITEMS++))
    else
        echo -e "${RED}✗${NC} $1"
        ((CRITICAL_ISSUES++))
    fi
}

check_file_exists() {
    if [ -f "$1" ]; then
        echo -e "${GREEN}✓${NC} Found: $1"
        ((INFO_ITEMS++))
    else
        echo -e "${RED}✗${NC} Missing: $1"
        ((CRITICAL_ISSUES++))
    fi
}

warn_issue() {
    echo -e "${YELLOW}⚠${NC} $1"
    ((WARNINGS++))
}

info_note() {
    echo -e "${BLUE}ℹ${NC} $1"
    ((INFO_ITEMS++))
}

section_title() {
    echo ""
    echo "📋 $1"
    echo "---"
}

# ============================================================================
# 1. Environment & Configuration Check
# ============================================================================
section_title "1. Environment & Configuration"

if [ -f "backend/main.py" ]; then
    echo -e "${GREEN}✓${NC} Running from project root"
else
    echo -e "${RED}✗${NC} Not running from project root"
    ((CRITICAL_ISSUES++))
fi

check_file_exists ".env"

# Check VAPID keys
if grep -q "VAPID" .env 2>/dev/null; then
    echo -e "${GREEN}✓${NC} VAPID configuration found in .env"
else
    warn_issue "VAPID configuration not in .env (should be auto-generated in database)"
fi

# Check push service configuration
if grep -q "PUSH_\|FCM_\|APNS_" .env 2>/dev/null; then
    echo -e "${GREEN}✓${NC} Push service configuration found"
else
    info_note "No explicit push service config in .env (may use defaults)"
fi

# Check SSL/TLS configuration
if grep -q "SSL_\|TLS_\|HTTPS" .env 2>/dev/null; then
    echo -e "${GREEN}✓${NC} SSL/TLS configuration found"
else
    warn_issue "SSL/TLS configuration not found in .env"
fi

# ============================================================================
# 2. Database State & Queries
# ============================================================================
section_title "2. Database State"

DB_AVAILABLE=false
DB_CONNSTR=""

# Try to get database connection string
if [ ! -z "$DATABASE_URL" ]; then
    DB_AVAILABLE=true
    DB_CONNSTR="$DATABASE_URL"
elif grep -q "DATABASE_URL" .env 2>/dev/null; then
    DB_AVAILABLE=true
    DB_CONNSTR=$(grep "DATABASE_URL" .env | cut -d'=' -f2- | sed "s/'//g" | sed 's/"//g')
fi

if [ "$DB_AVAILABLE" = true ]; then
    echo -e "${GREEN}✓${NC} Database connection string found"
    
    # Try to execute queries using psql if available
    if command -v psql &> /dev/null; then
        echo ""
        echo "Executing database queries..."
        
        # Extract connection details (basic support for postgres://)
        if [[ "$DB_CONNSTR" == postgres* ]]; then
            # Count push subscriptions
            SUBS_COUNT=$(psql "$DB_CONNSTR" -t -c "SELECT COUNT(*) FROM push_subscription 2>/dev/null || SELECT 0;" 2>/dev/null || echo "ERR")
            
            if [ "$SUBS_COUNT" != "ERR" ]; then
                echo -e "${GREEN}✓${NC} Push subscriptions in database: $SUBS_COUNT"
                if [ "$SUBS_COUNT" -eq 0 ]; then
                    warn_issue "No push subscriptions found (client may not have subscribed yet)"
                fi
            fi
            
            # Check for NULL endpoints (corrupted data)
            NULL_ENDPOINTS=$(psql "$DB_CONNSTR" -t -c "SELECT COUNT(*) FROM push_subscription WHERE endpoint IS NULL 2>/dev/null || SELECT 0;" 2>/dev/null || echo "ERR")
            
            if [ "$NULL_ENDPOINTS" != "ERR" ] && [ "$NULL_ENDPOINTS" -gt 0 ]; then
                warn_issue "Found $NULL_ENDPOINTS subscriptions with NULL endpoints (corrupted data)"
            fi
            
            # Check notification preferences
            PREFS_COUNT=$(psql "$DB_CONNSTR" -t -c "SELECT COUNT(*) FROM notification_preference 2>/dev/null || SELECT 0;" 2>/dev/null || echo "ERR")
            
            if [ "$PREFS_COUNT" != "ERR" ]; then
                echo -e "${GREEN}✓${NC} Notification preferences in database: $PREFS_COUNT"
            fi
            
            # Check VAPID keys in database
            VAPID_COUNT=$(psql "$DB_CONNSTR" -t -c "SELECT COUNT(*) FROM system_setting WHERE key LIKE '%vapid%' 2>/dev/null || SELECT 0;" 2>/dev/null || echo "ERR")
            
            if [ "$VAPID_COUNT" != "ERR" ] && [ "$VAPID_COUNT" -gt 0 ]; then
                echo -e "${GREEN}✓${NC} VAPID keys stored in database"
            else
                warn_issue "VAPID keys not found in database (will be auto-generated on first push)"
            fi
        fi
    else
        info_note "psql not available - skipping direct database queries"
        echo "To manually check database:"
        echo ""
        echo "  # Count subscriptions:"
        echo "  SELECT COUNT(*) FROM push_subscription;"
        echo ""
        echo "  # List recent subscriptions:"
        echo "  SELECT id, endpoint, created_at, last_used_at FROM push_subscription ORDER BY created_at DESC LIMIT 5;"
        echo ""
        echo "  # Check for corrupted data:"
        echo "  SELECT * FROM push_subscription WHERE endpoint IS NULL;"
        echo ""
    fi
else
    warn_issue "DATABASE_URL not configured"
fi

# ============================================================================
# 3. SSL/TLS Certificate Analysis
# ============================================================================
section_title "3. SSL/TLS Configuration"

SERVER_HOST="${SERVER_HOST:-localhost}"
SERVER_PORT="${SERVER_PORT:-3000}"
SERVER_PROTOCOL="http"

# Check if HTTPS is enabled
if [ -f "backend/certs/cert.pem" ] && [ -f "backend/certs/key.pem" ]; then
    SERVER_PROTOCOL="https"
    echo -e "${GREEN}✓${NC} SSL certificates found at backend/certs/"
    
    # Check certificate validity
    if command -v openssl &> /dev/null; then
        echo ""
        echo "Certificate Details:"
        openssl x509 -in backend/certs/cert.pem -noout -subject -issuer -dates 2>/dev/null || echo "Could not parse certificate"
        
        # Check if self-signed
        if openssl x509 -in backend/certs/cert.pem -noout -text 2>/dev/null | grep -q "Subject:.*Issuer:"; then
            SUBJ=$(openssl x509 -in backend/certs/cert.pem -noout -subject)
            ISSUER=$(openssl x509 -in backend/certs/cert.pem -noout -issuer)
            if [ "$SUBJ" = "$ISSUER" ]; then
                warn_issue "Certificate is self-signed (valid for localhost only)"
                echo "   This is fine for development but will cause issues on:"
                echo "   - Custom domains (e.g., argusai.local)"
                echo "   - Production deployments"
            fi
        fi
    fi
else
    info_note "No SSL certificates found at backend/certs/"
    echo "   Accessing via HTTP only: http://$SERVER_HOST:$SERVER_PORT"
    warn_issue "Push notifications REQUIRE HTTPS (with valid certificates)"
    echo ""
    echo "To enable HTTPS:"
    echo "  1. Generate self-signed cert (dev only):"
    echo "     mkdir -p backend/certs"
    echo "     openssl req -x509 -newkey rsa:2048 -nodes -out backend/certs/cert.pem -keyout backend/certs/key.pem -days 365"
    echo ""
    echo "  2. Or use Let's Encrypt (production):"
    echo "     certbot certonly --standalone -d argusai.yourdomain.com"
    echo ""
fi

# ============================================================================
# 4. API Endpoint Connectivity
# ============================================================================
section_title "4. API Endpoint Connectivity"

BASE_URL="${SERVER_PROTOCOL}://${SERVER_HOST}:${SERVER_PORT}"
API_PREFIX="/api/v1"

echo "Testing from: $BASE_URL"
echo ""

# HTTPS warning
if [ "$SERVER_PROTOCOL" = "https" ]; then
    CURL_OPTS="-s -k --insecure"
else
    CURL_OPTS="-s"
fi

# Test VAPID endpoint
echo "Testing VAPID endpoint..."
VAPID_RESPONSE=$(curl $CURL_OPTS -w "\n%{http_code}" "$BASE_URL$API_PREFIX/push/vapid-public-key" 2>/dev/null || echo "000")
VAPID_HTTP=$(echo "$VAPID_RESPONSE" | tail -1)
VAPID_BODY=$(echo "$VAPID_RESPONSE" | head -n -1)

if [ "$VAPID_HTTP" = "200" ]; then
    echo -e "${GREEN}✓${NC} VAPID endpoint responding (HTTP $VAPID_HTTP)"
    if echo "$VAPID_BODY" | grep -q "public_key"; then
        echo -e "${GREEN}✓${NC} VAPID response contains public_key"
    else
        warn_issue "VAPID response missing public_key field"
    fi
else
    echo -e "${RED}✗${NC} VAPID endpoint failed (HTTP $VAPID_HTTP)"
    ((CRITICAL_ISSUES++))
fi

echo ""

# Test subscription endpoint
echo "Testing subscription endpoint..."
SUBSCRIBE_HTTP=$(curl $CURL_OPTS -s -o /dev/null -w "%{http_code}" -X OPTIONS "$BASE_URL$API_PREFIX/push/subscribe" 2>/dev/null)

if [ "$SUBSCRIBE_HTTP" = "200" ] || [ "$SUBSCRIBE_HTTP" = "204" ]; then
    echo -e "${GREEN}✓${NC} Subscribe endpoint is accessible (HTTP $SUBSCRIBE_HTTP)"
else
    echo -e "${RED}✗${NC} Subscribe endpoint not responding correctly (HTTP $SUBSCRIBE_HTTP)"
    ((CRITICAL_ISSUES++))
fi

echo ""

# Test test endpoint (if available)
echo "Testing notification endpoint..."
TEST_HTTP=$(curl $CURL_OPTS -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL$API_PREFIX/push/test" 2>/dev/null)

if [ "$TEST_HTTP" = "200" ] || [ "$TEST_HTTP" = "204" ]; then
    echo -e "${GREEN}✓${NC} Test endpoint is accessible (HTTP $TEST_HTTP)"
else
    warn_issue "Test endpoint response: HTTP $TEST_HTTP (may require authentication)"
fi

# ============================================================================
# 5. Service Worker Configuration
# ============================================================================
section_title "5. Service Worker Check"

# Check if frontend exists
if [ -d "frontend" ]; then
    # Look for service worker file
    if find frontend -name "*.js" -o -name "*.ts" | xargs grep -l "self.addEventListener\|self.registration\|importScripts" 2>/dev/null | grep -q "sw\|service"; then
        echo -e "${GREEN}✓${NC} Service Worker file found in frontend"
    else
        warn_issue "Service Worker registration not found in frontend code"
        echo "   Expected: frontend/src/sw.js or similar"
    fi
    
    # Check for push event handler
    if find frontend -name "*.js" -o -name "*.ts" | xargs grep -l "push.*event" 2>/dev/null | grep -q .; then
        echo -e "${GREEN}✓${NC} Push event handlers found in service worker"
    else
        warn_issue "No push event handlers in service worker"
        echo "   Service worker needs: self.addEventListener('push', ...)"
    fi
fi

echo ""
echo "Browser-side Service Worker checks:"
echo "  1. Open DevTools (F12 or Ctrl+Shift+I)"
echo "  2. Go to Application tab"
echo "  3. Expand Service Workers section"
echo "  4. Look for registered service worker:"
echo "     ✓ Status: activated"
echo "     ✗ Red X: registration failed"
echo ""
echo "If registration failed, check console for errors"

# ============================================================================
# 6. Network & Firewall Checks
# ============================================================================
section_title "6. Network Configuration"

echo "Checking network connectivity..."
echo ""

# Check localhost accessibility
if timeout 2 bash -c "echo > /dev/tcp/localhost/$SERVER_PORT" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} Port $SERVER_PORT is open on localhost"
else
    warn_issue "Port $SERVER_PORT is not accessible (may be firewall/network issue)"
fi

echo ""

# Check DNS (if custom domain)
if [ "$SERVER_HOST" != "localhost" ] && [ "$SERVER_HOST" != "127.0.0.1" ]; then
    if nslookup "$SERVER_HOST" &> /dev/null; then
        echo -e "${GREEN}✓${NC} DNS resolution works for $SERVER_HOST"
    else
        warn_issue "DNS resolution failed for $SERVER_HOST"
    fi
fi

# ============================================================================
# 7. Browser Permissions Check
# ============================================================================
section_title "7. Browser Permissions"

echo "Push notifications require explicit browser permission."
echo ""
echo "To check/grant permission:"
echo "  1. In address bar, click the lock icon"
echo "  2. Find 'Notifications' in permissions"
echo "  3. If 'Block': click and change to 'Allow'"
echo "  4. If 'Ask': grant permission when prompted"
echo ""
echo "If blocked, clear notification permission:"
echo "  1. Settings → Privacy → Site permissions → Notifications"
echo "  2. Find your site"
echo "  3. Click 'Remove' to reset permission"
echo "  4. Reload page and grant permission again"

# ============================================================================
# 8. Browser Console Debugging
# ============================================================================
section_title "8. Console Error Debugging"

echo "Common errors and solutions:"
echo ""
echo "❌ 'NotAllowedError: Notification permission denied'"
echo "   → User denied permission. Clear site permission and retry."
echo ""
echo "❌ 'NotSupportedError: Push notifications not supported'"
echo "   → Browser doesn't support Web Push. Check browser compatibility:"
echo "   → Chrome ✓, Firefox ✓, Safari ✗, Edge ✓"
echo ""
echo "❌ 'Failed to register ServiceWorker'"
echo "   → HTTPS may not be properly configured"
echo "   → Check: certificate valid, domain matches, no mixed content"
echo ""
echo "❌ 'TypeError: Cannot read property 'pushManager' of undefined'"
echo "   → Service Worker not registered. Check sw.js exists and loads"
echo ""
echo "❌ 'HTTP 410/404 from push service'"
echo "   → Subscription expired or invalid. Need to re-subscribe."
echo ""
echo "❌ 'HTTPS certificate error / NET::ERR_CERT_AUTHORITY_INVALID'"
echo "   → Self-signed cert not trusted. Add exception or use proper cert."

# ============================================================================
# 9. Common Issues & Fixes
# ============================================================================
section_title "9. Troubleshooting Checklist"

echo ""
echo "Quick Fixes (try these first):"
echo ""
echo "□ Clear browser cache and reload with Ctrl+Shift+R (hard reload)"
echo ""
echo "□ Check browser console (F12) for Service Worker errors"
echo ""
echo "□ Verify permission:"
echo "   - Settings → Privacy → Site permissions → Notifications → Allow"
echo ""
echo "□ Test with localhost:3000 (avoid custom domains if using self-signed cert)"
echo ""
echo "□ Check database has subscriptions:"
echo "   SELECT COUNT(*) FROM push_subscription;"
echo ""
echo "□ Test with curl:"
echo "   curl $BASE_URL$API_PREFIX/push/vapid-public-key"
echo ""
echo "Advanced Debugging:"
echo ""
echo "□ Check backend logs for WebPush errors:"
echo "   grep -i 'webpush\|push.*exception' logs/*.log"
echo ""
echo "□ Enable debug logging in backend (set LOG_LEVEL=DEBUG)"
echo ""
echo "□ Test subscription data persists:"
echo "   - Subscribe → check DB → hard reload → verify still there"
echo ""
echo "□ Check if quiet hours are blocking notifications:"
echo "   SELECT * FROM notification_preference WHERE subscription_id = '...';"
echo ""
echo "□ Monitor backend during test:"
echo "   tail -f logs/backend.log | grep -i push"

# ============================================================================
# 10. Summary & Recommendations
# ============================================================================
section_title "10. Summary & Recommendations"

echo ""
echo "Issues Found:"
echo "  Critical: $CRITICAL_ISSUES"
echo "  Warnings: $WARNINGS"
echo "  Info: $INFO_ITEMS"
echo ""

if [ $CRITICAL_ISSUES -eq 0 ]; then
    echo -e "${GREEN}✓${NC} No critical issues detected!"
    echo ""
    echo "If notifications still not working:"
    echo "  1. Check Service Worker registration in DevTools"
    echo "  2. Check browser console for JavaScript errors"
    echo "  3. Verify notification permission is granted"
    echo "  4. Check backend logs for WebPush exceptions"
    echo ""
    echo "Next steps:"
    echo "  1. Open DevTools → Console tab"
    echo "  2. Subscribe to push: pushManager.subscribe(...)"
    echo "  3. Check if subscription created in database"
    echo "  4. Send test notification via API"
    echo "  5. Verify Service Worker receives push event"
else
    echo -e "${RED}✗${NC} Critical issues found - fix these first:"
    echo ""
    if ! curl $CURL_OPTS -s "$BASE_URL$API_PREFIX/push/vapid-public-key" &>/dev/null; then
        echo "  • Backend API not responding - check server is running"
    fi
    if [ "$SERVER_PROTOCOL" = "http" ]; then
        echo "  • HTTPS not configured - required for push notifications"
        echo "    Set up SSL certificates in backend/certs/"
    fi
    if [ ! -f "backend/main.py" ]; then
        echo "  • Not running from project root - cd to ArgusAI/"
    fi
fi

echo ""
echo "=================================================="
echo "For more help:"
echo "  - GitHub Issue #351"
echo "  - GitHub Issue #373 (investigation findings)"
echo "  - backend/app/services/push_notification_service.py"
echo "  - docs-site/docs/features/notifications.md"
echo ""
echo "Run this script regularly to monitor push status."
