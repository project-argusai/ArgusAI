"""
Prometheus Metrics Registry (Story 6.2, AC: #6)

Provides Prometheus-compatible metrics for:
- HTTP request counts and latencies
- Event processing statistics
- AI API usage and costs
- Camera connection status
- System resource usage (CPU, memory, disk)
"""
import time
import logging
from typing import Optional
from prometheus_client import (
    Counter, Histogram, Gauge, Info,
    CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
)
import psutil

logger = logging.getLogger(__name__)

# Create a custom registry to avoid conflicts with default registry
REGISTRY = CollectorRegistry()

# ============================================================================
# Application Info
# ============================================================================

app_info = Info(
    'app',
    'Application information',
    registry=REGISTRY
)

# ============================================================================
# HTTP Request Metrics
# ============================================================================

http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'path', 'status_code'],
    registry=REGISTRY
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'path'],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=REGISTRY
)

http_requests_in_progress = Gauge(
    'http_requests_in_progress',
    'Number of HTTP requests currently being processed',
    ['method'],
    registry=REGISTRY
)

# ============================================================================
# Event Processing Metrics
# ============================================================================

events_processed_total = Counter(
    'events_processed_total',
    'Total events processed',
    ['camera_id', 'status'],
    registry=REGISTRY
)

event_processing_duration_seconds = Histogram(
    'event_processing_duration_seconds',
    'Event processing duration in seconds',
    ['stage'],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
    registry=REGISTRY
)

event_queue_depth = Gauge(
    'event_queue_depth',
    'Current depth of event processing queue',
    registry=REGISTRY
)

# ============================================================================
# AI API Metrics
# ============================================================================

ai_api_calls_total = Counter(
    'ai_api_calls_total',
    'Total AI API calls',
    ['provider', 'model', 'status'],
    registry=REGISTRY
)

ai_api_duration_seconds = Histogram(
    'ai_api_duration_seconds',
    'AI API call duration in seconds',
    ['provider', 'model'],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
    registry=REGISTRY
)

ai_api_tokens_total = Counter(
    'ai_api_tokens_total',
    'Total tokens used in AI API calls',
    ['provider', 'model', 'type'],  # type: input, output
    registry=REGISTRY
)

ai_api_cost_total = Counter(
    'ai_api_cost_total',
    'Estimated total cost of AI API calls in USD',
    ['provider', 'model'],
    registry=REGISTRY
)

# ============================================================================
# Camera Metrics
# ============================================================================

cameras_connected = Gauge(
    'cameras_connected',
    'Number of cameras currently connected',
    registry=REGISTRY
)

cameras_total = Gauge(
    'cameras_total',
    'Total number of configured cameras',
    registry=REGISTRY
)

camera_frames_captured_total = Counter(
    'camera_frames_captured_total',
    'Total frames captured from cameras',
    ['camera_id'],
    registry=REGISTRY
)

# ============================================================================
# Alert and Webhook Metrics
# ============================================================================

alerts_triggered_total = Counter(
    'alerts_triggered_total',
    'Total alerts triggered',
    ['rule_id', 'action_type'],
    registry=REGISTRY
)

webhooks_sent_total = Counter(
    'webhooks_sent_total',
    'Total webhooks sent',
    ['status'],  # success, failure
    registry=REGISTRY
)

webhook_duration_seconds = Histogram(
    'webhook_duration_seconds',
    'Webhook delivery duration in seconds',
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=REGISTRY
)

# ============================================================================
# Push Notification Metrics (Story P4-1.1)
# ============================================================================

push_notifications_sent_total = Counter(
    'push_notifications_sent_total',
    'Total push notifications sent',
    ['status'],  # success, failure
    registry=REGISTRY
)

push_notification_duration_seconds = Histogram(
    'push_notification_duration_seconds',
    'Push notification delivery duration in seconds',
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=REGISTRY
)

push_subscriptions_active = Gauge(
    'push_subscriptions_active',
    'Number of active push subscriptions',
    registry=REGISTRY
)

# ============================================================================
# MQTT Integration Metrics (Story P4-2.1)
# ============================================================================

mqtt_connection_status = Gauge(
    'mqtt_connection_status',
    'MQTT connection status (0=disconnected, 1=connected)',
    registry=REGISTRY
)

mqtt_messages_published_total = Counter(
    'mqtt_messages_published_total',
    'Total MQTT messages published',
    registry=REGISTRY
)

mqtt_publish_errors_total = Counter(
    'mqtt_publish_errors_total',
    'Total MQTT publish errors',
    registry=REGISTRY
)

mqtt_reconnect_attempts_total = Counter(
    'mqtt_reconnect_attempts_total',
    'Total MQTT reconnect attempts',
    registry=REGISTRY
)

# ============================================================================
# HomeKit Streaming Metrics (Story P7-3.1)
# ============================================================================

