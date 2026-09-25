# ArgusAI API Reference

Complete REST API documentation for ArgusAI v1.

**Base URL:** `http://localhost:8000/api/v1`

**Interactive Docs:**
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

## Table of Contents

- [Authentication](#authentication)
- [Response Format](#response-format)
- [API Keys](#api-keys)
- [Cameras](#cameras)
- [Events](#events)
- [UniFi Protect](#unifi-protect)
- [AI Providers](#ai-providers)
- [Alert Rules](#alert-rules)
- [Context & Entities](#context--entities)
- [Push Notifications](#push-notifications)
- [Integrations](#integrations)
- [Voice Queries](#voice-queries)
- [Activity Summaries](#activity-summaries)
- [Feedback](#feedback)
- [System](#system)
- [Error Handling](#error-handling)

---

## Authentication

ArgusAI supports two authentication methods:

### 1. API Key Authentication (Recommended for Integrations)

API keys provide scoped access for external integrations and automation tools.

```bash
# Using X-API-Key header
curl -H "X-API-Key: argus_abc123..." http://localhost:8000/api/v1/events
```

**Key Features:**
- Scoped permissions: `read:events`, `read:cameras`, `write:cameras`, `admin`
- Per-key rate limiting with configurable limits
- Automatic expiration (optional)
- Usage tracking and statistics

API keys are accepted only on an explicit allowlist of event, camera, and
event-thumbnail routes (`backend/app/core/api_key_scopes.py`). Every other
route denies API keys, including batch and export endpoints outside that
list (motion-event export, webhook-log export, context adjustment export,
and embedding batches). A route added later stays denied until it is added
to the allowlist.

A `read:events` key can read events, including exports and media: event
frames and video, plus `GET /api/v1/thumbnails/{date}/{filename}`. A
`read:cameras` key can read camera status, previews, and discovery
availability. A `write:cameras` key can create, update, and delete cameras
and change their capture, motion, zone, schedule, and audio settings.
Camera connection tests, on-demand analysis, and ONVIF discovery scans are
not included. Event writes and deletes, including bulk delete and cleanup,
require `admin` (there is no `write:events` scope). The `admin` scope grants
those allowlisted event and camera routes, but never user, API-key, or
system management. Use a signed-in administrator session for those
management endpoints. A valid key without the required route scope receives
HTTP 403. `HEAD` on an allowlisted read route uses that route's read scope.

**Rate Limit Headers:**
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1735123456
```

### 2. JWT Token Authentication (Dashboard)

For browser-based dashboard access, JWT tokens are used via cookies.

```bash
# Using Authorization header (alternative to cookie)
curl -H "Authorization: Bearer eyJ..." http://localhost:8000/api/v1/events
```

### Authentication Priority

When both authentication methods are present, API keys take priority over JWT tokens.

---

## Response Format

### Success Responses

**Single Resource:**
```json
{
  "id": "uuid",
  "name": "Front Door Camera",
  "created_at": "2025-01-15T10:30:00Z"
}
```

**List Response:**
```json
{
  "items": [...],
  "total": 150,
  "limit": 20,
  "offset": 0,
  "has_more": true
}
```

**Protect Controller Response:**
```json
{
  "data": {...},
  "meta": {
    "request_id": "uuid",
    "timestamp": "2025-01-15T10:30:00Z",
    "count": 1
  }
}
```

### Error Response

```json
{
  "detail": "Camera not found",
  "status_code": 404
}
```

---

## API Keys

Create and manage API keys for external integrations. Requires a signed-in administrator. An API key, including one with the `admin` scope, cannot call these endpoints.

### Available Scopes

| Scope | Description |
|-------|-------------|
| `read:events` | Read events, exports, and event media (including thumbnails) |
| `read:cameras` | Read cameras, status, and previews |
| `write:cameras` | Create, update, and delete cameras and their capture settings |
| `admin` | Allowlisted event writes and camera routes. Does not grant user, API-key, or system management |

### List API Keys

```http
GET /api-keys
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `include_revoked` | boolean | Include revoked keys (default: false) |

**Response:** `200 OK`
```json
[
  {
    "id": "uuid",
    "name": "Home Assistant Integration",
    "prefix": "argus_ab",
    "scopes": ["read:events", "read:cameras"],
    "is_active": true,
    "expires_at": "2026-01-15T00:00:00Z",
    "last_used_at": "2025-01-15T10:30:00Z",
    "usage_count": 1523,
    "rate_limit_per_minute": 100,
    "created_at": "2025-01-01T00:00:00Z",
    "revoked_at": null
  }
]
```

### Create API Key

```http
POST /api-keys
```

**Request Body:**
```json
{
  "name": "Home Assistant Integration",
  "scopes": ["read:events", "read:cameras"],
  "expires_at": "2026-01-15T00:00:00Z",
  "rate_limit_per_minute": 100
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Descriptive name for the key |
| `scopes` | string[] | Yes | Array of permission scopes |
| `expires_at` | datetime | No | Expiration date (ISO 8601), null for never |
| `rate_limit_per_minute` | integer | No | Rate limit (default: 100, max: 10000) |

**Response:** `201 Created`
```json
{
  "id": "uuid",
  "name": "Home Assistant Integration",
  "key": "argus_abc123def456ghi789...",
  "prefix": "argus_ab",
  "scopes": ["read:events", "read:cameras"],
  "expires_at": "2026-01-15T00:00:00Z",
  "rate_limit_per_minute": 100,
  "created_at": "2025-01-15T10:30:00Z"
}
```

> **Important:** The `key` field contains the full API key and is only returned once at creation time. Store it securely - it cannot be retrieved again.

### Get API Key

```http
GET /api-keys/{key_id}
```

**Response:** `200 OK`
```json
{
  "id": "uuid",
  "name": "Home Assistant Integration",
  "prefix": "argus_ab",
  "scopes": ["read:events", "read:cameras"],
  "is_active": true,
  "expires_at": "2026-01-15T00:00:00Z",
  "last_used_at": "2025-01-15T10:30:00Z",
  "usage_count": 1523,
  "rate_limit_per_minute": 100,
  "created_at": "2025-01-01T00:00:00Z",
  "revoked_at": null
}
```

### Revoke API Key

```http
DELETE /api-keys/{key_id}
```

Immediately revokes the API key. Any subsequent requests using this key will be rejected.

**Response:** `200 OK`
```json
{
  "id": "uuid",
  "name": "Home Assistant Integration",
  "revoked_at": "2025-01-15T10:30:00Z"
}
```

### Get API Key Usage

```http
GET /api-keys/{key_id}/usage
```

**Response:** `200 OK`
```json
{
  "id": "uuid",
  "name": "Home Assistant Integration",
  "prefix": "argus_ab",
  "usage_count": 1523,
  "last_used_at": "2025-01-15T10:30:00Z",
  "last_used_ip": "192.168.1.100",
  "rate_limit_per_minute": 100,
  "created_at": "2025-01-01T00:00:00Z"
}
```

### Rate Limiting

API keys are rate limited based on their configured `rate_limit_per_minute` value. When rate limited, the API returns:

**Response:** `429 Too Many Requests`
```json
{
  "detail": "Rate limit exceeded. Limit: 100/minute. Retry after 45 seconds."
}
```

**Headers:**
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1735123500
Retry-After: 45
```

### Example: Creating an API Key for Home Assistant

```bash
# Create a read-only key for Home Assistant
curl -X POST http://localhost:8000/api/v1/api-keys \
  -H "Content-Type: application/json" \
  -H "Cookie: argusai_access_token=your-jwt-token" \
  -d '{
    "name": "Home Assistant",
    "scopes": ["read:events", "read:cameras"],
    "rate_limit_per_minute": 60
  }'

# Response includes the full key (save this!)
# {
#   "id": "uuid",
#   "key": "argus_abc123...",
#   ...
# }

# Use the key in Home Assistant configuration
# sensor:
#   - platform: rest
#     resource: http://argusai:8000/api/v1/events?limit=1
#     headers:
#       X-API-Key: argus_abc123...
```

---

## Cameras

Manage RTSP, USB, and Protect cameras.

### List Cameras

```http
GET /cameras
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `is_enabled` | boolean | Filter by enabled status |

**Response:** `200 OK`
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Front Door",
    "source_type": "protect",
    "is_enabled": true,
    "status": "connected",
    "last_frame_at": "2025-01-15T10:30:00Z"
  }
]
```

### Create Camera

```http
POST /cameras
```

**Request Body:**
```json
{
  "name": "Backyard Camera",
  "source_type": "rtsp",
  "rtsp_url": "rtsp://192.168.1.50:554/stream1",
  "username": "admin",
  "password": "secret",
  "is_enabled": true
}
```

**Response:** `201 Created`

### Get Camera

```http
GET /cameras/{camera_id}
```

**Response:** `200 OK`

### Update Camera

```http
PUT /cameras/{camera_id}
```

**Request Body:** Partial update supported
```json
{
  "name": "Updated Name",
  "is_enabled": false
}
```

### Delete Camera

```http
DELETE /cameras/{camera_id}
```

**Response:** `204 No Content`

### Test Camera Connection

```http
POST /cameras/{camera_id}/test
```

Tests connection without starting capture.

**Response:** `200 OK`
```json
{
  "success": true,
  "message": "Connection successful",
  "frame_size": [1920, 1080]
}
```

### Get Camera Preview

```http
GET /cameras/{camera_id}/preview
```

Returns current frame as base64-encoded JPEG.

**Response:** `200 OK`
```json
{
  "image": "data:image/jpeg;base64,/9j/4AAQ...",
  "timestamp": "2025-01-15T10:30:00Z"
}
```

### Trigger Manual Analysis

```http
POST /cameras/{camera_id}/analyze
```

Manually trigger AI analysis (bypasses motion detection).

**Response:** `200 OK`
```json
{
  "event_id": "uuid",
  "description": "A person walking toward the front door"
}
```

### Motion Detection Configuration

```http
GET /cameras/{camera_id}/motion/config
PUT /cameras/{camera_id}/motion/config
```

**Config Object:**
```json
{
  "enabled": true,
  "sensitivity": 50,
  "cooldown_seconds": 5,
  "algorithm": "mog2"
}
```

### Detection Zones

```http
GET /cameras/{camera_id}/zones
PUT /cameras/{camera_id}/zones
```

**Zones Object:**
```json
{
  "zones": [
    {
      "name": "Driveway",
      "points": [[0.1, 0.5], [0.9, 0.5], [0.9, 1.0], [0.1, 1.0]],
      "enabled": true
    }
  ]
}
```

### Detection Schedule

```http
GET /cameras/{camera_id}/schedule
PUT /cameras/{camera_id}/schedule
```

**Schedule Object:**
```json
{
  "enabled": true,
  "always_on": false,
  "time_ranges": [
    {"start": "22:00", "end": "06:00", "days": ["mon", "tue", "wed", "thu", "fri"]}
  ]
}
```

---

## Events

AI-generated event descriptions from camera feeds.

### List Events

```http
GET /events
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `camera_id` | uuid | Filter by camera |
| `start_time` | datetime | Start of date range (ISO 8601) |
| `end_time` | datetime | End of date range |
| `source_type` | string | `rtsp`, `usb`, or `protect` |
| `smart_detection_type` | string | `person`, `vehicle`, `package`, `animal`, `ring` |
| `analysis_mode` | string | `single_frame`, `multi_frame`, `video_native` |
| `anomaly_severity` | string | `low`, `medium`, `high` |
| `search_query` | string | Full-text search in descriptions |
| `limit` | integer | Max results (default: 20) |
| `offset` | integer | Pagination offset |
| `sort_order` | string | `asc` or `desc` (default: `desc`) |

**Example:**
```bash
curl "http://localhost:8000/api/v1/events?camera_id=uuid&search_query=person&limit=10"
```

**Response:** `200 OK`
```json
{
  "items": [
    {
      "id": "uuid",
      "camera_id": "uuid",
      "camera_name": "Front Door",
      "description": "A person in a blue jacket approached the front door",
      "enriched_description": "John arrived at the front door",
      "timestamp": "2025-01-15T10:30:00Z",
      "source_type": "protect",
      "smart_detection_type": "person",
      "analysis_mode": "multi_frame",
      "confidence_score": 0.92,
      "anomaly_score": 15,
      "recognition_status": "known",
      "thumbnail_url": "/api/v1/events/uuid/thumbnail"
    }
  ],
  "total": 150,
  "limit": 10,
  "offset": 0,
  "has_more": true
}
```

### Get Event

```http
GET /events/{event_id}
```

Includes correlated events and matched entities.

**Response:** `200 OK`
```json
{
  "id": "uuid",
  "description": "A person in a blue jacket approached the front door",
  "enriched_description": "John arrived at the front door",
  "confidence_score": 0.92,
  "anomaly_score": 15,
  "recognition_status": "known",
  "matched_entity_ids": ["entity-uuid"],
  "correlated_events": [
    {"id": "uuid", "camera_name": "Side Yard", "description": "..."}
  ],
  "similar_events": [
    {"id": "uuid", "similarity": 0.89, "description": "..."}
  ]
}
```

### Delete Event

```http
DELETE /events/{event_id}
```

**Response:** `204 No Content`

### Bulk Delete Events

```http
DELETE /events/bulk
```

**Request Body:**
```json
{
  "event_ids": ["uuid1", "uuid2", "uuid3"]
}
```

Max 100 events per request.

### Re-analyze Event

```http
POST /events/{event_id}/reanalyze
```

Re-analyze with different mode. Rate limited: 3 per hour.

**Request Body:**
```json
{
  "analysis_mode": "video_native"
}
```

**Response:** `200 OK`
```json
{
  "event_id": "uuid",
  "old_description": "...",
  "new_description": "...",
  "old_confidence": 0.75,
  "new_confidence": 0.92
}
```

### Export Events

```http
GET /events/export
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `format` | string | `json` or `csv` |
| `start_time` | datetime | Start of range |
| `end_time` | datetime | End of range |
| `camera_id` | uuid | Filter by camera |

Returns streaming response for large exports.

### Event Feedback

```http
POST /events/{event_id}/feedback
GET /events/{event_id}/feedback
PUT /events/{event_id}/feedback
DELETE /events/{event_id}/feedback
```

**Request Body:**
```json
{
  "rating": "helpful",
  "correction": "It was actually a delivery driver, not a visitor"
}
```

Rating: `helpful` or `not_helpful`

---

## UniFi Protect

Native UniFi Protect controller integration.

### List Controllers

```http
GET /protect/controllers
```

### Create Controller

```http
POST /protect/controllers
```

**Request Body:**
```json
{
  "name": "Home UDM Pro",
  "host": "192.168.1.1",
  "port": 443,
  "username": "argusai",
  "password": "secret",
  "verify_ssl": false
}
```

### Test Connection (New Credentials)

```http
POST /protect/controllers/test
```

Tests without saving. Use for validation before create.

**Request Body:** Same as create

**Response:** `200 OK`
```json
{
  "success": true,
  "controller_name": "UDM Pro",
  "firmware_version": "3.0.15",
  "camera_count": 8
}
```

### Test Connection (Existing)

```http
POST /protect/controllers/{controller_id}/test
```

Tests using stored credentials.

### Connect/Disconnect Controller

```http
POST /protect/controllers/{controller_id}/connect
POST /protect/controllers/{controller_id}/disconnect
```

Establishes or closes WebSocket connection for real-time events.

### Discover Cameras

```http
GET /protect/controllers/{controller_id}/cameras
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `force_refresh` | boolean | Bypass 60s cache |

**Response:** `200 OK`
```json
{
  "data": [
    {
      "id": "protect-camera-id",
      "name": "Front Door",
      "type": "G4 Doorbell Pro",
      "is_enabled_for_ai": true,
      "smart_detection_types": ["person", "vehicle", "package"],
      "is_connected": true
    }
  ]
}
```

### Enable Camera for AI

```http
POST /protect/controllers/{controller_id}/cameras/{camera_id}/enable
```

Creates camera record and starts event listening.

### Disable Camera

```http
POST /protect/controllers/{controller_id}/cameras/{camera_id}/disable
```

### Update Camera Filters

```http
PUT /protect/controllers/{controller_id}/cameras/{camera_id}/filters
```

**Request Body:**
```json
{
  "smart_detection_types": ["person", "package"],
  "include_motion": false
}
```

---

## AI Providers

Configure and monitor AI providers.

### Get AI Usage Statistics

```http
GET /ai/usage
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `start_date` | date | Start of range |
| `end_date` | date | End of range |
| `provider` | string | Filter by provider |

**Response:** `200 OK`
```json
{
  "total_requests": 1523,
  "total_tokens": 245000,
  "total_cost_usd": 12.45,
  "by_provider": {
    "openai": {"requests": 1200, "tokens": 200000, "cost_usd": 10.00},
    "anthropic": {"requests": 323, "tokens": 45000, "cost_usd": 2.45}
  },
  "daily_breakdown": [...]
}
```

### Get AI Capabilities

```http
GET /ai/capabilities
```

Returns provider capabilities including video support.

**Response:** `200 OK`
```json
{
  "providers": {
    "openai": {
      "available": true,
      "supports_video": true,
      "max_images": 10,
      "supported_formats": ["jpeg", "png", "webp", "mp4"]
    },
    "anthropic": {
      "available": true,
      "supports_video": false,
      "max_images": 5
    }
  }
}
```

### Get Context Metrics

```http
GET /ai/context-metrics
```

Returns MCP context system metrics for monitoring performance (Phase 14).

**Response:** `200 OK`
```json
{
  "cache_hit_rate": 0.75,
  "total_requests": 1000,
  "cache_hits": 750,
  "cache_misses": 250,
  "timeouts": 2,
  "cache_ttl_seconds": 30,
  "timeout_threshold_ms": 80,
  "cache_size": 5
}
```

| Field | Type | Description |
|-------|------|-------------|
| `cache_hit_rate` | float | Ratio of cache hits to total requests (0-1) |
| `total_requests` | integer | Total context gathering requests |
| `cache_hits` | integer | Number of requests served from cache |
| `cache_misses` | integer | Number of requests requiring database queries |
| `timeouts` | integer | Number of context queries that exceeded 80ms timeout |
| `cache_ttl_seconds` | integer | Cache entry time-to-live |
| `timeout_threshold_ms` | integer | Query timeout threshold in milliseconds |
| `cache_size` | integer | Number of entries currently in cache |

---

## Alert Rules

Configure automated alert triggers.

### List Rules

```http
GET /alert-rules
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `is_enabled` | boolean | Filter by enabled status |

### Create Rule

```http
POST /alert-rules
```

**Request Body:**
```json
{
  "name": "Person at Night",
  "is_enabled": true,
  "conditions": {
    "camera_ids": ["uuid1", "uuid2"],
    "detection_types": ["person"],
    "keywords": ["front door"],
    "time_range": {"start": "22:00", "end": "06:00"},
    "anomaly_threshold": 60,
    "entity_ids": ["entity-uuid"],
    "entity_names": ["John*", "Delivery*"]
  },
  "actions": {
    "push_notification": true,
    "in_app_notification": true,
    "webhook_url": "https://example.com/webhook",
    "webhook_headers": {"Authorization": "Bearer token"}
  }
}
```

### Update Rule

```http
PUT /alert-rules/{rule_id}
```

### Delete Rule

```http
DELETE /alert-rules/{rule_id}
```

### Test Rule

```http
POST /alert-rules/{rule_id}/test
```

Tests rule against recent events.

**Response:** `200 OK`
```json
{
  "would_trigger": true,
  "matching_events": 5,
  "sample_events": [...]
}
```

---

## Context & Entities

Temporal context engine, entity recognition, and anomaly detection.

### Find Similar Events

```http
GET /context/similar/{event_id}
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | integer | Max results (default: 10) |
| `threshold` | float | Minimum similarity (0-1) |

**Response:** `200 OK`
```json
{
  "event_id": "uuid",
  "similar_events": [
    {
      "id": "uuid",
      "similarity": 0.89,
      "description": "...",
      "timestamp": "2025-01-14T10:30:00Z"
    }
  ]
}
```

### List Entities

```http
GET /context/entities
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `entity_type` | string | `person` or `vehicle` |
| `named_only` | boolean | Only return named entities |
| `limit` | integer | Max results |
| `offset` | integer | Pagination offset |

**Response:** `200 OK`
```json
{
  "entities": [
    {
      "id": "uuid",
      "entity_type": "person",
      "name": "John",
      "first_seen_at": "2025-01-01T10:00:00Z",
      "last_seen_at": "2025-01-15T10:30:00Z",
      "occurrence_count": 45,
      "is_vip": true,
      "is_blocked": false
    }
  ],
  "total": 23
}
```

### Get Entity

```http
GET /context/entities/{entity_id}
```

Includes recent events for this entity.

### Update Entity

```http
PUT /context/entities/{entity_id}
```

**Request Body:**
```json
{
  "name": "John Smith",
  "is_vip": true,
  "is_blocked": false
}
```

### Delete Entity

```http
DELETE /context/entities/{entity_id}
```

### List VIP Entities

```http
GET /context/entities/vip
```

Returns all entities marked as VIP.

### List Blocked Entities

```http
GET /context/entities/blocked
```

Returns all blocked entities.

### Get Anomaly Score

```http
POST /context/anomaly/score
```

**Request Body:**
```json
{
  "event_id": "uuid"
}
```

**Response:** `200 OK`
```json
{
  "event_id": "uuid",
  "anomaly_score": 75,
  "severity": "high",
  "factors": [
    {"factor": "unusual_time", "contribution": 40},
    {"factor": "rare_detection_type", "contribution": 35}
  ]
}
```

### Get Camera Baseline

```http
GET /context/anomaly/baseline/{camera_id}
```

**Response:** `200 OK`
```json
{
  "camera_id": "uuid",
  "baseline_period_days": 7,
  "hourly_patterns": {
    "0": {"avg_events": 0.5, "std_dev": 0.3},
    "8": {"avg_events": 5.2, "std_dev": 1.8}
  },
  "detection_type_distribution": {
    "person": 0.65,
    "vehicle": 0.30,
    "package": 0.05
  }
}
```

### Get Activity Patterns

```http
GET /context/patterns/{camera_id}
```

**Response:** `200 OK`
```json
{
  "camera_id": "uuid",
  "patterns": [
    {
      "pattern_type": "recurring_visitor",
      "description": "Mail carrier arrives between 10-11 AM on weekdays",
      "confidence": 0.92,
      "occurrences": 23
    }
  ]
}
```

---

## Push Notifications

Web Push notification management.

### Subscribe to Push

```http
POST /push/subscribe
```

**Request Body:**
```json
{
  "subscription": {
    "endpoint": "https://fcm.googleapis.com/...",
    "keys": {
      "p256dh": "...",
      "auth": "..."
    }
  },
  "device_name": "iPhone 15"
}
```

### Unsubscribe

```http
POST /push/unsubscribe
```

**Request Body:**
```json
{
  "endpoint": "https://fcm.googleapis.com/..."
}
```

### Get Subscriptions

```http
GET /push/subscriptions
```

### Test Push Notification

```http
POST /push/test
```

Sends a test notification to all subscribed devices.

---

## Integrations

Home Assistant MQTT and HomeKit integration.

### MQTT Configuration

```http
GET /integrations/mqtt/config
PUT /integrations/mqtt/config
```

**Config Object:**
```json
{
  "enabled": true,
  "host": "192.168.1.100",
  "port": 1883,
  "username": "homeassistant",
  "password": "secret",
  "discovery_prefix": "homeassistant",
  "base_topic": "argusai"
}
```

### Get MQTT Status

```http
GET /integrations/mqtt/status
```

**Response:** `200 OK`
```json
{
  "connected": true,
  "broker": "192.168.1.100:1883",
  "last_publish": "2025-01-15T10:30:00Z",
  "published_entities": 8
}
```

### Test MQTT Connection

```http
POST /integrations/mqtt/test
```

**Request Body:**
```json
{
  "host": "192.168.1.100",
  "port": 1883,
  "username": "test",
  "password": "test"
}
```

### Publish Discovery Config

```http
POST /integrations/mqtt/publish-discovery
```

Publishes Home Assistant MQTT auto-discovery configs for all cameras.

### HomeKit Configuration

```http
GET /integrations/homekit/config
PUT /integrations/homekit/config
```

**Config Object:**
```json
{
  "enabled": true,
  "bridge_name": "ArgusAI Bridge",
  "port": 51826
}
```

### Get HomeKit Status

```http
GET /integrations/homekit/status
```

**Response:** `200 OK`
```json
{
  "enabled": true,
  "paired": true,
  "pairing_code": "123-45-678",
  "accessories": 5
}
```

### Get HomeKit Pairing Code

```http
GET /integrations/homekit/pairing-code
```

Returns the pairing code for Apple Home setup.

---

## Voice Queries

Natural language queries about security events.

### Submit Voice Query

```http
POST /voice/query
```

**Request Body:**
```json
{
  "query": "What happened at the front door today?",
  "camera_id": "uuid"
}
```

**Response:** `200 OK`
```json
{
  "response": "I found 5 events at the front door today. There were 3 person detections and 2 package deliveries. The most recent was a delivery at 2:30 PM.",
  "events_found": 5,
  "event_ids": ["uuid1", "uuid2", "uuid3", "uuid4", "uuid5"]
}
```

**Example Queries:**
- "What's happening at the front door?"
- "Any activity this morning?"
- "Was there anyone in the backyard today?"
- "Show me recent package deliveries"
- "How many people visited yesterday?"

---

## Activity Summaries

AI-generated activity summaries and daily digests.

### Generate Summary

```http
POST /summaries/generate
```

**Request Body:**
```json
{
  "hours_back": 24,
  "camera_ids": ["uuid1", "uuid2"]
}
```

Or with explicit time range:
```json
{
  "start_time": "2025-01-14T00:00:00Z",
  "end_time": "2025-01-15T00:00:00Z"
}
```

**Response:** `200 OK`
```json
{
  "id": "uuid",
  "period_start": "2025-01-14T00:00:00Z",
  "period_end": "2025-01-15T00:00:00Z",
  "summary": "A quiet day with 12 events across 3 cameras. Most activity was at the front door (8 events) with regular mail delivery at 10:30 AM and a package drop-off at 2:15 PM. The backyard camera detected 3 instances of wildlife (likely deer) in the early morning.",
  "event_count": 12,
  "highlights": [
    {"type": "package_delivery", "time": "2025-01-14T14:15:00Z"},
    {"type": "unusual_activity", "description": "Activity at 3 AM"}
  ]
}
```

### Get Daily Summary

```http
GET /summaries/daily
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `date` | date | Specific date (default: today) |

### List Recent Summaries

```http
GET /summaries/recent
```

Returns today's and yesterday's summaries.

### List All Summaries

```http
GET /summaries
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | integer | Max results |
| `offset` | integer | Pagination offset |

---

## Feedback

Feedback statistics and AI improvement insights.

### Get Feedback Statistics

```http
GET /feedback/stats
```

**Response:** `200 OK`
```json
{
  "total_feedback": 234,
  "helpful_count": 198,
  "not_helpful_count": 36,
  "accuracy_rate": 0.846,
  "by_camera": {
    "Front Door": {"helpful": 85, "not_helpful": 12}
  },
  "daily_trend": [...]
}
```

### Get Prompt Insights

```http
GET /feedback/prompt-insights
```

AI-generated suggestions for prompt improvements based on feedback.

**Response:** `200 OK`
```json
{
  "suggestions": [
    {
      "id": "uuid",
      "category": "false_positive",
      "description": "Users frequently correct 'visitor' to 'delivery driver'",
      "suggested_change": "Add context about uniforms and packages",
      "confidence": 0.85,
      "affected_events": 12
    }
  ]
}
```

### Apply Suggestion

```http
POST /feedback/prompt-insights/apply
```

**Request Body:**
```json
{
  "suggestion_id": "uuid"
}
```

---

## System

System configuration, health, and maintenance.

### Health Check

```http
GET /system/health
```

**Response:** `200 OK`
```json
{
  "status": "healthy",
  "database": "connected",
  "ai_providers": {
    "openai": "available",
    "anthropic": "available"
  },
  "protect_controllers": {
    "Home UDM Pro": "connected"
  },
  "active_cameras": 5,
  "uptime_seconds": 86400
}
```

### Get Settings

```http
GET /system/settings
```

Returns all system settings (sensitive fields masked).

### Update Settings

```http
PUT /system/settings
```

**Request Body:**
```json
{
  "openai_api_key": "sk-...",
  "retention_days": 30,
  "daily_cost_limit": 5.00
}
```

### Get Retention Policy

```http
GET /system/retention
PUT /system/retention
```

**Policy Object:**
```json
{
  "retention_days": 30,
  "cleanup_enabled": true,
  "last_cleanup": "2025-01-15T00:00:00Z"
}
```

### Get Storage Info

```http
GET /system/storage
```

**Response:** `200 OK`
```json
{
  "database_size_mb": 245.5,
  "thumbnails_size_mb": 1024.3,
  "clips_size_mb": 512.0,
  "total_events": 15234,
  "oldest_event": "2024-12-15T00:00:00Z"
}
```

### Create Backup

```http
POST /system/backup
```

Creates a backup of database and settings.

**Response:** `200 OK`
```json
{
  "backup_id": "2025-01-15T10-30-00",
  "size_mb": 256.5,
  "download_url": "/api/v1/system/backup/2025-01-15T10-30-00/download"
}
```

### Download Backup

```http
GET /system/backup/{timestamp}/download
```

Returns backup file as download.

### Restore Backup

```http
POST /system/restore
```

**Request Body:** Multipart form with backup file

---

## Error Handling

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| `200` | Success |
| `201` | Created |
| `204` | No Content (successful delete) |
| `400` | Bad Request (invalid input) |
| `404` | Not Found |
| `409` | Conflict (duplicate resource) |
| `422` | Validation Error |
| `429` | Rate Limited |
| `500` | Internal Server Error |
| `503` | Service Unavailable |

### Error Response Format

```json
{
  "detail": "Camera with name 'Front Door' already exists",
  "status_code": 409,
  "error_code": "DUPLICATE_RESOURCE"
}
```

### Rate Limits

| Endpoint | Limit |
|----------|-------|
| `POST /events/{id}/reanalyze` | 3 per hour |
| `POST /summaries/generate` | 10 per hour |
| `POST /voice/query` | 30 per minute |

---

## WebSocket

Real-time event notifications via WebSocket.

### Connect

```
ws://localhost:8000/api/v1/ws
```

### Message Types

**Event Notification:**
```json
{
  "type": "event",
  "data": {
    "id": "uuid",
    "camera_name": "Front Door",
    "description": "Person detected",
    "timestamp": "2025-01-15T10:30:00Z"
  }
}
```

**Camera Status:**
```json
{
  "type": "camera_status",
  "data": {
    "camera_id": "uuid",
    "status": "connected"
  }
}
```

---

*Last updated: December 2025 (Phase 14 - MCP Context Enhancement)*
