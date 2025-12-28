# ArgusAI - Epic Breakdown

**Author:** Brent
**Date:** 2025-12-28
**Phase:** 13 - Platform Maturity & External Integration
**PRD Reference:** [PRD-phase13.md](./PRD-phase13.md)

---

## Overview

This document provides the complete epic and story breakdown for Phase 13, decomposing the requirements from the PRD into implementable stories.

**Living Document Notice:** This is the initial version. It will be updated after Architecture workflow adds technical details to stories.

### Epic Summary

| Epic | Title | Stories | Priority | FRs Covered |
|------|-------|---------|----------|-------------|
| P13-1 | API Key Management | 6 | P2 | FR1-FR10 |
| P13-2 | Cloud Relay | 5 | P3 | FR11-FR18 |
| P13-3 | Entity Reprocessing | 4 | P3 | FR19-FR26 |
| P13-4 | Branding | 3 | P3 | FR27-FR32 |
| P13-5 | n8n Development Pipeline | 5 | P2 | FR33-FR40 |

**Total: 5 Epics, 23 Stories**

---

## Functional Requirements Inventory

### API Key Management (FR1-FR10)
- FR1: Administrators can generate new API keys with a descriptive name
- FR2: API keys are displayed only once at creation time
- FR3: Administrators can view a list of all API keys
- FR4: Administrators can revoke API keys immediately
- FR5: API keys can be scoped to specific permissions
- FR6: External systems can authenticate using API keys
- FR7: API key usage is logged
- FR8: API keys can have optional expiration dates
- FR9: Rate limiting is applied per API key
- FR10: Revoked or expired API keys return 401 Unauthorized

### Cloud Relay (FR11-FR18)
- FR11: Users can configure Cloudflare Tunnel credentials
- FR12: System establishes secure tunnel connection on startup
- FR13: Remote clients can connect via tunnel URL
- FR14: WebSocket connections are relayed
- FR15: System falls back to local network when available
- FR16: Tunnel status is displayed in Settings
- FR17: Users can test tunnel connectivity
- FR18: Remote sessions use existing auth mechanisms

### Entity Reprocessing (FR19-FR26)
- FR19: Administrators can trigger bulk entity reprocessing
- FR20: Reprocessing accepts optional filters
- FR21: System displays estimated event count
- FR22: Reprocessing runs as background task
- FR23: Progress is reported via WebSocket
- FR24: Users can cancel in-progress reprocessing
- FR25: Reprocessing generates embeddings for events missing them
- FR26: Matched entities are updated in event records

### Branding (FR27-FR32)
- FR27: ArgusAI logo appears as favicon
- FR28: ArgusAI logo appears in PWA manifest icons
- FR29: ArgusAI logo appears in docs-site
- FR30: ArgusAI logo appears in Open Graph meta tags
- FR31: Apple touch icon uses ArgusAI logo
- FR32: Logo is consistent across light and dark themes

### n8n Pipeline (FR33-FR40)
- FR33: n8n instance can be deployed via Docker Compose
- FR34: n8n workflows can trigger BMAD create-story
- FR35: n8n workflows can trigger BMAD dev-story
- FR36: n8n workflows can trigger BMAD code-review
- FR37: n8n can receive GitHub webhook events
- FR38: n8n can send notifications to Slack or Discord
- FR39: n8n dashboard displays pipeline status
- FR40: Human approval gates can pause pipeline

---

## FR Coverage Map

| Epic | FRs Covered |
|------|-------------|
| P13-1: API Key Management | FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR8, FR9, FR10 |
| P13-2: Cloud Relay | FR11, FR12, FR13, FR14, FR15, FR16, FR17, FR18 |
| P13-3: Entity Reprocessing | FR19, FR20, FR21, FR22, FR23, FR24, FR25, FR26 |
| P13-4: Branding | FR27, FR28, FR29, FR30, FR31, FR32 |
| P13-5: n8n Pipeline | FR33, FR34, FR35, FR36, FR37, FR38, FR39, FR40 |

**Coverage: 40/40 FRs (100%)**

---

## Epic P13-1: API Key Management

**Goal:** Enable secure programmatic access to ArgusAI for third-party integrations, automation scripts, and external systems without exposing admin credentials.

