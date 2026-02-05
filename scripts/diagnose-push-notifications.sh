#!/bin/bash
#
# ArgusAI Push Notifications Diagnostic Script
# 
# Purpose: Troubleshoot push notification issues (#351)
# This script checks configuration, database state, and API connectivity
#

set -e

echo "🔍 ArgusAI Push Notifications Diagnostic Report"
echo "=============================================="
echo ""
echo "Generated: $(date -u +'%Y-%m-%d %H:%M:%S UTC')"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counter for issues found
ISSUES_FOUND=0

# Helper functions
check_success() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $1"
    else
        echo -e "${RED}✗${NC} $1"
        ((ISSUES_FOUND++))
    fi
}

check_file_exists() {
    if [ -f "$1" ]; then
        echo -e "${GREEN}✓${NC} Found: $1"
    else
        echo -e "${RED}✗${NC} Missing: $1"
        ((ISSUES_FOUND++))
    fi
}

section_title() {
    echo ""
    echo "📋 $1"
    echo "---"
}

# ============================================================================
# 1. Check Environment & Configuration
# ============================================================================
section_title "Environment & Configuration"

# Check if running from project root
if [ -f "backend/main.py" ]; then
    echo -e "${GREEN}✓${NC} Running from project root"
else
    echo -e "${RED}✗${NC} Not running from project root"
    ((ISSUES_FOUND++))
fi

# Check .env file
check_file_exists ".env"

# Check VAPID keys setup
if grep -q "VAPID" .env 2>/dev/null; then
    echo -e "${GREEN}✓${NC} VAPID configuration found in .env"
else
    echo -e "${YELLOW}⚠${NC} VAPID configuration not in .env (may be in database)"
fi

# ============================================================================
# 2. Database State
# ============================================================================
section_title "Database State"

# Note: This requires DATABASE_URL to be set or accessible
DB_QUERY_AVAILABLE=false
if [ ! -z "$DATABASE_URL" ]; then
    DB_QUERY_AVAILABLE=true
elif grep -q "DATABASE_URL" .env 2>/dev/null; then
    DB_QUERY_AVAILABLE=true
fi

if [ "$DB_QUERY_AVAILABLE" = true ]; then
    echo -e "${YELLOW}⚠${NC} Database queries require direct access (run on server)"
    echo ""
    echo "   Run these queries to check database state:"
    echo ""
    echo "   # Count subscriptions:"
    echo "   SELECT COUNT(*) as subscription_count FROM push_subscription;"
    echo ""
    echo "   # Check if subscriptions exist with dates:"
    echo "   SELECT id, endpoint, created_at, last_used_at FROM push_subscription LIMIT 5;"
    echo ""
    echo "   # Check notification preferences:"
    echo "   SELECT COUNT(*) as preference_count FROM notification_preference;"
    echo ""
    echo "   # Check for any NULL endpoints (corrupted data):"
    echo "   SELECT COUNT(*) FROM push_subscription WHERE endpoint IS NULL;"
    echo ""
else
    echo -e "${RED}✗${NC} DATABASE_URL not configured"
    ((ISSUES_FOUND++))
fi

# ============================================================================
# 3. API Endpoint Check
# ============================================================================
section_title "API Endpoints"

echo "Testing push notification endpoints:"
echo ""

# Check if server is running
SERVER_URL="${SERVER_URL:-http://localhost:3000}"
API_PREFIX="${API_PREFIX:-/api/v1}"

echo "Base URL: $SERVER_URL"
echo ""

# Test VAPID public key endpoint
echo "Testing VAPID endpoint:"
if curl -s "$SERVER_URL$API_PREFIX/push/vapid-public-key" | grep -q "public_key"; then
    echo -e "${GREEN}✓${NC} GET /push/vapid-public-key returns valid response"
else
    echo -e "${RED}✗${NC} GET /push/vapid-public-key failed or returned invalid response"
    ((ISSUES_FOUND++))
fi

echo ""
echo "Testing test notification endpoint:"
# This requires POST
if curl -s -X POST "$SERVER_URL$API_PREFIX/push/test" | grep -q "success"; then
    echo -e "${GREEN}✓${NC} POST /push/test endpoint is accessible"
else
    echo -e "${YELLOW}⚠${NC} POST /push/test may not be working (check response above)"
fi

# ============================================================================
# 4. Browser Requirements
# ============================================================================
section_title "Browser Requirements (Client-Side)"

