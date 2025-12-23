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

Currently, ArgusAI uses basic authentication. API endpoints are protected when auth is enabled.

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

Real-time updates are available via WebSocket:

```
ws://localhost:8000/ws
```

Events:
- `event.created` - New event detected
- `camera.status` - Camera status change
- `notification.new` - New notification

## Rate Limiting

API requests are not rate-limited by default. Consider adding rate limiting for production deployments.

## OpenAPI Documentation

Interactive API documentation available at:

- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`