**Backlog Reference:** FF-033

**Priority:** P2

---

### Story P13-1.1: Create APIKey Database Model and Migration

As an administrator,
I want API keys stored securely in the database,
So that they persist across server restarts and can be managed.

**Acceptance Criteria:**

**Given** the database schema needs to support API keys
**When** the migration is applied
**Then** an `api_keys` table exists with columns:
- `id` (UUID, primary key)
- `name` (string, max 100 chars, required)
- `key_hash` (string, bcrypt hash, required)
- `key_prefix` (string, first 8 chars of key, for identification)
- `scopes` (JSON array of permission strings)
- `created_at` (timestamp)
- `expires_at` (timestamp, nullable)
- `last_used_at` (timestamp, nullable)
- `revoked_at` (timestamp, nullable)
- `created_by_user_id` (foreign key to users)

**And** an `api_key_usage` table exists for audit logging:
- `id` (UUID)
- `api_key_id` (foreign key)
- `endpoint` (string)
- `method` (string)
- `ip_address` (string)
- `timestamp` (timestamp)
- `response_status` (integer)

**Prerequisites:** None (first story in epic)

**Technical Notes:**
- Use Alembic migration
- Index on `key_prefix` for fast lookups
- Index on `api_key_id` + `timestamp` for usage queries
- Model in `backend/app/models/api_key.py`

---

### Story P13-1.2: Implement API Key Generation Endpoint

As an administrator,
I want to generate new API keys via the API,
So that I can create keys for external systems.

**Acceptance Criteria:**

