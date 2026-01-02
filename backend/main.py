"""
FastAPI application entry point for ArgusAI

Initializes the FastAPI app, registers routers, and sets up startup/shutdown events.
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.database import engine, Base
from app.core.logging_config import setup_logging, get_logger
from app.core.metrics import init_metrics, get_metrics, get_content_type, update_system_metrics
from app.middleware.logging_middleware import RequestLoggingMiddleware
from app.middleware.auth_middleware import AuthMiddleware
from app.middleware.last_seen import LastSeenMiddleware
from app.middleware.https_redirect import HTTPSRedirectMiddleware
from app.middleware.rate_limit import RateLimitMiddleware, limiter as global_limiter  # Story P14-2.6
from app.api.v1.cameras import router as cameras_router, camera_service
from app.api.v1.motion_events import router as motion_events_router
from app.api.v1.ai import router as ai_router
from app.api.v1.events import router as events_router
from app.api.v1.metrics import router as metrics_router
from app.api.v1.system import router as system_router, get_retention_policy_from_db
from app.services.backup_service import get_backup_service
from app.api.v1.alert_rules import router as alert_rules_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.websocket import router as websocket_router
from app.api.v1.logs import router as logs_router
from app.api.v1.auth import router as auth_router, ensure_admin_exists, limiter
from app.api.v1.protect import router as protect_router  # Story P2-1.1: UniFi Protect
from app.api.v1.system_notifications import router as system_notifications_router  # Story P3-7.4: Cost Alerts
from app.api.v1.push import router as push_router  # Story P4-1.1: Web Push
from app.api.v1.integrations import router as integrations_router  # Story P4-2.1: MQTT
from app.api.v1.context import router as context_router  # Story P4-3.1: Embeddings
from app.api.v1.summaries import router as summaries_router  # Story P4-4.1: Activity Summaries
from app.api.v1.digests import router as digests_router  # Story P4-4.2: Daily Digest Scheduler
from app.api.v1.feedback import router as feedback_router  # Story P4-5.2: Feedback Statistics
from app.api.v1.voice import router as voice_router  # Story P4-6.3: Voice Query API
from app.api.v1.homekit import router as homekit_router  # Story P5-1.1: HomeKit API
from app.api.v1.discovery import router as discovery_router  # Story P5-2.1: ONVIF Discovery
from app.api.v1.audio import router as audio_router  # Story P6-3.2: Audio Event Detection
from app.api.v1.devices import router as devices_router  # Story P11-2.4: Device Registration
from app.api.v1.mobile_auth import router as mobile_auth_router  # Story P12-3: Mobile Auth
from app.api.v1.api_keys import router as api_keys_router  # Story P13-1: API Key Management
from app.api.v1.users import router as users_router  # Story P15-2.3: User Management
from app.services.event_processor import initialize_event_processor, shutdown_event_processor
from app.services.cleanup_service import get_cleanup_service
from app.services.protect_service import get_protect_service  # Story P2-1.4: Protect WebSocket
from app.services.mqtt_service import initialize_mqtt_service, shutdown_mqtt_service  # Story P4-2.1: MQTT
from app.services.mqtt_discovery_service import initialize_discovery_service, get_discovery_service  # Story P4-2.2: HA Discovery
from app.services.mqtt_status_service import initialize_status_sensors  # Story P4-2.5: Camera Status Sensors
from app.services.pattern_service import get_pattern_service  # Story P4-3.5: Pattern Detection
from app.services.digest_scheduler import initialize_digest_scheduler, shutdown_digest_scheduler  # Story P4-4.2: Digest Scheduler
from app.services.homekit_service import get_homekit_service, initialize_homekit_service, shutdown_homekit_service  # Story P4-6.1: HomeKit

# Application version
APP_VERSION = "1.0.0"

# Initialize structured JSON logging (Story 6.2)
setup_logging(app_version=APP_VERSION)
logger = get_logger(__name__)

# Initialize Prometheus metrics
init_metrics(version=APP_VERSION)

# Global scheduler instance
scheduler: AsyncIOScheduler = None


async def scheduled_cleanup_job():
    """
    Scheduled cleanup job that runs daily at 2:00 AM

    Deletes old events based on retention policy from system_settings table.
    Only runs if retention policy is not set to "forever" (retention_days > 0).
    """
    try:
        # Get retention policy from database
        retention_days = get_retention_policy_from_db()

        # Skip cleanup if retention is set to forever
        if retention_days <= 0:
            logger.info("Scheduled cleanup skipped (retention policy set to forever)")
            return

        logger.info(f"Starting scheduled cleanup (retention: {retention_days} days)")

        # Execute cleanup
        cleanup_service = get_cleanup_service()
        stats = await cleanup_service.cleanup_old_events(retention_days=retention_days)

        logger.info(
            f"Scheduled cleanup complete: {stats['events_deleted']} events deleted, "
            f"{stats['space_freed_mb']} MB freed",
            extra=stats
        )

    except Exception as e:
        logger.error(f"Scheduled cleanup failed: {e}", exc_info=True)


async def scheduled_backup_job():
    """
    Scheduled backup job that runs daily at 3:00 AM (configurable)

    Creates automatic backups and maintains retention policy (keeps last N backups).
    Only runs if automatic backups are enabled in system_settings.
    """
    try:
        # Check if automatic backups are enabled
        from app.core.database import get_db_session
        from app.models.system_setting import SystemSetting

        with get_db_session() as db:
            auto_backup_setting = db.query(SystemSetting).filter(
                SystemSetting.key == "settings_auto_backup_enabled"
            ).first()

            # Skip if auto-backup is not enabled (default: disabled)
            if not auto_backup_setting or auto_backup_setting.value.lower() not in ('true', '1', 'yes'):
                logger.debug("Scheduled backup skipped (auto-backup not enabled)")
                return

            # Get retention count setting
            retention_setting = db.query(SystemSetting).filter(
                SystemSetting.key == "settings_backup_retention_count"
            ).first()
            keep_count = int(retention_setting.value) if retention_setting else 7

        logger.info("Starting scheduled automatic backup")

        # Create backup
        backup_service = get_backup_service()
        result = await backup_service.create_backup()

        if result.success:
            logger.info(
                f"Scheduled backup complete: {result.timestamp}",
                extra={
                    "event_type": "scheduled_backup_complete",
                    "timestamp": result.timestamp,
                    "size_bytes": result.size_bytes
                }
            )

            # Cleanup old backups based on retention
            deleted = backup_service.cleanup_old_backups(keep_count=keep_count)
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old backups (keeping {keep_count})")
        else:
            logger.error(f"Scheduled backup failed: {result.message}")

    except Exception as e:
        logger.error(f"Scheduled backup failed: {e}", exc_info=True)


async def scheduled_pattern_calculation_job():
    """
    Scheduled pattern calculation job that runs hourly (Story P4-3.5)

    Recalculates activity patterns for all enabled cameras based on their
    historical event data. Patterns are used to provide timing context in AI descriptions.
    """
    try:
        logger.info("Starting scheduled pattern calculation")

        from app.core.database import get_db_session

        with get_db_session() as db:
            # Get pattern service and recalculate all patterns
            pattern_service = get_pattern_service()
            result = await pattern_service.recalculate_all_patterns(db)

            logger.info(
                f"Scheduled pattern calculation complete: {result['patterns_calculated']} patterns updated, "
                f"{result['patterns_skipped']} skipped",
                extra={
                    "event_type": "scheduled_pattern_calculation_complete",
                    **result
                }
            )

    except Exception as e:
        logger.error(f"Scheduled pattern calculation failed: {e}", exc_info=True)


async def scheduled_session_cleanup_job():
    """
    Scheduled session cleanup job that runs hourly (Story P15-2.8)

    Removes expired sessions from the database to keep session table clean
    and ensure expired sessions don't accumulate.
    """
    try:
        logger.info("Starting scheduled session cleanup")

        from app.core.database import get_db_session
        from app.services.session_service import SessionService

        with get_db_session() as db:
            session_service = SessionService(db)
            count = session_service.cleanup_expired_sessions()

            logger.info(
                f"Scheduled session cleanup complete: {count} expired sessions removed",
                extra={
                    "event_type": "scheduled_session_cleanup_complete",
                    "expired_count": count
                }
            )

    except Exception as e:
        logger.error(f"Scheduled session cleanup failed: {e}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler for startup and shutdown events.

    Manages the application lifecycle:
    - Startup: Creates database tables and initializes resources
    - Shutdown: Stops camera threads and cleans up resources
    """
    global scheduler

    # Startup logic with structured logging (Story 6.2)
    logger.info(
        "Application starting",
        extra={
            "event_type": "app_startup",
            "version": APP_VERSION,
            "log_level": settings.LOG_LEVEL,
            "debug_mode": settings.DEBUG,
        }
    )

    # Create database tables
    Base.metadata.create_all(bind=engine)
    logger.info(
        "Database initialized",
        extra={"event_type": "database_init", "status": "success"}
    )

    # Ensure admin user exists (Story 6.3)
    from app.core.database import get_db
    setup_db = next(get_db())
    try:
        created, password = ensure_admin_exists(setup_db)
        if created:
            logger.info(
                "Default admin user created - SAVE THIS PASSWORD",
                extra={
                    "event_type": "admin_setup",
                    "username": "admin",
                    "password": password,  # Only logged on first creation
                }
            )
            print(f"\n{'='*60}")
            print("INITIAL SETUP - SAVE THIS INFORMATION")
            print(f"{'='*60}")
            print(f"Username: admin")
            print(f"Password: {password}")
            print(f"{'='*60}\n")
    finally:
        setup_db.close()

    # Create thumbnails directory
    thumbnail_dir = os.path.join(os.path.dirname(__file__), 'data', 'thumbnails')
    os.makedirs(thumbnail_dir, exist_ok=True)
    logger.info(
        "Thumbnails directory ready",
        extra={"event_type": "directory_init", "path": thumbnail_dir}
    )

    # Initialize Event Processor (Story 3.3)
    await initialize_event_processor()
    logger.info(
        "Event processor started",
        extra={"event_type": "event_processor_init", "status": "running"}
    )

    # Initialize APScheduler for daily cleanup (Story 3.4)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        scheduled_cleanup_job,
        trigger=CronTrigger(hour=2, minute=0),  # Daily at 2:00 AM
        id="daily_cleanup",
        name="Daily event cleanup based on retention policy",
        replace_existing=True
    )

    # Add system metrics update job (every minute)
    scheduler.add_job(
        update_system_metrics,
        trigger=CronTrigger(minute="*"),  # Every minute
        id="system_metrics_update",
        name="Update system resource metrics",
        replace_existing=True
    )

    # Add automatic backup job (Story 6.4) - Daily at 3:00 AM
    scheduler.add_job(
        scheduled_backup_job,
        trigger=CronTrigger(hour=3, minute=0),  # Daily at 3:00 AM
        id="daily_backup",
        name="Daily automatic backup (if enabled)",
        replace_existing=True
    )

    # Add pattern calculation job (Story P4-3.5) - Hourly
    scheduler.add_job(
        scheduled_pattern_calculation_job,
        trigger=CronTrigger(minute=0),  # Every hour at :00
        id="hourly_pattern_calculation",
        name="Hourly activity pattern calculation",
        replace_existing=True
    )

    # Add session cleanup job (Story P15-2.8) - Hourly
    scheduler.add_job(
        scheduled_session_cleanup_job,
        trigger=CronTrigger(minute=30),  # Every hour at :30
        id="hourly_session_cleanup",
        name="Hourly session cleanup",
        replace_existing=True
    )

    scheduler.start()
    logger.info(
        "Scheduler started",
        extra={
            "event_type": "scheduler_init",
            "jobs": ["daily_cleanup", "system_metrics_update", "daily_backup", "hourly_pattern_calculation", "hourly_session_cleanup"]
        }
    )

    # Start enabled cameras on startup (Story 4.3)
    from app.core.database import get_db
    from app.models.camera import Camera
    from app.core.metrics import record_camera_status
    import asyncio

    # Set the main event loop for camera service (needed for thread-safe async calls)
    camera_service.set_event_loop(asyncio.get_running_loop())

    db = next(get_db())
    try:
        enabled_cameras = db.query(Camera).filter(Camera.is_enabled == True).all()
        total_cameras = db.query(Camera).count()
        started_count = 0

        logger.info(
            "Starting cameras",
            extra={
                "event_type": "camera_startup",
                "enabled_count": len(enabled_cameras),
                "total_count": total_cameras
            }
        )

        # Small delay to ensure network stack is ready (helps with immediate RTSP connections)
        import time
        time.sleep(1)

        for camera in enabled_cameras:
            success = camera_service.start_camera(camera)
            if success:
                started_count += 1
                logger.info(
                    "Camera started",
                    extra={
                        "event_type": "camera_connected",
                        "camera_id": str(camera.id),
                        "camera_name": camera.name
                    }
                )
            else:
                logger.warning(
                    "Camera failed to start",
                    extra={
                        "event_type": "camera_connection_failed",
                        "camera_id": str(camera.id),
                        "camera_name": camera.name
                    }
                )

        # Update camera metrics
        record_camera_status(started_count, total_cameras)

    finally:
        db.close()

    # Connect to Protect controllers on startup (Story P2-1.4, AC1)
    from app.models.protect_controller import ProtectController
    protect_service = get_protect_service()

    db = next(get_db())
    try:
        # Initialize app.state.protect_connections (AC9)
        # Note: app is not in scope here yet, so we store in service

        protect_controllers = db.query(ProtectController).all()
        protect_started_count = 0

        if protect_controllers:
            logger.info(
                "Starting Protect controllers",
                extra={
                    "event_type": "protect_startup",
                    "controller_count": len(protect_controllers)
                }
            )

            for controller in protect_controllers:
                try:
                    success = await protect_service.connect(controller)
                    if success:
                        protect_started_count += 1
                        logger.info(
                            "Protect controller connected",
                            extra={
                                "event_type": "protect_controller_connected",
                                "controller_id": str(controller.id),
                                "controller_name": controller.name
                            }
                        )
                    else:
                        logger.warning(
                            "Protect controller failed to connect",
                            extra={
                                "event_type": "protect_controller_connection_failed",
                                "controller_id": str(controller.id),
                                "controller_name": controller.name
                            }
                        )
                except Exception as e:
                    # AC8: One failing controller doesn't affect others
                    logger.error(
                        f"Exception connecting Protect controller: {e}",
                        extra={
                            "event_type": "protect_controller_connection_error",
                            "controller_id": str(controller.id),
                            "error": str(e)
                        }
                    )

            logger.info(
                "Protect controllers startup complete",
                extra={
                    "event_type": "protect_startup_complete",
                    "started_count": protect_started_count,
                    "total_count": len(protect_controllers)
                }
            )
    finally:
        db.close()

    # Initialize MQTT service (Story P4-2.1, AC1, AC2)
    try:
        await initialize_mqtt_service()
        logger.info(
            "MQTT service initialized",
            extra={"event_type": "mqtt_init_complete"}
        )

        # Initialize MQTT discovery service (Story P4-2.2)
        # Must be after MQTT service to register on_connect callback
        await initialize_discovery_service()
        logger.info(
            "MQTT discovery service initialized",
            extra={"event_type": "mqtt_discovery_init_complete"}
        )

        # Initialize MQTT status sensors (Story P4-2.5)
        # Publishes initial camera statuses and sets up scheduler for count updates
        await initialize_status_sensors()
        logger.info(
            "MQTT status sensors initialized",
            extra={"event_type": "mqtt_status_sensors_init_complete"}
        )
    except Exception as e:
        # MQTT failure should not prevent app startup
        logger.warning(
            f"MQTT initialization failed (non-fatal): {e}",
            extra={"event_type": "mqtt_init_failed", "error": str(e)}
        )

    # Initialize Digest Scheduler (Story P4-4.2)
    try:
        await initialize_digest_scheduler()
        logger.info(
            "Digest scheduler initialized",
            extra={"event_type": "digest_scheduler_init_complete"}
        )
    except Exception as e:
        # Digest scheduler failure should not prevent app startup
        logger.warning(
            f"Digest scheduler initialization failed (non-fatal): {e}",
            extra={"event_type": "digest_scheduler_init_failed", "error": str(e)}
        )

    # Initialize HomeKit service (Story P4-6.1)
    # Only starts if HOMEKIT_ENABLED=true or homekit_enabled setting is true
    try:
        from app.models.system_setting import SystemSetting

        homekit_db = next(get_db())
        try:
            # Check database setting (takes precedence over env var)
            homekit_setting = homekit_db.query(SystemSetting).filter(
                SystemSetting.key == "homekit_enabled"
            ).first()

            homekit_service = get_homekit_service()

            # Use database setting if exists, otherwise env var
            if homekit_setting:
                homekit_enabled = homekit_setting.value.lower() in ('true', '1', 'yes')
                homekit_service.config.enabled = homekit_enabled
            else:
                homekit_enabled = homekit_service.config.enabled

            if homekit_enabled:
                # Get enabled cameras for HomeKit
                homekit_cameras = homekit_db.query(Camera).filter(Camera.is_enabled == True).all()
                success = await homekit_service.start(homekit_cameras)

                if success:
                    logger.info(
                        "HomeKit service started",
                        extra={
                            "event_type": "homekit_init_complete",
                            "camera_count": len(homekit_cameras),
                            "port": homekit_service.config.port
                        }
                    )
                else:
                    logger.warning(
                        f"HomeKit service failed to start: {homekit_service._error}",
                        extra={"event_type": "homekit_init_failed", "error": homekit_service._error}
                    )
            else:
                logger.debug(
                    "HomeKit service disabled",
                    extra={"event_type": "homekit_disabled"}
                )
        finally:
            homekit_db.close()
    except Exception as e:
        # HomeKit failure should not prevent app startup
        logger.warning(
            f"HomeKit initialization failed (non-fatal): {e}",
            extra={"event_type": "homekit_init_failed", "error": str(e)}
        )

    # Initialize Cloudflare Tunnel (Story P11-1.1)
    # Only starts if tunnel_enabled setting is true and token is saved
    try:
        from app.services.tunnel_service import get_tunnel_service
        from app.utils.encryption import decrypt_password

        tunnel_db = next(get_db())
        try:
            # Check if tunnel is enabled
            tunnel_enabled_setting = tunnel_db.query(SystemSetting).filter(
                SystemSetting.key == "settings_tunnel_enabled"
            ).first()

            tunnel_enabled = (
                tunnel_enabled_setting
                and tunnel_enabled_setting.value.lower() in ('true', '1', 'yes')
            )

            if tunnel_enabled:
                # Get saved token
                token_setting = tunnel_db.query(SystemSetting).filter(
                    SystemSetting.key == "settings_tunnel_token"
                ).first()

                if token_setting and token_setting.value:
                    try:
                        # Decrypt token
                        token = decrypt_password(token_setting.value)

                        # Start tunnel
                        tunnel_service = get_tunnel_service()
                        success = await tunnel_service.start(token)

                        if success:
                            logger.info(
                                "Cloudflare Tunnel started",
                                extra={"event_type": "tunnel_init_complete"}
                            )
                        else:
                            logger.warning(
                                f"Cloudflare Tunnel failed to start: {tunnel_service.error_message}",
                                extra={
                                    "event_type": "tunnel_init_failed",
                                    "error": tunnel_service.error_message
                                }
                            )
                    except ValueError as e:
                        logger.warning(
                            f"Failed to decrypt tunnel token: {e}",
                            extra={"event_type": "tunnel_token_decrypt_failed"}
                        )
                else:
                    logger.warning(
                        "Tunnel enabled but no token saved",
                        extra={"event_type": "tunnel_no_token"}
                    )
            else:
                logger.debug(
                    "Cloudflare Tunnel disabled",
                    extra={"event_type": "tunnel_disabled"}
                )
        finally:
            tunnel_db.close()
    except Exception as e:
        # Tunnel failure should not prevent app startup
        logger.warning(
            f"Cloudflare Tunnel initialization failed (non-fatal): {e}",
            extra={"event_type": "tunnel_init_failed", "error": str(e)}
        )

    logger.info(
        "Application startup complete",
        extra={
            "event_type": "app_startup_complete",
            "version": APP_VERSION,
            "cameras_started": started_count if 'started_count' in dir() else 0
        }
    )

    yield  # Application runs here

    # Shutdown logic with structured logging
    logger.info(
        "Application shutting down",
        extra={"event_type": "app_shutdown_start", "version": APP_VERSION}
    )

    # Shutdown Digest Scheduler (Story P4-4.2)
    try:
        await shutdown_digest_scheduler()
        logger.info(
            "Digest scheduler stopped",
            extra={"event_type": "digest_scheduler_shutdown_complete"}
        )
    except Exception as e:
        logger.error(
            f"Error stopping digest scheduler: {e}",
            extra={"event_type": "digest_scheduler_shutdown_error", "error": str(e)}
        )

    # Shutdown HomeKit service (Story P4-6.1)
    try:
        homekit_service = get_homekit_service()
        if homekit_service.is_running:
            await homekit_service.stop()
            logger.info(
                "HomeKit service stopped",
                extra={"event_type": "homekit_shutdown_complete"}
            )
    except Exception as e:
        logger.error(
            f"Error stopping HomeKit service: {e}",
            extra={"event_type": "homekit_shutdown_error", "error": str(e)}
        )

    # Shutdown Cloudflare Tunnel (Story P11-1.1)
    try:
        from app.services.tunnel_service import get_tunnel_service
        tunnel_service = get_tunnel_service()
        if tunnel_service.is_running:
            await tunnel_service.stop()
            logger.info(
                "Cloudflare Tunnel stopped",
                extra={"event_type": "tunnel_shutdown_complete"}
            )
    except Exception as e:
        logger.error(
            f"Error stopping Cloudflare Tunnel: {e}",
            extra={"event_type": "tunnel_shutdown_error", "error": str(e)}
        )

    # Disconnect MQTT service (Story P4-2.1)
    try:
        await shutdown_mqtt_service()
        logger.info(
            "MQTT service disconnected",
            extra={"event_type": "mqtt_shutdown_complete"}
        )
    except Exception as e:
        logger.error(
            f"Error disconnecting MQTT: {e}",
            extra={"event_type": "mqtt_shutdown_error", "error": str(e)}
        )

    # Disconnect Protect controllers (Story P2-1.4, AC5)
    # Must happen before other services shutdown
    try:
        await protect_service.disconnect_all(timeout=10.0)
        logger.info(
            "Protect controllers disconnected",
            extra={"event_type": "protect_shutdown_complete"}
        )
    except Exception as e:
        logger.error(
            f"Error disconnecting Protect controllers: {e}",
            extra={"event_type": "protect_shutdown_error", "error": str(e)}
        )

    # Stop scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info(
            "Scheduler stopped",
            extra={"event_type": "scheduler_shutdown"}
        )

    # Stop Event Processor (Story 3.3)
    await shutdown_event_processor(timeout=30.0)
    logger.info(
        "Event processor stopped",
        extra={"event_type": "event_processor_shutdown"}
    )

    # Stop all camera threads
    camera_service.stop_all_cameras(timeout=5.0)
    logger.info(
        "Cameras stopped",
        extra={"event_type": "cameras_shutdown"}
    )

    logger.info(
        "Application shutdown complete",
        extra={"event_type": "app_shutdown_complete", "version": APP_VERSION}
    )


