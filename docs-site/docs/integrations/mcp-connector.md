---
sidebar_position: 5
---

# Assistant Connector (MCP)

ArgusAI includes a **read-only** [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server. Connect an assistant bot to it and ask:

- "Anything happen at home in the last hour?"
- "Is there a package at the door?"
- "Who came by today?"
- "When was the blue truck last here?"

The assistant answers from ArgusAI's stored event descriptions. It cannot change anything: the connector has no tools for deleting events, changing settings, editing alert rules, or controlling cameras.

## How it works

| | |
|---|---|
| **Endpoint** | `POST https://argusai.example.com/api/v1/mcp` |
| **Transport** | MCP Streamable HTTP, stateless, JSON responses (no SSE stream; `GET` returns 405) |
| **Auth** | A dedicated API key with the `read:mcp` scope, sent as `Authorization: Bearer argus_...` or `X-API-Key: argus_...` |
| **Rate limit** | Per key: the lower of the key's own limit and `MCP_RATE_LIMIT_PER_MINUTE` (default 60/minute). Each HTTP request counts once |
| **Audit** | Every tool call is recorded (see [Security](#security)) |

Replace `argusai.example.com` with the hostname your [Cloudflare Tunnel](./cloudflare-tunnel.md) (or reverse proxy) serves ArgusAI on. The path goes through the same `/api/v1` proxy as the web app, so no extra tunnel route is needed.

## 1. Create a read-only key

1. Open **Settings → API Keys** and select **Create Key**.
2. Name it after the bot, for example `Assistant bot`.
3. Tick **Assistant connector (MCP)** only. The connector refuses any key that also has **Admin** or **Write Cameras**, so the form clears those when you pick it. You may add **Read Events** or **Read Cameras**, but the connector does not need them.
4. Optional: set an expiry and a lower rate limit.
5. Copy the key (`argus_...`). It is shown once.

Revoke the key from the same page at any time; the next request with it gets `401`.

## 2. Connect the assistant

Add a remote MCP server in the assistant's connector settings:

- **URL:** `https://argusai.example.com/api/v1/mcp`
- **Authentication:** bearer token / API key → the `argus_...` key
  (if the client only supports custom headers, use `X-API-Key: argus_...`)

Check it from a terminal:

```bash
curl -s https://argusai.example.com/api/v1/mcp \
  -H "Authorization: Bearer $ARGUS_MCP_KEY" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## Tools

All tools are annotated `readOnlyHint: true`. Times in results are ISO 8601 with the household UTC offset (from **Settings → General → Timezone**). Descriptions are truncated; lists are capped.

Time arguments (`since`, `window`) accept ISO 8601 (`2026-10-06T08:00:00-04:00`; no offset = household time) or `15m`, `1h`, `24h`, `7d`, `2w`, `today`, `yesterday`. `m` means minutes. Windows may not exceed 90 days.

| Tool | Arguments | Returns |
|------|-----------|---------|
| `recent_events` | `since` (default `1h`), `camera`, `limit` (1-100, default 20), `object_type` (`person`, `vehicle`, `package`, `animal`) | Newest-first events: time, camera, description, objects, identified people/vehicles, doorbell ring, carrier, incident id, signed thumbnail URL |
| `event_summary` | `window` (default `today`), `camera` | Headline, totals (by camera/object, doorbell rings, packages, alerts), named visitors, and incidents. Events on several cameras that ArgusAI correlated are one incident |
| `camera_status` | none | Each camera: `online`, `offline`, `disabled`, or `unknown` (with a reason), plus its last event |
| `package_status` | `since` (default `today`), `camera` | Package deliveries with carrier. Pickup is **best effort**: ArgusAI does not confirm pickups. `possibly_picked_up` means a later event on the same camera described something being picked up |
| `entity_sightings` | `name` (required), `since` (default `7d`), `limit` (1-50) | For named people/vehicles: first/last seen, total sightings, and sightings in the window. Suggests close names when nothing matches |

`camera` accepts a camera name (case-insensitive, partial match allowed) or id. An unknown camera returns an error that lists the camera names.

Example call and (shortened) result:

```json
{"jsonrpc": "2.0", "id": 2, "method": "tools/call",
 "params": {"name": "recent_events", "arguments": {"since": "1h"}}}
```

```json
{
  "window": {"start": "2026-10-06T12:30:00-04:00", "end": "2026-10-06T13:30:00-04:00",
             "label": "last 1h", "timezone": "America/New_York"},
  "count": 1,
  "truncated": false,
  "events": [{
    "id": "4c1f...",
    "time": "2026-10-06T13:20:41-04:00",
    "camera": "Front Door",
    "description": "A delivery driver in a brown uniform leaves a box on the porch.",
    "objects": ["person", "package"],
    "detection": "package",
    "carrier": "ups",
    "thumbnail_url": "https://argusai.example.com/api/v1/mcp/thumbnails/4c1f...?expires=1791311441&sig=..."
  }]
}
```

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `MCP_ENABLED` | `true` | `false` turns the endpoint (and thumbnail links) off with 404 |
| `MCP_RATE_LIMIT_PER_MINUTE` | `60` | Per-key ceiling for MCP requests |
| `MCP_THUMBNAIL_URL_TTL_SECONDS` | `600` | Lifetime of signed thumbnail links (30-3600) |
| `MCP_PUBLIC_BASE_URL` | unset | e.g. `https://argusai.example.com`. When unset, thumbnail URLs are relative paths (`/api/v1/mcp/thumbnails/...`) |

## Security

- **Read-only by construction.** The tool list has no write tools, and the handlers only run ORM `SELECT` queries in a short session that is rolled back.
- **Dedicated key.** `/api/v1/mcp` accepts API keys only (web sessions get `401`). The key must have `read:mcp` and must not have `admin` or any `write:` scope (`403`). A `read:mcp` key cannot call any other API route.
- **Bearer support is scoped.** `Authorization: Bearer argus_...` is read as an API key only on `/api/v1/mcp`; everywhere else a bearer token must be a session JWT.
- **Rate limited** per key, before the request body is read (`429` with `Retry-After`).
- **No raw media.** Results never include frames, clips, base64 images, or file paths. Thumbnails are reachable only through HMAC-SHA256 signed links bound to one event and expiring after `MCP_THUMBNAIL_URL_TTL_SECONDS`. The signing key is derived from `ENCRYPTION_KEY` and differs from the push-notification thumbnail signatures. Anyone holding a link can open that one thumbnail until it expires, so treat links like short-lived secrets.
- **Audit log.** Each tool call writes a `user_audit_logs` row with action `mcp_tool_call`: key id and prefix, tool name, a bounded argument summary, result count, outcome, and duration (never the key). A structured log line with `event_type: mcp_tool_call` is emitted too.
- **Input validation.** Every tool has a JSON Schema with `additionalProperties: false`, string length limits, and integer bounds. Errors return generic messages.
- **Privacy.** Results include names you assigned to people and vehicles, and AI descriptions. Only connect assistants you trust with that information, and revoke the key when you stop using it.