**Given** I am authenticated as an admin
**When** I POST to `/api/v1/api-keys` with:
```json
{
  "name": "Home Assistant Integration",
  "scopes": ["read:events", "read:cameras"],
  "expires_at": "2026-01-01T00:00:00Z"  // optional
}
```
**Then** a new API key is generated with format `ak_<32-random-chars>`
**And** the response includes the FULL key (only time it's shown):
```json
{
  "id": "uuid",
  "name": "Home Assistant Integration",
  "key": "ak_abc123...",  // ONLY returned on creation
  "key_prefix": "ak_abc12",
  "scopes": ["read:events", "read:cameras"],
  "created_at": "2025-12-28T...",
  "expires_at": "2026-01-01T00:00:00Z"
}
```
**And** the key is hashed with bcrypt before storage
**And** response status is 201 Created

**Given** name is missing or empty
**When** I POST to `/api/v1/api-keys`
**Then** response is 400 Bad Request with validation error

**Given** I am not authenticated
**When** I POST to `/api/v1/api-keys`
**Then** response is 401 Unauthorized

**Prerequisites:** P13-1.1

**Technical Notes:**
- Use `secrets.token_urlsafe(24)` for key generation
- Prefix with `ak_` for easy identification
- Hash with bcrypt (cost factor 12)
- Router in `backend/app/api/v1/api_keys.py`
- Valid scopes: `read:events`, `read:cameras`, `write:cameras`, `read:entities`, `write:entities`, `admin`

---

### Story P13-1.3: Implement API Key List and Revoke Endpoints

As an administrator,
I want to view and revoke API keys,
So that I can manage access to the system.

**Acceptance Criteria:**

**Given** I am authenticated as an admin
**When** I GET `/api/v1/api-keys`
**Then** I receive a list of all API keys (without full key values):
```json
[
  {
    "id": "uuid",
    "name": "Home Assistant",
    "key_prefix": "ak_abc12",
    "scopes": ["read:events"],
    "created_at": "...",
    "expires_at": null,
    "last_used_at": "...",
    "revoked": false
  }
]
```

**Given** I am authenticated as an admin
**When** I DELETE `/api/v1/api-keys/{id}`
**Then** the API key is marked as revoked (soft delete)
**And** `revoked_at` timestamp is set
**And** response is 204 No Content

**Given** the API key ID doesn't exist
**When** I DELETE `/api/v1/api-keys/{id}`
**Then** response is 404 Not Found

**Prerequisites:** P13-1.2

**Technical Notes:**
- Never return full key in list response
- Soft delete allows audit trail preservation
- Add `is_active` computed property: not revoked and not expired

---

### Story P13-1.4: Implement API Key Authentication Middleware

As an external system,
I want to authenticate using an API key,
So that I can access ArgusAI programmatically.

**Acceptance Criteria:**

**Given** I have a valid API key
**When** I make a request with header `Authorization: Bearer ak_abc123...`
**Then** the request is authenticated
**And** `last_used_at` is updated on the API key

**Given** I have a revoked API key
**When** I make a request with that key
**Then** response is 401 Unauthorized with message "API key revoked"

**Given** I have an expired API key
**When** I make a request with that key
**Then** response is 401 Unauthorized with message "API key expired"

**Given** I have an API key with limited scopes
**When** I access an endpoint requiring a scope I don't have
**Then** response is 403 Forbidden with message "Insufficient permissions"

**Given** the API key doesn't exist
**When** I make a request with that key
**Then** response is 401 Unauthorized

**And** authentication adds <10ms latency (NFR8)

**Prerequisites:** P13-1.3

**Technical Notes:**
- Create `APIKeyAuth` dependency in `backend/app/api/deps.py`
- Check `Authorization` header for `Bearer ak_` prefix
- Extract key, hash it, lookup by hash
- Cache valid keys for 60 seconds to reduce DB lookups
- Log usage to `api_key_usage` table asynchronously

---

### Story P13-1.5: Implement API Key Rate Limiting

As a system administrator,
I want rate limiting per API key,
So that no single integration can overwhelm the system.

**Acceptance Criteria:**

**Given** an API key has made 100 requests in the last minute
**When** it makes another request
**Then** response is 429 Too Many Requests
**And** response includes `Retry-After` header

**Given** rate limit is hit
**When** I check the response headers
**Then** I see:
- `X-RateLimit-Limit: 100`
- `X-RateLimit-Remaining: 0`
- `X-RateLimit-Reset: <timestamp>`

**Given** a minute has passed since rate limit was hit
**When** the API key makes a new request
**Then** the request succeeds

**Prerequisites:** P13-1.4

**Technical Notes:**
- Use sliding window rate limiting
- Store counters in memory (or Redis if available)
- Default: 100 requests/minute per key
- Consider making limit configurable per key in future

---

### Story P13-1.6: Create API Keys Settings UI

As an administrator,
I want to manage API keys through the web interface,
So that I don't need to use the API directly.

**Acceptance Criteria:**

**Given** I navigate to Settings > API Keys
**When** the page loads
**Then** I see a list of existing API keys with:
- Name
- Key prefix (e.g., "ak_abc12...")
- Scopes (as badges)
- Created date
- Last used date
- Status (Active/Revoked/Expired)
- Revoke button

**Given** I click "Create API Key"
**When** a modal opens
**Then** I can enter:
- Name (required, text input)
- Scopes (multi-select checkboxes)
- Expiration (optional date picker)

**Given** I submit the create form
**When** the key is created
**Then** a modal shows the FULL API key with:
- Copy button
- Warning that this is the only time the key will be shown
- "I've copied my key" confirmation button

**Given** I click Revoke on an active key
**When** confirmation dialog appears and I confirm
**Then** the key is revoked and shows as "Revoked" in the list

**Prerequisites:** P13-1.3

**Technical Notes:**
- New page: `frontend/app/settings/api-keys/page.tsx`
- Use existing shadcn/ui components (Dialog, Button, Badge, Table)
- Add to settings navigation sidebar
- Copy functionality using `navigator.clipboard.writeText()`

---

## Epic P13-2: Cloud Relay

**Goal:** Enable secure remote access to ArgusAI from anywhere without port forwarding or VPN, using Cloudflare Tunnel.

**Backlog Reference:** FF-025

**Priority:** P3

---

### Story P13-2.1: Add Tunnel Configuration to Settings

As a user,
I want to configure Cloudflare Tunnel credentials in Settings,
So that I can enable remote access.

**Acceptance Criteria:**

**Given** I navigate to Settings > Remote Access (new section)
**When** the page loads
**Then** I see:
- Enable Remote Access toggle
- Tunnel Token input field (password type, masked)
- Tunnel URL display (read-only, shown when connected)
- Connection status indicator
- Save button

**Given** I enter a valid tunnel token and enable remote access
**When** I click Save
**Then** the token is stored encrypted (Fernet)
**And** the system attempts to establish tunnel connection
**And** status updates to show connection state

**Given** I disable remote access
**When** I click Save
**Then** the tunnel connection is terminated
**And** status shows "Disabled"

**Prerequisites:** None (first story in epic)

**Technical Notes:**
- Store tunnel token in SystemSettings table (encrypted)
- New settings section in `frontend/app/settings/remote-access/page.tsx`
- Backend config in `backend/app/core/config.py`
- Reference existing Cloudflare Tunnel docs

---

### Story P13-2.2: Implement Cloudflare Tunnel Service

As the system,
I want to establish and maintain a Cloudflare Tunnel connection,
So that remote clients can connect to ArgusAI.

**Acceptance Criteria:**

**Given** remote access is enabled with a valid tunnel token
**When** the backend starts
**Then** the cloudflared tunnel process is spawned
**And** connection is established within 30 seconds
**And** tunnel URL is logged and stored

**Given** the tunnel connection drops
**When** network is restored
**Then** the connection automatically reconnects (NFR13)
**And** reconnection attempts use exponential backoff

**Given** an invalid tunnel token is configured
**When** connection is attempted
**Then** error is logged with clear message
**And** status shows "Authentication Failed"

**Given** remote access is disabled
**When** the setting is changed
**Then** cloudflared process is gracefully terminated

**Prerequisites:** P13-2.1

**Technical Notes:**
- Service in `backend/app/services/tunnel_service.py`
- Use subprocess to manage cloudflared
- Parse cloudflared output for tunnel URL
- Health check via periodic connection test
- Consider Docker sidecar pattern for containerized deployments

---

### Story P13-2.3: Add Tunnel Status Endpoint

As a user or monitoring system,
I want to check tunnel status via API,
So that I can verify remote access is working.

**Acceptance Criteria:**

**Given** remote access is enabled and connected
**When** I GET `/api/v1/system/tunnel-status`
**Then** I receive:
```json
{
  "enabled": true,
  "status": "connected",
  "tunnel_url": "https://argus-abc123.trycloudflare.com",
  "connected_since": "2025-12-28T10:00:00Z",
  "last_health_check": "2025-12-28T12:00:00Z"
}
```

**Given** remote access is disabled
**When** I GET `/api/v1/system/tunnel-status`
**Then** I receive:
```json
{
  "enabled": false,
  "status": "disabled",
  "tunnel_url": null
}
```

**Given** tunnel is enabled but connection failed
**When** I GET `/api/v1/system/tunnel-status`
**Then** status is "error" with error message

**Prerequisites:** P13-2.2

**Technical Notes:**
- Endpoint in `backend/app/api/v1/system.py`
- Include error details if connection failed

---

### Story P13-2.4: Implement Tunnel Connectivity Test

As a user,
I want to test tunnel connectivity from Settings,
So that I can verify remote access works before relying on it.

**Acceptance Criteria:**

**Given** remote access is enabled and connected
**When** I click "Test Connection" in Settings
**Then** the system makes an HTTP request through the tunnel to itself
**And** displays "Connection successful - <latency>ms" on success
**And** displays error message on failure

**Given** I POST to `/api/v1/system/tunnel/test`
**When** the tunnel is connected
**Then** response includes:
```json
{
  "success": true,
  "latency_ms": 145,
  "tested_at": "2025-12-28T12:00:00Z"
}
```

**Prerequisites:** P13-2.3

**Technical Notes:**
- Test by making request to tunnel URL and checking response
- Measure round-trip latency
- Timeout after 10 seconds

---

### Story P13-2.5: WebSocket Relay Support

As a remote user,
I want real-time event updates when connected via tunnel,
So that I have the same experience as local access.

**Acceptance Criteria:**

**Given** I am connected via the tunnel URL
**When** I establish a WebSocket connection
**Then** the connection is successfully relayed
**And** I receive real-time event updates

**Given** a new event occurs
**When** I am connected via tunnel WebSocket
**Then** I receive the event notification with <500ms additional latency (NFR9)

**Given** the tunnel reconnects after a drop
**When** I have an active WebSocket
**Then** the WebSocket automatically reconnects

**Prerequisites:** P13-2.2

**Technical Notes:**
- Cloudflare Tunnel natively supports WebSocket
- May need to verify existing WebSocket code works through tunnel
- Add reconnection logic to frontend WebSocket client if not present

---

## Epic P13-3: Entity Reprocessing

**Goal:** Allow bulk reprocessing of historical events to improve entity matching after system improvements or new entity creation.

**Backlog Reference:** FF-034

**Priority:** P3

---

### Story P13-3.1: Create Reprocessing Background Task

As the system,
I want to reprocess events for entity matching in the background,
So that the UI remains responsive during long operations.

**Acceptance Criteria:**

**Given** a reprocessing job is started
**When** events are being processed
**Then** processing happens in a background task
**And** the API returns immediately with job ID
**And** processing handles 100 events/second minimum (NFR10)

**Given** an event is missing an embedding
**When** it is reprocessed
**Then** an embedding is generated from the thumbnail

**Given** an event is processed
**When** entity matching runs
**Then** `matched_entity_ids` is updated if matches found
**And** EntityEvent junction records are created

**Given** the server restarts during reprocessing
**When** it comes back up
**Then** processing can resume from last checkpoint (NFR14)

**Prerequisites:** None (first story in epic)

**Technical Notes:**
- Background task using existing asyncio pattern
- Store progress in database: `reprocessing_jobs` table
- Process in batches of 100 events
- Use existing `match_or_create_entity()` function
- Track: total_events, processed, matched, errors

---

### Story P13-3.2: Implement Reprocessing API Endpoints

As an administrator,
I want to start, monitor, and cancel reprocessing via API,
So that I can manage the operation programmatically.

**Acceptance Criteria:**

**Given** I POST to `/api/v1/events/reprocess-entities` with optional filters:
```json
{
  "start_date": "2025-12-01",
  "end_date": "2025-12-28",
  "camera_id": "uuid",  // optional
  "only_unmatched": true  // optional, default true
}
```
**When** I am authenticated as admin
**Then** a reprocessing job is created
**And** response includes:
```json
{
  "job_id": "uuid",
  "status": "running",
  "total_events": 1500,
  "processed": 0,
  "matched": 0,
  "errors": 0,
  "started_at": "..."
}
```

**Given** a job is running
**When** I GET `/api/v1/events/reprocess-entities`
**Then** I receive current job status with progress

**Given** a job is running
**When** I DELETE `/api/v1/events/reprocess-entities`
**Then** the job is cancelled gracefully
**And** status becomes "cancelled"

**Prerequisites:** P13-3.1

**Technical Notes:**
- Only one reprocessing job can run at a time
- Return 409 Conflict if job already running
- Endpoint in `backend/app/api/v1/events.py`

---

### Story P13-3.3: Add WebSocket Progress Updates

As a user watching the reprocessing UI,
I want real-time progress updates,
So that I can see how the operation is progressing.

**Acceptance Criteria:**

**Given** a reprocessing job is running
**When** progress changes
**Then** WebSocket message is sent:
```json
{
  "type": "reprocessing_progress",
  "job_id": "uuid",
  "processed": 500,
  "total": 1500,
  "matched": 45,
  "errors": 2,
  "percent_complete": 33.3
}
```

**And** updates are sent every 1 second or 100 events (NFR11)

**Given** the job completes
**When** all events are processed
**Then** a completion message is sent:
```json
{
  "type": "reprocessing_complete",
  "job_id": "uuid",
  "total_processed": 1500,
  "total_matched": 120,
  "total_errors": 5,
  "duration_seconds": 15
}
```

**Prerequisites:** P13-3.2

**Technical Notes:**
- Use existing WebSocket broadcast infrastructure
- Throttle updates to avoid flooding clients

---

### Story P13-3.4: Create Reprocessing UI

As an administrator,
I want to trigger and monitor reprocessing from the UI,
So that I don't need to use the API directly.

**Acceptance Criteria:**

**Given** I navigate to Settings > Entities (or Events page)
**When** I click "Reprocess Entity Matching"
**Then** a modal opens with filter options:
- Date range picker
- Camera dropdown (optional)
- "Only events without entities" checkbox (default: checked)
- Estimated event count displayed

**Given** I configure filters and click "Start Reprocessing"
**When** confirmation dialog appears and I confirm
**Then** the job starts
**And** the modal shows progress:
- Progress bar with percentage
- Events processed / total
- Entities matched count
- Errors count
- Cancel button

**Given** I click Cancel during processing
**When** confirmation appears and I confirm
**Then** the job is cancelled
**And** partial results are preserved

**Prerequisites:** P13-3.3

**Technical Notes:**
- Add button to Settings > Entities section
- Use WebSocket for live progress updates
- Disable button if job already running

---

## Epic P13-4: Branding

**Goal:** Establish consistent ArgusAI visual identity across all platforms and touchpoints.

**Backlog Reference:** IMP-039

**Priority:** P3

---

### Story P13-4.1: Export Logo Assets in Required Sizes

As a developer,
I want logo assets exported in all required sizes,
So that they can be used across different platforms.

**Acceptance Criteria:**

**Given** the source logo in `graphics/` directory
**When** assets are exported
**Then** the following files exist in `frontend/public/`:
- `favicon.ico` (16x16, 32x32, 48x48 multi-size)
- `favicon-16x16.png`
- `favicon-32x32.png`
- `apple-touch-icon.png` (180x180)
- `android-chrome-192x192.png`
- `android-chrome-512x512.png`
- `mstile-150x150.png`
- `og-image.png` (1200x630 for social sharing)

**And** the following files exist in `docs-site/static/img/`:
- `logo.svg` (vector)
- `favicon.ico`
- `docusaurus-social-card.png` (1200x630)

**Prerequisites:** None (first story in epic)

**Technical Notes:**
- Source: `graphics/argusai-image.*`
- Use image processing tool (ImageMagick, Sharp, or online tool)
- Ensure transparency is preserved where appropriate
- Optimize PNG files for web

---

### Story P13-4.2: Update Frontend Branding

As a user,
I want to see the ArgusAI logo throughout the web application,
So that the app has a professional, branded appearance.

**Acceptance Criteria:**

**Given** I visit the ArgusAI web app
**When** the page loads
**Then** the favicon shows the ArgusAI logo
**And** the browser tab shows the logo

**Given** I install the PWA
**When** I view the app icon
**Then** it shows the ArgusAI logo in correct size

**Given** I view the sidebar/header
**When** the app loads
**Then** the ArgusAI logo appears in the navigation

**Given** I share a link to ArgusAI on social media
**When** the preview generates
**Then** it shows the ArgusAI Open Graph image

**Prerequisites:** P13-4.1

**Technical Notes:**
- Update `frontend/app/layout.tsx` metadata
- Update `frontend/public/manifest.json` icons
- Update sidebar component with logo
- Add Open Graph meta tags

---

### Story P13-4.3: Update Docs Site Branding

As a visitor to the documentation site,
I want to see consistent ArgusAI branding,
So that it matches the main application.

**Acceptance Criteria:**

**Given** I visit the GitHub Pages docs site
**When** the page loads
**Then** the favicon shows the ArgusAI logo
**And** the header shows the ArgusAI logo

**Given** I share a docs link on social media
**When** the preview generates
**Then** it shows the ArgusAI social card image

**Given** I view the docs in light or dark mode
**When** switching themes
**Then** the logo remains visible and appropriate for each theme

**Prerequisites:** P13-4.1

**Technical Notes:**
- Update `docs-site/docusaurus.config.js` with logo paths
- Update `docs-site/static/img/` with assets
- May need light and dark logo variants

---

## Epic P13-5: n8n Development Pipeline

**Goal:** Accelerate development with AI-assisted automation using n8n workflows integrated with BMAD methodology.

**Backlog Reference:** FF-027

**Priority:** P2

---

### Story P13-5.1: Create n8n Docker Compose Configuration

As a developer,
I want to deploy n8n alongside ArgusAI,
So that I have an automation platform for development workflows.

**Acceptance Criteria:**

**Given** the docker-compose.yml file
**When** I run `docker-compose up n8n`
**Then** n8n starts and is accessible at `http://localhost:5678`
**And** n8n data persists in a volume

**Given** n8n is running
**When** I access the web UI
**Then** I can log in and create workflows

**Prerequisites:** None (first story in epic)

**Technical Notes:**
- Add n8n service to existing `docker-compose.yml`
- Mount volume for `/home/node/.n8n`
- Environment variables for initial admin credentials
- Document setup in README or dedicated docs

---

### Story P13-5.2: Create GitHub Webhook Integration Workflow

As an automation,
I want to receive GitHub events in n8n,
So that I can trigger development workflows automatically.

**Acceptance Criteria:**

**Given** a GitHub webhook is configured for the repo
**When** a push event occurs
**Then** n8n receives the webhook payload
**And** the workflow can parse commit info, branch, and changed files

**Given** a pull request is opened
**When** the webhook fires
**Then** n8n receives the event
**And** can extract PR title, description, and changed files

**Given** an issue is created with specific labels
**When** the webhook fires
**Then** n8n can filter by label and trigger appropriate workflows

**Prerequisites:** P13-5.1

**Technical Notes:**
- Export workflow JSON to `n8n-workflows/github-webhook.json`
- Document webhook URL setup in GitHub
- Include example payload parsing nodes

---

### Story P13-5.3: Create BMAD Workflow Integration

As an automation,
I want to trigger BMAD workflows from n8n,
So that story creation and development can be automated.

**Acceptance Criteria:**

**Given** an n8n workflow with Claude Code integration
**When** triggered with a story request
**Then** it executes `claude-code /bmad:bmm:workflows:create-story`
**And** captures the output

**Given** a story is created
**When** dev-story workflow is triggered
**Then** it executes `claude-code /bmad:bmm:workflows:dev-story`
**And** monitors for completion

**Given** development completes
**When** code-review workflow is triggered
**Then** it executes `claude-code /bmad:bmm:workflows:code-review`
**And** captures review results

**Prerequisites:** P13-5.2

**Technical Notes:**
- Use Execute Command node to run Claude Code CLI
- Capture stdout/stderr for logging
- Handle timeout (30 seconds for story creation - NFR12)
- Parse output for success/failure

---

### Story P13-5.4: Create Notification Workflow

As a developer,
I want notifications when pipeline events occur,
So that I stay informed without watching the dashboard.

**Acceptance Criteria:**

**Given** a BMAD workflow completes successfully
**When** the notification node executes
**Then** a Slack/Discord message is sent with:
- Workflow name
- Status (success/failure)
- Duration
- Link to details

**Given** a workflow fails
**When** the error is detected
**Then** a notification is sent with error details
**And** the message is formatted for easy reading

**Given** a human approval is required
**When** the workflow pauses
**Then** a notification is sent with approve/reject buttons (if supported)

**Prerequisites:** P13-5.3

**Technical Notes:**
- Support both Slack and Discord via n8n nodes
- Use webhook URLs stored as n8n credentials
- Include workflow ID for tracking

---

### Story P13-5.5: Create Pipeline Dashboard View

As a developer,
I want to see pipeline status in n8n,
So that I can monitor ongoing workflows.

**Acceptance Criteria:**

**Given** I access the n8n dashboard
**When** workflows have executed
**Then** I can see:
- Recent workflow executions
- Success/failure status
- Execution duration
- Error messages for failures

**Given** a workflow is running
**When** I view the execution
**Then** I can see real-time progress through nodes

**Given** I want to manually trigger a workflow
**When** I click the play button
**Then** I can provide input parameters and start execution

**Prerequisites:** P13-5.3

**Technical Notes:**
- This is native n8n functionality
- Document how to access and use the dashboard
- Create a "getting started" guide for the dev pipeline

---

## FR Coverage Matrix

| FR | Description | Epic | Story |
|----|-------------|------|-------|
| FR1 | Generate API keys with name | P13-1 | P13-1.2 |
| FR2 | Display key only once | P13-1 | P13-1.2, P13-1.6 |
| FR3 | List API keys | P13-1 | P13-1.3, P13-1.6 |
| FR4 | Revoke API keys | P13-1 | P13-1.3, P13-1.6 |
| FR5 | Scoped permissions | P13-1 | P13-1.2, P13-1.4 |
| FR6 | API key authentication | P13-1 | P13-1.4 |
| FR7 | Usage logging | P13-1 | P13-1.4 |
| FR8 | Expiration dates | P13-1 | P13-1.2 |
| FR9 | Rate limiting | P13-1 | P13-1.5 |
| FR10 | 401 for revoked/expired | P13-1 | P13-1.4 |
| FR11 | Configure tunnel credentials | P13-2 | P13-2.1 |
| FR12 | Establish tunnel on startup | P13-2 | P13-2.2 |
| FR13 | Remote client connection | P13-2 | P13-2.2 |
| FR14 | WebSocket relay | P13-2 | P13-2.5 |
| FR15 | Local network fallback | P13-2 | P13-2.2 |
| FR16 | Tunnel status display | P13-2 | P13-2.1, P13-2.3 |
| FR17 | Test connectivity | P13-2 | P13-2.4 |
| FR18 | Existing auth for remote | P13-2 | P13-2.2 |
| FR19 | Trigger bulk reprocessing | P13-3 | P13-3.2, P13-3.4 |
| FR20 | Reprocessing filters | P13-3 | P13-3.2, P13-3.4 |
| FR21 | Estimated event count | P13-3 | P13-3.4 |
| FR22 | Background task | P13-3 | P13-3.1 |
| FR23 | WebSocket progress | P13-3 | P13-3.3 |
| FR24 | Cancel reprocessing | P13-3 | P13-3.2, P13-3.4 |
| FR25 | Generate missing embeddings | P13-3 | P13-3.1 |
| FR26 | Update matched entities | P13-3 | P13-3.1 |
| FR27 | Favicon | P13-4 | P13-4.2 |
| FR28 | PWA icons | P13-4 | P13-4.2 |
| FR29 | Docs-site branding | P13-4 | P13-4.3 |
| FR30 | Open Graph images | P13-4 | P13-4.2, P13-4.3 |
| FR31 | Apple touch icon | P13-4 | P13-4.2 |
| FR32 | Light/dark theme logo | P13-4 | P13-4.3 |
| FR33 | n8n Docker deployment | P13-5 | P13-5.1 |
| FR34 | Trigger create-story | P13-5 | P13-5.3 |
| FR35 | Trigger dev-story | P13-5 | P13-5.3 |
| FR36 | Trigger code-review | P13-5 | P13-5.3 |
| FR37 | GitHub webhooks | P13-5 | P13-5.2 |
| FR38 | Slack/Discord notifications | P13-5 | P13-5.4 |
| FR39 | Pipeline dashboard | P13-5 | P13-5.5 |
| FR40 | Human approval gates | P13-5 | P13-5.4 |

**Coverage: 40/40 FRs (100%)**

---

## Summary

Phase 13 epic breakdown is complete with:

| Metric | Value |
|--------|-------|
| Total Epics | 5 |
| Total Stories | 23 |
| FRs Covered | 40/40 (100%) |
| NFRs Referenced | 14 |

### Implementation Order (Recommended)

1. **P13-4: Branding** (3 stories) - Quick win, visual impact
2. **P13-1: API Key Management** (6 stories) - Core infrastructure
3. **P13-3: Entity Reprocessing** (4 stories) - Data quality
4. **P13-2: Cloud Relay** (5 stories) - Builds on P13-1 for auth
5. **P13-5: n8n Pipeline** (5 stories) - Development tooling

### Dependencies

```
P13-4 (Branding) ──────────────────────────────────────► Independent
P13-1 (API Keys) ──────────────────────────────────────► Independent
P13-3 (Reprocessing) ──────────────────────────────────► Independent
P13-2 (Cloud Relay) ───────► Depends on P13-1 (API Key Auth)
P13-5 (n8n) ───────────────────────────────────────────► Independent
```

---

_For implementation: Use the `create-story` workflow to generate individual story implementation plans from this epic breakdown._

_This document will be updated after Architecture workflow to incorporate technical decisions._