# Story P10-5.1: OpenAPI Specification Enhancement
# API documentation and security scheme configuration
OPENAPI_DESCRIPTION = """
## Overview

ArgusAI is an AI-powered event detection system for home security. It analyzes video feeds
from UniFi Protect cameras, RTSP IP cameras, and USB webcams, detects motion and smart events,
and generates natural language descriptions using multi-provider AI.

## Authentication

Most endpoints require authentication via JWT bearer token. Obtain a token by calling
`POST /api/v1/auth/login` with valid credentials.

Include the token in the `Authorization` header:
```
Authorization: Bearer <your_token>
```

## Key Features

- **Camera Management**: Configure RTSP, USB, and UniFi Protect cameras
- **Event Detection**: AI-powered motion and object detection with natural language descriptions
- **Smart Detection**: Person, vehicle, package, and animal classification
- **Entity Recognition**: Identify recurring visitors and vehicles
- **Push Notifications**: Web push notifications for important events
- **Home Automation**: MQTT/Home Assistant and HomeKit integration

## Rate Limits

- Authentication endpoints: 5 requests per 15 minutes per IP
- GET requests: 100 requests per minute per IP
- POST/PUT/DELETE requests: 20 requests per minute per IP
- API key authenticated requests: Use per-key limits (configurable)
- Health/metrics endpoints: Exempt from rate limiting

Rate limit headers are included in all responses:
- `X-RateLimit-Limit`: Maximum requests allowed
- `X-RateLimit-Remaining`: Requests remaining in window
- `X-RateLimit-Reset`: Unix timestamp when limit resets
- `Retry-After`: Seconds until rate limit resets (on 429 responses)

## Versioning

All API endpoints are prefixed with `/api/v1`. Future breaking changes will use `/api/v2`.
"""