homekit_streams_active = Gauge(
    'argusai_homekit_streams_active',
    'Number of active HomeKit camera streams',
    ['camera_id'],
    registry=REGISTRY
)

homekit_streams_total = Gauge(
    'argusai_homekit_streams_total',
    'Total number of active HomeKit streams across all cameras',
    registry=REGISTRY
)

homekit_stream_starts_total = Counter(
    'argusai_homekit_stream_starts_total',
    'Total HomeKit stream start attempts',
    ['camera_id', 'quality', 'status'],  # status: success, rejected, error
    registry=REGISTRY
)

homekit_stream_rejections_total = Counter(
    'argusai_homekit_stream_rejections_total',
    'Total HomeKit stream rejections due to concurrent limit',
    ['camera_id'],
    registry=REGISTRY
)

# ============================================================================
# HomeKit Snapshot Metrics (Story P7-3.2)
# ============================================================================

homekit_snapshot_cache_hits_total = Counter(
    'argusai_homekit_snapshot_cache_hits_total',
    'Total HomeKit snapshot cache hits',
    ['camera_id'],
    registry=REGISTRY
)

homekit_snapshot_cache_misses_total = Counter(
    'argusai_homekit_snapshot_cache_misses_total',
    'Total HomeKit snapshot cache misses',
    ['camera_id'],
    registry=REGISTRY
)

# ============================================================================
# System Resource Metrics
# ============================================================================

system_cpu_usage_percent = Gauge(
    'system_cpu_usage_percent',
    'Current CPU usage percentage',
    registry=REGISTRY
)

system_memory_usage_percent = Gauge(
    'system_memory_usage_percent',
    'Current memory usage percentage',
    registry=REGISTRY
)

system_memory_used_bytes = Gauge(
    'system_memory_used_bytes',
    'Memory used in bytes',
    registry=REGISTRY
)

system_disk_usage_percent = Gauge(
    'system_disk_usage_percent',
    'Disk usage percentage',
    ['path'],
    registry=REGISTRY
)

system_disk_used_bytes = Gauge(
    'system_disk_used_bytes',
    'Disk space used in bytes',
    ['path'],
    registry=REGISTRY
)

# ============================================================================
# Application Uptime
# ============================================================================

_start_time: Optional[float] = None

app_uptime_seconds = Gauge(
    'app_uptime_seconds',
    'Application uptime in seconds',
    registry=REGISTRY
)

# ============================================================================
# Helper Functions
# ============================================================================


def init_metrics(version: str = "1.0.0"):
    """
    Initialize metrics with application info.

    Args:
        version: Application version string
    """
    global _start_time
    _start_time = time.time()

    app_info.info({
        'version': version,
        'name': 'ArgusAI'
    })

    logger.info("Prometheus metrics initialized", extra={"version": version})


def record_request_metrics(
    method: str,
    path: str,
    status_code: int,
    response_time_seconds: float
):
    """
    Record HTTP request metrics.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: Request path
        status_code: Response status code
        response_time_seconds: Response time in seconds
    """
    # Normalize path to avoid high cardinality
    normalized_path = _normalize_path(path)

    http_requests_total.labels(
        method=method,
        path=normalized_path,
        status_code=str(status_code)
    ).inc()

    http_request_duration_seconds.labels(
        method=method,
        path=normalized_path
    ).observe(response_time_seconds)


def record_event_processed(camera_id: str, status: str, processing_time_seconds: float):
    """
    Record event processing metrics.

    Args:
        camera_id: Camera ID that generated the event
        status: Processing status (success, error)
        processing_time_seconds: Total processing time
    """
    events_processed_total.labels(camera_id=camera_id, status=status).inc()
    event_processing_duration_seconds.labels(stage="total").observe(processing_time_seconds)


def record_ai_api_call(
    provider: str,
    model: str,
    status: str,
    duration_seconds: float,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: float = 0.0
):
    """
    Record AI API call metrics.

    Args:
        provider: AI provider (openai, anthropic, google)
        model: Model name
        status: Call status (success, error)
        duration_seconds: Call duration
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        cost_usd: Estimated cost in USD
    """
    ai_api_calls_total.labels(provider=provider, model=model, status=status).inc()
    ai_api_duration_seconds.labels(provider=provider, model=model).observe(duration_seconds)

    if input_tokens > 0:
        ai_api_tokens_total.labels(provider=provider, model=model, type="input").inc(input_tokens)
    if output_tokens > 0:
        ai_api_tokens_total.labels(provider=provider, model=model, type="output").inc(output_tokens)
    if cost_usd > 0:
        ai_api_cost_total.labels(provider=provider, model=model).inc(cost_usd)


def record_camera_status(connected_count: int, total_count: int):
    """
    Update camera connection metrics.

    Args:
        connected_count: Number of connected cameras
        total_count: Total configured cameras
    """
    cameras_connected.set(connected_count)
    cameras_total.set(total_count)


