---
sidebar_position: 1
---

# API Overview

ArgusAI provides a RESTful API for all functionality.

## Base URL

```
http://localhost:8000/api/v1
```

With HTTPS:
```
https://your-domain.com/api/v1
```

## Authentication

ArgusAI supports two authentication methods:

### API Key Authentication (Recommended for Integrations)

Include the `X-API-Key` header with your API key:

```bash
curl -H "X-API-Key: argus_abc123..." http://localhost:8000/api/v1/events
```

API keys provide:
- **Scoped permissions**: `read:events`, `read:cameras`, `write:cameras`, `admin`
- **Per-key rate limiting**: Configurable requests per minute
- **Usage tracking**: Monitor requests and last used timestamp

See [API Keys](./api-keys) for full documentation.

### JWT Token Authentication (Dashboard)

For browser-based access, JWT tokens are used via cookies or Authorization header.

## Common Endpoints

### Cameras

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/cameras` | List all cameras |
| POST | `/cameras` | Create camera |
| GET | `/cameras/{id}` | Get camera details |
| PUT | `/cameras/{id}` | Update camera |
| DELETE | `/cameras/{id}` | Delete camera |
| POST | `/cameras/{id}/start` | Start camera |
| POST | `/cameras/{id}/stop` | Stop camera |
| POST | `/cameras/test` | Test connection |

### Events

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/events` | List events (paginated) |
| GET | `/events/{id}` | Get event details |
| DELETE | `/events/{id}` | Delete event |
| POST | `/events/{id}/reanalyse` | Re-analyze event |
| GET | `/events/stats` | Event statistics |
| GET | `/events/export` | Export events CSV |

### Protect Controllers

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/protect/controllers` | List controllers |
| POST | `/protect/controllers` | Add controller |
| GET | `/protect/controllers/{id}` | Get controller |
| PUT | `/protect/controllers/{id}` | Update controller |
| DELETE | `/protect/controllers/{id}` | Delete controller |
| POST | `/protect/controllers/test` | Test connection |
| GET | `/protect/controllers/{id}/cameras` | List cameras |

### AI

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/ai/providers` | List AI providers |
| POST | `/ai/describe` | Describe image |
| GET | `/ai/usage` | Get usage stats |
| GET | `/ai/capabilities` | Get provider capabilities |
| GET | `/ai/context-metrics` | Get MCP context metrics |
| POST | `/ai/refine-prompt` | AI-assisted prompt refinement |

### API Keys

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api-keys` | List API keys |
| POST | `/api-keys` | Create API key |
| GET | `/api-keys/{id}` | Get API key details |
| DELETE | `/api-keys/{id}` | Revoke API key |
| GET | `/api-keys/{id}/usage` | Get usage stats |

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/system/health` | Health check |
| GET | `/system/settings` | Get settings |
| PUT | `/system/settings` | Update settings |
| GET | `/system/storage` | Storage stats |
| GET | `/system/ssl-status` | SSL configuration |

## Request Format

### Headers

```
Content-Type: application/json
Accept: application/json
```

### Pagination

List endpoints support pagination:

```
GET /events?page=1&limit=20
```

Response includes:
```json
{
  "items": [...],
  "total": 150,
  "page": 1,
  "limit": 20,
  "pages": 8
}
```

### Filtering

Many endpoints support filtering:

```
GET /events?camera_id=123&detection_type=person
```

## Response Format

### Success

```json
{
  "id": "uuid",
  "created_at": "2025-12-23T10:30:00Z",
  "...": "..."
}
```

### Error

```json
{
  "detail": "Error message",
  "status_code": 400
}
```

## WebSocket

Real-time updates are available via WebSocket. The browser sends the same session cookie used for HTTP requests. Non-browser clients send `Authorization: Bearer` with a JWT that has a server-side session. Query-string tokens are not accepted. A disallowed `Origin` is rejected. After logout, revocation, or deactivation, an open socket is closed within 30 seconds. The web app stops automatic reconnects when that close is an authorization failure.

```
ws://localhost:8000/ws
```

Events:
- `event.created` - New event detected
- `camera.status` - Camera status change
- `notification.new` - New notification

## Rate Limiting

API key authenticated requests are rate-limited based on the key's configured limit. Rate limit headers are included in responses:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1735123456
```

When rate limited, the API returns `429 Too Many Requests` with a `Retry-After` header.

## OpenAPI Documentation

Interactive API documentation available at:

- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`