# OpenAPI tags with descriptions for endpoint grouping
OPENAPI_TAGS = [
    {"name": "Authentication", "description": "User authentication and session management"},
    {"name": "cameras", "description": "Camera configuration and control"},
    {"name": "events", "description": "AI-generated event management and search"},
    {"name": "Protect Controllers", "description": "UniFi Protect controller management"},
    {"name": "Alert Rules", "description": "Alert rule configuration"},
    {"name": "Webhooks", "description": "Webhook delivery management"},
    {"name": "Notifications", "description": "In-app notification management"},
    {"name": "Push Notifications", "description": "Web push subscription management"},
    {"name": "Integrations", "description": "MQTT and Home Assistant integration"},
    {"name": "HomeKit", "description": "Apple HomeKit integration"},
    {"name": "Context", "description": "Entity and similarity search"},
    {"name": "Summaries", "description": "Activity summaries and digests"},
    {"name": "Feedback", "description": "User feedback on AI descriptions"},
    {"name": "Voice", "description": "Voice query processing"},
    {"name": "System", "description": "System configuration and health"},
    {"name": "AI", "description": "AI provider configuration and usage"},
    {"name": "Metrics", "description": "Prometheus metrics"},
    {"name": "Logs", "description": "Application log access"},
    {"name": "Discovery", "description": "ONVIF camera discovery"},
    {"name": "Audio", "description": "Audio event detection"},
    {"name": "Digests", "description": "Daily digest scheduling"},
    {"name": "Motion Events", "description": "Raw motion event tracking"},
    {"name": "System Notifications", "description": "System alerts and cost notifications"},
    {"name": "API Keys", "description": "API key management for external integrations"},
]