def record_webhook_sent(status: str, duration_seconds: float):
    """
    Record webhook delivery metrics.

    Args:
        status: Delivery status (success, failure)
        duration_seconds: Delivery duration
    """
    webhooks_sent_total.labels(status=status).inc()
    webhook_duration_seconds.observe(duration_seconds)


def record_alert_triggered(rule_id: str, action_type: str):
    """
    Record alert trigger metrics.

    Args:
        rule_id: Alert rule ID
        action_type: Type of action (notification, webhook)
    """
    alerts_triggered_total.labels(rule_id=rule_id, action_type=action_type).inc()


def record_push_notification_sent(status: str, duration_seconds: float = 0.0):
    """
    Record push notification delivery metrics.

    Args:
        status: Delivery status (success, failure)
        duration_seconds: Delivery duration
    """
    push_notifications_sent_total.labels(status=status).inc()
    if duration_seconds > 0:
        push_notification_duration_seconds.observe(duration_seconds)


def update_push_subscription_count(count: int):
    """
    Update active push subscription count.

    Args:
        count: Number of active subscriptions
    """
    push_subscriptions_active.set(count)


def update_mqtt_connection_status(connected: bool):
    """
    Update MQTT connection status metric.

    Args:
        connected: Whether MQTT is connected
    """
    mqtt_connection_status.set(1 if connected else 0)


def record_mqtt_message_published():
    """Record a successful MQTT message publish."""
    mqtt_messages_published_total.inc()


def record_mqtt_publish_error():
    """Record an MQTT publish error."""
    mqtt_publish_errors_total.inc()


def record_mqtt_reconnect_attempt():
    """Record an MQTT reconnect attempt."""
    mqtt_reconnect_attempts_total.inc()


def record_homekit_stream_start(
    camera_id: str,
    quality: str,
    status: str
):
    """
    Record a HomeKit stream start attempt (Story P7-3.1 AC4).

    Args:
        camera_id: Camera ID
        quality: Stream quality (low, medium, high)
        status: Result status (success, rejected, error)
    """
    homekit_stream_starts_total.labels(
        camera_id=camera_id,
        quality=quality,
        status=status
    ).inc()

    if status == 'rejected':
        homekit_stream_rejections_total.labels(camera_id=camera_id).inc()


def update_homekit_active_streams(camera_id: str, count: int):
    """
    Update the active stream count for a camera (Story P7-3.1 AC4).

    Args:
        camera_id: Camera ID
        count: Number of active streams for this camera
    """
    homekit_streams_active.labels(camera_id=camera_id).set(count)


def update_homekit_total_streams(total_count: int):
    """
    Update the total active stream count (Story P7-3.1 AC4).

    Args:
        total_count: Total number of active streams across all cameras
    """
    homekit_streams_total.set(total_count)


def record_homekit_snapshot_cache_hit(camera_id: str):
    """
    Record a HomeKit snapshot cache hit (Story P7-3.2 AC3).

    Args:
        camera_id: Camera ID
    """
    homekit_snapshot_cache_hits_total.labels(camera_id=camera_id).inc()


def record_homekit_snapshot_cache_miss(camera_id: str):
    """
    Record a HomeKit snapshot cache miss (Story P7-3.2 AC3).

    Args:
        camera_id: Camera ID
    """
    homekit_snapshot_cache_misses_total.labels(camera_id=camera_id).inc()


def update_system_metrics():
    """
    Update system resource metrics (CPU, memory, disk).

    Should be called periodically (e.g., every minute).
    """
    try:
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=None)
        system_cpu_usage_percent.set(cpu_percent)

        # Memory usage
        memory = psutil.virtual_memory()
        system_memory_usage_percent.set(memory.percent)
        system_memory_used_bytes.set(memory.used)

        # Disk usage (root partition)
        disk = psutil.disk_usage('/')
        system_disk_usage_percent.labels(path='/').set(disk.percent)
        system_disk_used_bytes.labels(path='/').set(disk.used)

        # Update uptime
        if _start_time:
            app_uptime_seconds.set(time.time() - _start_time)

    except Exception as e:
        logger.warning(f"Failed to update system metrics: {e}")


def get_metrics() -> bytes:
    """
    Generate Prometheus metrics output.

    Returns:
        Prometheus text format metrics
    """
    # Update system metrics before generating output
    update_system_metrics()
    return generate_latest(REGISTRY)


def get_content_type() -> str:
    """
    Get the content type for Prometheus metrics.

    Returns:
        Content type string
    """
    return CONTENT_TYPE_LATEST


def _normalize_path(path: str) -> str:
    """
    Normalize request path to avoid high cardinality.

    Replaces UUIDs and numeric IDs with placeholders.

    Args:
        path: Original request path

    Returns:
        Normalized path
    """
    import re

    # Replace UUIDs
    path = re.sub(
        r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
        '{id}',
        path,
        flags=re.IGNORECASE
    )

    # Replace numeric IDs
    path = re.sub(r'/\d+', '/{id}', path)

    return path
