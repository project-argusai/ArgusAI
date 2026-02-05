#!/usr/bin/env python3
"""
ArgusAI Push Notification Testing & Debugging Tool

Helps debug push notification issues (#351) by:
- Testing API endpoints
- Verifying database state
- Checking service worker setup
- Testing notification payload delivery
- Generating test notifications
"""

import sys
import os
import asyncio
import json
import argparse
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

try:
    from sqlalchemy.orm import Session
    from app.core.database import SessionLocal
    from app.models.push_subscription import PushSubscription
    from app.models.notification_preference import NotificationPreference
    from app.services.push_notification_service import (
        PushNotificationService,
        format_rich_notification,
        send_event_notification
    )
    from app.utils.vapid import ensure_vapid_keys
except ImportError as e:
    print(f"❌ Failed to import ArgusAI modules: {e}")
    print("Make sure you're running from the ArgusAI backend directory")
    sys.exit(1)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Color codes for CLI output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

def print_success(msg: str):
    print(f"{Colors.GREEN}✓{Colors.END} {msg}")

def print_error(msg: str):
    print(f"{Colors.RED}✗{Colors.END} {msg}")

def print_warning(msg: str):
    print(f"{Colors.YELLOW}⚠{Colors.END} {msg}")

def print_info(msg: str):
    print(f"{Colors.BLUE}ℹ{Colors.END} {msg}")

# ============================================================================
# Diagnostic Functions
# ============================================================================

def check_database() -> bool:
    """Check database connectivity and schema."""
    try:
        db = SessionLocal()
        
        # Try to query push_subscription table
        count = db.query(PushSubscription).count()
        print_success(f"Database connected: {count} push subscriptions found")
        
        # Check notification preferences
        pref_count = db.query(NotificationPreference).count()
        print_success(f"Notification preferences: {pref_count} found")
        
        db.close()
        return True
    except Exception as e:
        print_error(f"Database connection failed: {e}")
        return False

def check_vapid_keys(db: Session) -> bool:
    """Check if VAPID keys are configured."""
    try:
        private_key, public_key = ensure_vapid_keys(db)
        
        if private_key and public_key:
            print_success("VAPID keys found and valid")
            print_info(f"Public key (first 50 chars): {public_key[:50]}...")
            return True
        else:
            print_error("VAPID keys not found or invalid")
            return False
    except Exception as e:
        print_error(f"VAPID key check failed: {e}")
        return False

def list_subscriptions(db: Session, limit: int = 10) -> List[Dict[str, Any]]:
    """List recent push subscriptions."""
    subscriptions = db.query(PushSubscription).order_by(
        PushSubscription.created_at.desc()
    ).limit(limit).all()
    
    if not subscriptions:
        print_warning("No push subscriptions found in database")
        return []
    
    print_success(f"Found {len(subscriptions)} recent subscriptions:")
    print("")
    
    result = []
    for sub in subscriptions:
        # Truncate endpoint for display
        endpoint_display = sub.endpoint[:60] + "..." if sub.endpoint else "N/A"
        
        info = {
            "id": sub.id,
            "endpoint": sub.endpoint,
            "created_at": sub.created_at.isoformat() if sub.created_at else None,
            "last_used_at": sub.last_used_at.isoformat() if sub.last_used_at else None,
        }
        result.append(info)
        
        print(f"  ID: {sub.id}")
        print(f"  Endpoint: {endpoint_display}")
        print(f"  Created: {sub.created_at}")
        print(f"  Last Used: {sub.last_used_at or 'Never'}")
        print("")
    
    return result

def check_preferences(db: Session) -> List[Dict[str, Any]]:
    """Check notification preferences for all subscriptions."""
    prefs = db.query(NotificationPreference).all()
    
    if not prefs:
        print_warning("No notification preferences configured")
        return []
    
    print_success(f"Found {len(prefs)} notification preference records:")
    print("")
    
    result = []
    for pref in prefs:
        # Get subscription details
        sub = db.query(PushSubscription).filter(
            PushSubscription.id == pref.subscription_id
        ).first()
        
        info = {
            "subscription_id": pref.subscription_id,
            "quiet_hours_enabled": pref.quiet_hours_enabled,
            "sound_enabled": pref.sound_enabled,
            "quiet_hours": f"{pref.quiet_hours_start} - {pref.quiet_hours_end}" if pref.quiet_hours_start else None,
        }
        result.append(info)
        
        print(f"  Subscription: {pref.subscription_id}")
        print(f"  Sound: {'✓' if pref.sound_enabled else '✗'}")
        print(f"  Quiet Hours: {'✓' if pref.quiet_hours_enabled else '✗'}")
        if pref.quiet_hours_enabled and pref.quiet_hours_start:
            print(f"    Time: {pref.quiet_hours_start} - {pref.quiet_hours_end}")
            print(f"    Timezone: {pref.timezone}")
        print("")
    
    return result