# Create FastAPI app with enhanced OpenAPI configuration
app = FastAPI(
    title="ArgusAI API",
    description=OPENAPI_DESCRIPTION,
    version="1.0.0",
    redirect_slashes=False,  # Disable trailing slash redirects to avoid proxy issues
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=OPENAPI_TAGS,
    contact={
        "name": "ArgusAI",
        "url": "https://github.com/project-argusai/ArgusAI",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    lifespan=lifespan
)

# Story P10-5.1: Custom OpenAPI schema with security schemes
def custom_openapi():
    """Generate custom OpenAPI schema with security schemes for JWT authentication."""
    if app.openapi_schema:
        return app.openapi_schema

    from fastapi.openapi.utils import get_openapi

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
        contact=app.contact,
        license_info=app.license_info,
    )

    # Add security schemes (AC-5.1.3, Story P13-1.4)
    openapi_schema["components"]["securitySchemes"] = {
        "bearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT access token obtained from POST /api/v1/auth/login"
        },
        "cookieAuth": {
            "type": "apiKey",
            "in": "cookie",
            "name": "access_token",
            "description": "JWT token stored in HTTP-only cookie (set by login endpoint)"
        },
        "apiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "API key for programmatic access. Create keys via POST /api/v1/api-keys/"
        }
    }

    # Apply security globally (endpoints can override with security=[])
    openapi_schema["security"] = [
        {"bearerAuth": []},
        {"cookieAuth": []},
        {"apiKeyAuth": []}
    ]

    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Add rate limiter state (Story 6.3, P14-2.6)
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
# Use global_limiter for all endpoints, auth limiter for auth-specific
app.state.limiter = global_limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom exception handler to ensure CORS headers on HTTPException responses
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

