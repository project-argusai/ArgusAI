---
sidebar_position: 2
---

# API Keys

ArgusAI supports API key authentication for external integrations and automation tools. API keys provide scoped access to the API with configurable rate limits.

## Overview

API keys are ideal for:
- **Home Assistant** integrations
- **n8n** automation workflows
- **Custom scripts** and monitoring tools
- **Third-party applications**

## Available Scopes

| Scope | Description |
|-------|-------------|
| `read:events` | Read events, exports, and event media (including thumbnails) |
| `read:cameras` | Read cameras, status, and previews |
| `write:cameras` | Create, update, and delete cameras and their capture settings |
| `admin` | Allowlisted event writes and camera routes. Does not grant user, API-key, or system management |

API keys work only on an explicit allowlist of event, camera, and event-thumbnail routes. Other routes, including motion-event export, webhook-log export, and context batch or export endpoints, return HTTP 403. Camera connection tests, on-demand analysis, and ONVIF discovery scans are not on the allowlist. Event writes and deletes require `admin`.

## Creating API Keys

### Via Settings UI

1. Navigate to **Settings** > **Security** tab
2. Click **Create Key**
3. Enter a descriptive name (e.g., "Home Assistant Integration")
4. Select the required scopes
5. Set expiration (optional)
6. Configure rate limit (default: 100 requests/minute)
7. Click **Create Key**

:::warning Important
The full API key is only shown once at creation time. Copy and store it securely - it cannot be retrieved again.
:::

### Via API

```bash
curl -X POST http://localhost:8000/api/v1/api-keys \
  -H "Content-Type: application/json" \
  -H "Cookie: argusai_access_token=your-jwt-token" \
  -d '{
    "name": "Home Assistant",
    "scopes": ["read:events", "read:cameras"],
    "rate_limit_per_minute": 60
  }'
```

## Using API Keys

Include the API key in the `X-API-Key` header:

```bash
curl -H "X-API-Key: argus_abc123..." http://localhost:8000/api/v1/events
```

## API Endpoints

### List API Keys

```http
GET /api/v1/api-keys
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `include_revoked` | boolean | Include revoked keys (default: false) |

**Response:**
```json
[
  {
    "id": "uuid",
    "name": "Home Assistant",
    "prefix": "argus_ab",
    "scopes": ["read:events", "read:cameras"],
    "is_active": true,
    "expires_at": "2026-01-15T00:00:00Z",
    "last_used_at": "2025-01-15T10:30:00Z",
    "usage_count": 1523,
    "rate_limit_per_minute": 100,
    "created_at": "2025-01-01T00:00:00Z"
  }
]
```

### Create API Key

```http
POST /api/v1/api-keys
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
| `expires_at` | datetime | No | Expiration date (ISO 8601) |
| `rate_limit_per_minute` | integer | No | Rate limit (default: 100) |

**Response:** `201 Created`
```json
{
  "id": "uuid",
  "name": "Home Assistant Integration",
  "key": "argus_abc123def456...",
  "prefix": "argus_ab",
  "scopes": ["read:events", "read:cameras"],
  "expires_at": "2026-01-15T00:00:00Z",
  "rate_limit_per_minute": 100,
  "created_at": "2025-01-15T10:30:00Z"
}
```

### Get API Key Details

```http
GET /api/v1/api-keys/{key_id}
```

### Revoke API Key

```http
DELETE /api/v1/api-keys/{key_id}
```

Immediately revokes the API key. Any requests using this key will be rejected.

### Get API Key Usage

```http
GET /api/v1/api-keys/{key_id}/usage
```

**Response:**
```json
{
  "id": "uuid",
  "name": "Home Assistant",
  "prefix": "argus_ab",
  "usage_count": 1523,
  "last_used_at": "2025-01-15T10:30:00Z",
  "last_used_ip": "192.168.1.100",
  "rate_limit_per_minute": 100
}
```

## Rate Limiting

Each API key has a configurable rate limit (requests per minute). When exceeded:

**Response:** `429 Too Many Requests`
```json
{
  "detail": "Rate limit exceeded. Limit: 100/minute. Retry after 45 seconds."
}
```

**Rate Limit Headers:**
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1735123456
Retry-After: 45
```

## Integration Examples

### Home Assistant REST Sensor

```yaml
sensor:
  - platform: rest
    name: ArgusAI Latest Event
    resource: http://argusai:8000/api/v1/events?limit=1
    headers:
      X-API-Key: argus_abc123...
    value_template: "{{ value_json.items[0].description }}"
    scan_interval: 60
```

### n8n HTTP Request Node

Configure an HTTP Request node:
- **Method**: GET
- **URL**: `http://argusai:8000/api/v1/events`
- **Headers**:
  - `X-API-Key`: `argus_abc123...`

### Python Script

```python
import requests

API_KEY = "argus_abc123..."
BASE_URL = "http://localhost:8000/api/v1"

headers = {"X-API-Key": API_KEY}

# Get recent events
response = requests.get(f"{BASE_URL}/events?limit=10", headers=headers)
events = response.json()

for event in events["items"]:
    print(f"{event['timestamp']}: {event['description']}")
```

### curl Examples

```bash
# List events
curl -H "X-API-Key: argus_abc123..." \
  http://localhost:8000/api/v1/events

# Get camera status
curl -H "X-API-Key: argus_abc123..." \
  http://localhost:8000/api/v1/cameras

# Filter events by camera
curl -H "X-API-Key: argus_abc123..." \
  "http://localhost:8000/api/v1/events?camera_id=uuid&limit=20"
```

## Security Best Practices

1. **Use Minimal Scopes**: Only grant the permissions needed for each integration
2. **Set Expiration Dates**: For temporary integrations, set an expiration
3. **Use Descriptive Names**: Make it easy to identify which integration uses each key
4. **Revoke Unused Keys**: Remove keys that are no longer needed
5. **Monitor Usage**: Check usage statistics to detect unusual patterns
6. **Protect Keys**: Never commit API keys to version control or share publicly

## Troubleshooting

### "Invalid API key" Error

- Verify the key is correctly copied (no extra spaces)
- Check the key hasn't been revoked
- Ensure the key hasn't expired

### "Insufficient permissions" Error

- Check the key has the required scope for the endpoint
- Use `admin` scope for full access

### Rate Limit Exceeded

- Wait for the rate limit window to reset (check `Retry-After` header)
- Increase the key's `rate_limit_per_minute` if needed
- Optimize your integration to make fewer requests