async def test_notification_send(
    db: Session,
    subscription_id: Optional[str] = None,
    dry_run: bool = False
) -> bool:
    """Test sending a notification to a subscription."""
    
    # Get or use first subscription
    if subscription_id:
        subscription = db.query(PushSubscription).filter(
            PushSubscription.id == subscription_id
        ).first()
        if not subscription:
            print_error(f"Subscription not found: {subscription_id}")
            return False
    else:
        subscription = db.query(PushSubscription).first()
        if not subscription:
            print_error("No subscriptions available for testing")
            return False
    
    if dry_run:
        print_info(f"DRY RUN: Would send to subscription {subscription.id}")
        return True
    
    print_info(f"Sending test notification to {subscription.id}")
    
    service = PushNotificationService(db)
    
    result = await service.send_notification(
        subscription_id=subscription.id,
        title="🧪 ArgusAI Test Notification",
        body="This is a test push notification from ArgusAI",
        data={
            "test": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        tag="test-notification"
    )
    
    if result.success:
        print_success(f"Notification sent successfully (retries: {result.retries})")
        return True
    else:
        print_error(f"Failed to send notification: {result.error}")
        print_info(f"Status code: {result.status_code}")
        return False

async def test_event_notification(
    db: Session,
    camera_name: str = "Front Door",
    smart_detection_type: str = "person",
    dry_run: bool = False
) -> bool:
    """Test sending a rich event notification."""
    
    if dry_run:
        print_info("DRY RUN: Would send event notification")
        return True
    
    print_info("Sending test event notification to all subscriptions")
    
    results = await send_event_notification(
        event_id="test-event-" + datetime.now(timezone.utc).isoformat(),
        camera_name=camera_name,
        description="Test motion detection event for debugging push notifications",
        camera_id="test-camera",
        smart_detection_type=smart_detection_type,
        thumbnail_url="https://via.placeholder.com/150",
        db=db
    )
    
    success_count = sum(1 for r in results if r.success)
    print_success(f"Sent to {success_count}/{len(results)} subscriptions")
    
    for result in results[:5]:  # Show first 5
        status = "✓" if result.success else "✗"
        print(f"  {status} {result.subscription_id}: {result.error or 'OK'}")
    
    return success_count > 0

async def test_broadcast(db: Session, dry_run: bool = False) -> bool:
    """Test broadcasting to all subscriptions."""
    
    service = PushNotificationService(db)
    
    if dry_run:
        count = db.query(PushSubscription).count()
        print_info(f"DRY RUN: Would broadcast to {count} subscriptions")
        return True
    
    print_info("Testing broadcast notification...")
    
    results = await service.broadcast_notification(
        title="🧪 Test Broadcast",
        body="This is a broadcast test notification",
        tag="broadcast-test",
        silent=False
    )
    
    success_count = sum(1 for r in results if r.success)
    print_success(f"Broadcast sent to {success_count}/{len(results)} subscriptions")
    
    return success_count > 0

# ============================================================================
# CLI Interface
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="ArgusAI Push Notification Testing Tool"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Database check
    subparsers.add_parser(
        "database",
        help="Check database connectivity and schema"
    )
    
    # List subscriptions
    subparsers.add_parser(
        "subscriptions",
        help="List push subscriptions from database"
    )
    
    # Check VAPID keys
    subparsers.add_parser(
        "vapid",
        help="Check VAPID key configuration"
    )
    
    # Check preferences
    subparsers.add_parser(
        "preferences",
        help="Check notification preferences"
    )
    
    # Send test notification
    test_parser = subparsers.add_parser(
        "test-send",
        help="Send a test notification"
    )
    test_parser.add_argument(
        "--subscription",
        help="Specific subscription ID to test (uses first if not specified)"
    )
    test_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually send, just show what would happen"
    )
    
    # Send event notification
    event_parser = subparsers.add_parser(
        "test-event",
        help="Send a test event notification"
    )
    event_parser.add_argument(
        "--camera",
        default="Front Door",
        help="Camera name for notification"
    )
    event_parser.add_argument(
        "--type",
        default="person",
        help="Detection type (person, vehicle, etc.)"
    )
    event_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually send"
    )
    
    # Broadcast test
    broadcast_parser = subparsers.add_parser(
        "test-broadcast",
        help="Test broadcasting to all subscriptions"
    )
    broadcast_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually send"
    )
    
    # Full diagnostic
    subparsers.add_parser(
        "diagnose",
        help="Run full push notification diagnostic"
    )
    
    args = parser.parse_args()
    
    # Handle commands
    try:
        db = SessionLocal()
        
        if args.command == "database":
            check_database()
        
        elif args.command == "subscriptions":
            list_subscriptions(db)
        
        elif args.command == "vapid":
            check_vapid_keys(db)
        
        elif args.command == "preferences":
            check_preferences(db)
        
        elif args.command == "test-send":
            asyncio.run(test_notification_send(
                db,
                subscription_id=args.subscription,
                dry_run=args.dry_run
            ))
        
        elif args.command == "test-event":
            asyncio.run(test_event_notification(
                db,
                camera_name=args.camera,
                smart_detection_type=args.type,
                dry_run=args.dry_run
            ))
        
        elif args.command == "test-broadcast":
            asyncio.run(test_broadcast(db, dry_run=args.dry_run))
        
        elif args.command == "diagnose":
            print("\n" + "="*60)
            print("🔍 ArgusAI Push Notification Full Diagnostic")
            print("="*60 + "\n")
            
            print("📋 Checking Database...\n")
            if check_database():
                print()
                print("📋 Checking VAPID Keys...\n")
                check_vapid_keys(db)
                
                print("\n📋 Listing Subscriptions...\n")
                subs = list_subscriptions(db, limit=5)
                
                print("📋 Checking Preferences...\n")
                check_preferences(db)
                
                print("\n" + "="*60)
                if subs:
                    print(f"✓ Diagnostic complete - Found {len(subs)} subscriptions")
                else:
                    print("⚠ Diagnostic complete - No subscriptions found")
                    print("  Subscriptions appear when clients call pushManager.subscribe()")
                print("="*60 + "\n")
        
        else:
            parser.print_help()
        
        db.close()
    
    except Exception as e:
        print_error(f"Error: {e}")
        logger.exception("Diagnostic error")
        sys.exit(1)

if __name__ == "__main__":
    main()