@app.exception_handler(HTTPException)
async def cors_http_exception_handler(request: Request, exc: HTTPException):
    """
    Custom HTTPException handler that ensures CORS headers are included.
    This is needed because HTTPException responses bypass CORS middleware.
    """
    # Get origin from request
    origin = request.headers.get("origin", "")

    # Build CORS headers if origin is allowed
    cors_headers = {}
    if origin in settings.cors_origins_list or "*" in settings.cors_origins_list:
        cors_headers = {
            "Access-Control-Allow-Origin": origin or settings.cors_origins_list[0],
            "Access-Control-Allow-Credentials": "true",
        }

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=cors_headers,
    )

# Add request logging middleware (Story 6.2, AC: #2)
app.add_middleware(RequestLoggingMiddleware)

# Add authentication middleware (Story 6.3, AC: #6)
# Note: Auth middleware runs after logging middleware (LIFO order)
app.add_middleware(AuthMiddleware)

# Add rate limiting middleware (Story P14-2.6)
# Runs after auth to access request.state.api_key for API key rate limiting
# Note: Middleware executes in reverse order (LIFO), so this runs AFTER auth
if settings.RATE_LIMIT_ENABLED:
    app.add_middleware(RateLimitMiddleware)
    logger.info(
        "Rate limiting middleware enabled",
        extra={
            "event_type": "rate_limit_enabled",
            "default_limit": settings.RATE_LIMIT_DEFAULT,
            "read_limit": settings.RATE_LIMIT_READS,
            "write_limit": settings.RATE_LIMIT_WRITES,
        }
    )