echo "Push notifications require:"
echo "  ✓ HTTPS connection (self-signed certs may have issues)"
echo "  ✓ Service Worker support"
echo "  ✓ Browser permission granted"
echo "  ✓ Valid Push service endpoint (FCM, Web Push service)"
echo ""
echo "Check browser console for errors:"
echo "  - Open DevTools (F12)"
echo "  - Go to Console tab"
echo "  - Look for Service Worker registration errors"
echo "  - Check for 'Failed to register push' messages"
echo ""

# ============================================================================
# 5. HTTPS/SSL Check
# ============================================================================
section_title "HTTPS/SSL Configuration"

# Check if the server is using HTTPS
if curl -s --insecure https://localhost:3000/api/v1/push/vapid-public-key >/dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} HTTPS is available"
else
    echo -e "${YELLOW}⚠${NC} HTTPS may not be properly configured"
    
    # Check for SSL certificate files
    if [ -f "backend/certs/cert.pem" ] || [ -f "backend/certs/key.pem" ]; then
        echo "   SSL cert files found but may not be valid"
    else
        echo "   No SSL certificates found"
    fi
fi

echo ""
echo "Self-signed certificate note:"
echo "  ⚠  Service Workers require trusted SSL certificates"
echo "  ⚠  Self-signed certs work on localhost but not on custom domains"
echo ""
echo "   Options to fix:"
echo "   1. Use localhost:3000 instead of custom domain"
echo "   2. Add self-signed cert to system trust store"
echo "   3. Use Let's Encrypt (free) instead of self-signed"

# ============================================================================
# 6. Service Worker Check
# ============================================================================
section_title "Service Worker (Browser-Side)"

echo "Check browser DevTools for Service Worker registration:"
echo ""
echo "  1. Open DevTools (F12)"
echo "  2. Go to Application → Service Workers"
echo "  3. Look for '/sw.js' registration"
echo "  4. Check status:"
echo "     ✓ If registered: Service Worker is working"
echo "     ✗ If failed: Check console for error message"
echo ""

# ============================================================================
# 7. Sample Test Requests
# ============================================================================
section_title "Manual Test Requests"

echo "To manually test push notifications:"
echo ""
echo "1. Create test subscription (requires push service endpoint):"
cat << 'EOF'
curl -X POST http://localhost:3000/api/v1/push/subscribe \
  -H "Content-Type: application/json" \
  -d '{
    "endpoint": "https://fcm.googleapis.com/fcm/send/test-endpoint-xxx",
    "keys": {
      "p256dh": "test-p256dh-key",
      "auth": "test-auth-key"
    }
  }'
EOF

echo ""
echo "2. Send test notification:"
echo ""
echo "curl -X POST http://localhost:3000/api/v1/push/test"
echo ""
echo "3. Get preferences:"
echo ""
echo "curl -X POST http://localhost:3000/api/v1/push/preferences \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{\"endpoint\": \"your-endpoint-url\"}'"
echo ""

# ============================================================================
# 8. Common Issues Checklist
# ============================================================================
section_title "Common Issues Checklist"

echo "Try these troubleshooting steps:"
echo ""
echo "□ Clear browser cache and cookies"
echo "□ Reload the page with Ctrl+Shift+R (hard reload)"
echo "□ Check browser console for permission denied errors"
echo "□ Try accessing via http://localhost:3000 instead of custom domain"
echo "□ Verify database has push_subscription records:"
echo "   SELECT COUNT(*) FROM push_subscription;"
echo "□ Check if quiet hours are enabled (might filter notifications)"
echo "□ Review backend logs for WebPush exceptions:"
echo "   grep -i 'push\\|notification' /var/log/argusai/*.log"
echo "□ Verify VAPID keys are set in database:"
echo "   SELECT * FROM system_setting WHERE key LIKE '%vapid%';"
echo ""

# ============================================================================
# 9. Summary
# ============================================================================
section_title "Summary"

if [ $ISSUES_FOUND -eq 0 ]; then
    echo -e "${GREEN}✓${NC} No critical issues detected"
    echo ""
    echo "If push notifications are still not working, it's likely:"
    echo "  1. Service Worker registration failing (check browser console)"
    echo "  2. Self-signed SSL certificate issue"
    echo "  3. Subscription not persisting in database"
    echo "  4. Preferences filtering out notifications"
else
    echo -e "${RED}✗${NC} Found $ISSUES_FOUND issue(s)"
fi

echo ""
echo "=============================================="
echo "For more help, check:"
echo "  - Issue #351 on GitHub"
echo "  - Issue #373 (investigation findings)"
echo "  - backend/app/services/push_notification_service.py"
echo "  - frontend/hooks/usePushNotifications.ts"