# Add device last_seen tracking middleware (Story P12-2.4)
# Runs after auth to access request.state.user, updates device last_seen_at
app.add_middleware(LastSeenMiddleware)

# Add HTTPS redirect middleware (Story P9-5.1)
# Only active when SSL is enabled and redirect is configured
if settings.SSL_ENABLED and settings.SSL_REDIRECT_HTTP:
    app.add_middleware(
        HTTPSRedirectMiddleware,
        ssl_enabled=settings.SSL_ENABLED,
        ssl_port=settings.SSL_PORT
    )
    logger.info(
        "HTTPS redirect middleware enabled",
        extra={"event_type": "https_redirect_enabled", "ssl_port": settings.SSL_PORT}
    )

# Register API routers
# Note: Register discovery_router before cameras_router to prevent {camera_id} from matching "discover"
# Note: Register motion_events before cameras to ensure proper route precedence
app.include_router(discovery_router, prefix=f"{settings.API_V1_PREFIX}/cameras")  # Story P5-2.1 - ONVIF Discovery (must be before cameras_router)
app.include_router(motion_events_router, prefix=settings.API_V1_PREFIX)
app.include_router(cameras_router, prefix=settings.API_V1_PREFIX)
app.include_router(ai_router, prefix=settings.API_V1_PREFIX)
app.include_router(events_router, prefix=settings.API_V1_PREFIX)
app.include_router(metrics_router, prefix=settings.API_V1_PREFIX)
app.include_router(system_router, prefix=settings.API_V1_PREFIX)  # Story 3.4
app.include_router(alert_rules_router, prefix=settings.API_V1_PREFIX)  # Story 5.1
app.include_router(webhooks_router, prefix=settings.API_V1_PREFIX)  # Story 5.3
app.include_router(notifications_router, prefix=settings.API_V1_PREFIX)  # Story 5.4
app.include_router(websocket_router)  # Story 5.4 - WebSocket at /ws (no prefix)
app.include_router(logs_router, prefix=settings.API_V1_PREFIX)  # Story 6.2 - Log retrieval
app.include_router(auth_router, prefix=settings.API_V1_PREFIX)  # Story 6.3 - Authentication
app.include_router(protect_router, prefix=settings.API_V1_PREFIX)  # Story P2-1.1 - UniFi Protect
app.include_router(system_notifications_router, prefix=settings.API_V1_PREFIX)  # Story P3-7.4 - Cost Alerts
app.include_router(push_router, prefix=settings.API_V1_PREFIX)  # Story P4-1.1 - Web Push
app.include_router(integrations_router, prefix=settings.API_V1_PREFIX)  # Story P4-2.1 - MQTT
app.include_router(context_router, prefix=settings.API_V1_PREFIX)  # Story P4-3.1 - Embeddings
app.include_router(summaries_router, prefix=settings.API_V1_PREFIX)  # Story P4-4.1 - Activity Summaries
app.include_router(digests_router, prefix=settings.API_V1_PREFIX)  # Story P4-4.2 - Daily Digest Scheduler
app.include_router(feedback_router, prefix=settings.API_V1_PREFIX)  # Story P4-5.2 - Feedback Statistics
app.include_router(voice_router, prefix=settings.API_V1_PREFIX)  # Story P4-6.3 - Voice Query API
app.include_router(homekit_router, prefix=settings.API_V1_PREFIX)  # Story P5-1.1 - HomeKit API
app.include_router(audio_router, prefix=settings.API_V1_PREFIX)  # Story P6-3.2 - Audio Event Detection
app.include_router(devices_router, prefix=settings.API_V1_PREFIX)  # Story P11-2.4 - Device Registration
app.include_router(mobile_auth_router, prefix=settings.API_V1_PREFIX)  # Story P12-3 - Mobile Auth
app.include_router(api_keys_router, prefix=settings.API_V1_PREFIX)  # Story P13-1 - API Key Management
app.include_router(users_router, prefix=settings.API_V1_PREFIX)  # Story P15-2.3 - User Management

# Thumbnail serving endpoint (with CORS support)
from fastapi.responses import FileResponse, Response as FastAPIResponse

@app.get("/api/v1/thumbnails/{date}/{filename}")
async def get_thumbnail(date: str, filename: str, request: Request):
    """Serve thumbnail images with CORS headers"""
    thumbnail_dir = os.path.join(os.path.dirname(__file__), 'data', 'thumbnails')
    file_path = os.path.join(thumbnail_dir, date, filename)

    # Get origin for CORS - validate against allowed origins
    origin = request.headers.get("origin", "")
    if origin and origin in settings.cors_origins_list:
        allowed_origin = origin
    elif origin:
        # Origin provided but not in allowed list - use first allowed origin
        allowed_origin = settings.cors_origins_list[0] if settings.cors_origins_list else "*"
    else:
        # No origin header (direct image load) - allow all
        allowed_origin = "*"

    cors_headers = {
        "Access-Control-Allow-Origin": allowed_origin,
        "Access-Control-Allow-Credentials": "true" if allowed_origin != "*" else "false",
        "Cache-Control": "public, max-age=86400"
    }

    if os.path.exists(file_path):
        with open(file_path, "rb") as f:
            content = f.read()
        return FastAPIResponse(
            content=content,
            media_type="image/jpeg",
            headers=cors_headers
        )

    return FastAPIResponse(
        content=b"",
        status_code=404,
        headers=cors_headers
    )


@app.get("/")
async def root():
    """Root endpoint - API status check"""
    return {
        "name": "ArgusAI API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint (no authentication required)"""
    return {
        "status": "healthy",
        "camera_count": len(camera_service.get_all_camera_status())
    }


@app.get("/metrics")
async def prometheus_metrics():
    """
    Prometheus metrics endpoint (Story 6.2, AC: #6)

    Returns Prometheus-compatible metrics for scraping.
    """
    return Response(
        content=get_metrics(),
        media_type=get_content_type()
    )


if __name__ == "__main__":
    import uvicorn
    import ssl

    # Build uvicorn configuration
    uvicorn_config = {
        "app": "main:app",
        "host": "0.0.0.0",
        "reload": settings.DEBUG,
        "log_level": settings.LOG_LEVEL.lower()
    }

    # Configure SSL if enabled and ready (Story P9-5.1)
    if settings.ssl_ready:
        uvicorn_config["port"] = settings.SSL_PORT
        uvicorn_config["ssl_certfile"] = settings.SSL_CERT_FILE
        uvicorn_config["ssl_keyfile"] = settings.SSL_KEY_FILE

        # Set minimum TLS version
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        if settings.SSL_MIN_VERSION == "TLSv1_3":
            ssl_context.minimum_version = ssl.TLSVersion.TLSv1_3
        else:
            ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2

        logger.info(
            "Starting server with SSL/HTTPS enabled",
            extra={
                "event_type": "ssl_startup",
                "port": settings.SSL_PORT,
                "cert_file": settings.SSL_CERT_FILE,
                "min_tls_version": settings.SSL_MIN_VERSION
            }
        )
    else:
        uvicorn_config["port"] = 8000
        if settings.SSL_ENABLED:
            # SSL is enabled but not properly configured
            logger.warning(
                "SSL is enabled but not properly configured. Running on HTTP.",
                extra={
                    "event_type": "ssl_config_warning",
                    "ssl_enabled": settings.SSL_ENABLED,
                    "cert_file_exists": settings.SSL_CERT_FILE is not None,
                    "key_file_exists": settings.SSL_KEY_FILE is not None
                }
            )
        else:
            logger.info(
                "SSL is not enabled. Running on HTTP.",
                extra={"event_type": "http_startup", "port": 8000}
            )

    uvicorn.run(**uvicorn_config)
