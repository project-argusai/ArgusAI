# Live Object AI Classifier Phase 2 - Epic Breakdown

**Author:** Brent
**Date:** 2025-11-30
**Project Level:** Feature Enhancement (Phase 2)
**Target Scale:** Existing MVP users + UniFi Protect ecosystem users

---

## Overview

This document provides the complete epic and story breakdown for Phase 2 of Live Object AI Classifier, decomposing the requirements from [PRD-phase2.md](./PRD-phase2.md) into implementable stories.

**Phase 2 Focus:**
1. **Primary:** UniFi Protect Native Integration - Real-time WebSocket events, camera auto-discovery, smart detection filtering
2. **Secondary:** xAI Grok AI Provider - Additional vision-capable AI provider option

**Living Document Notice:** This is the initial version created from PRD-phase2.md. UX Design (Section 10) and Architecture (Phase 2 Additions) have already been completed, so stories include those details.

### Epic Summary

**6 Epics organized by feature delivery and technical dependencies:**

| Epic | Name | FRs Covered | Stories | Focus |
|------|------|-------------|---------|-------|
| 1 | UniFi Protect Controller Integration | FR1-FR7, FR14-FR15 | 5 | Foundation for Protect integration |
| 2 | Camera Discovery & Configuration | FR8-FR13 | 4 | Auto-discovery and camera setup |
| 3 | Real-Time Event Processing | FR16-FR20 | 4 | Event pipeline from Protect to AI |
| 4 | Doorbell & Multi-Camera Features | FR21-FR26 | 4 | Advanced event handling |
| 5 | xAI Grok Provider | FR27-FR31 | 3 | New AI provider integration |
| 6 | Coexistence & Polish | FR32-FR36, NFRs | 4 | Unified experience, testing |

**Total: 24 Stories across 6 Epics**

---

## Functional Requirements Inventory

**UniFi Protect Controller Management (7 FRs)**
- FR1: Users can add a UniFi Protect controller by providing hostname/IP and credentials
- FR2: System validates controller connection and authentication before saving
- FR3: System stores controller credentials encrypted using existing Fernet encryption
- FR4: Users can edit controller connection settings
- FR5: Users can remove a controller (with confirmation)
- FR6: Users can test controller connectivity from the UI
- FR7: System displays controller connection status (connected/disconnected/error)

**Camera Discovery & Selection (6 FRs)**
- FR8: System auto-discovers all cameras from connected UniFi Protect controller
- FR9: Users can view list of discovered cameras with names and types
- FR10: Users can enable or disable individual cameras for AI analysis
- FR11: Users can configure event type filters per camera (Person/Vehicle/Package/Animal/All Motion)
- FR12: System distinguishes camera types (standard camera vs doorbell)
- FR13: Camera enable/disable and filter settings persist across restarts

**Real-Time Event Processing (7 FRs)**
- FR14: System maintains WebSocket connection to UniFi Protect controller
- FR15: System automatically reconnects WebSocket on connection loss (exponential backoff)
- FR16: System receives real-time motion/smart detection events via WebSocket
- FR17: System filters events based on per-camera event type configuration
- FR18: System fetches snapshot from Protect API when event passes filters
- FR19: System submits snapshot to AI provider for description generation
- FR20: System stores event with AI description in existing event system

**Doorbell Integration (3 FRs)**
- FR21: System detects doorbell ring events from UniFi Protect
- FR22: System generates "doorbell ring" notification distinct from motion events
- FR23: Doorbell events trigger AI analysis of who is at the door

**Multi-Camera Correlation (3 FRs)**
- FR24: System detects when multiple cameras capture the same event (time-window based)
- FR25: System links correlated events together in the event record
- FR26: Dashboard displays correlated events as related

**xAI Grok AI Provider (5 FRs)**
- FR27: Users can add xAI Grok as an AI provider with API key
- FR28: System validates Grok API key on save
- FR29: Users can configure Grok's position in the AI provider fallback chain
- FR30: System can send images to Grok API for vision-based description
- FR31: Grok provider follows same interface as existing providers (OpenAI/Claude/Gemini)

**Coexistence & Unified Experience (5 FRs)**
- FR32: UniFi Protect cameras and RTSP/USB cameras can operate simultaneously
- FR33: All camera types feed events into the same unified event pipeline
- FR34: Dashboard displays events from all camera sources in single timeline
- FR35: Alert rules apply equally to events from any camera source
- FR36: Users can identify camera source type in event details

---

## FR Coverage Map

**Epic 1 (Controller Integration):** FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR14, FR15
- FR1-FR7: Controller CRUD and status management
- FR14-FR15: WebSocket connection foundation

**Epic 2 (Camera Discovery):** FR8, FR9, FR10, FR11, FR12, FR13
- FR8-FR9: Auto-discovery and display
- FR10-FR13: Camera configuration and persistence

**Epic 3 (Real-Time Events):** FR16, FR17, FR18, FR19, FR20
- FR16-FR17: Event reception and filtering
- FR18-FR20: Snapshot retrieval and AI processing

**Epic 4 (Doorbell & Correlation):** FR21, FR22, FR23, FR24, FR25, FR26
- FR21-FR23: Doorbell-specific handling
- FR24-FR26: Multi-camera correlation

**Epic 5 (xAI Grok):** FR27, FR28, FR29, FR30, FR31
- FR27-FR29: Provider configuration
- FR30-FR31: Vision API integration

**Epic 6 (Coexistence):** FR32, FR33, FR34, FR35, FR36, NFR1-NFR16
- FR32-FR36: Unified experience
- NFRs: Performance, reliability, security validation

---

## Epic 1: UniFi Protect Controller Integration

**Goal:** Establish the foundation for UniFi Protect integration by enabling users to connect their Protect controller and maintaining a persistent WebSocket connection for real-time events.

**Value:** Users can connect their UniFi Protect system once and have it "just work" - no manual RTSP configuration needed.

---

### Story 1.1: Create Protect Controller Database Model and API Endpoints

**As a** backend developer,
**I want** database models and API endpoints for Protect controller management,
**So that** the system can store and manage controller connection settings.

**Acceptance Criteria:**

**Given** the backend database needs to support Protect controllers
**When** I run database migrations
**Then** the `protect_controllers` table is created with columns:
- `id` (TEXT PRIMARY KEY) - UUID format
- `name` (TEXT NOT NULL) - User-friendly name, max 100 chars
- `host` (TEXT NOT NULL) - IP address or hostname
- `port` (INTEGER DEFAULT 443) - HTTPS port
- `username` (TEXT NOT NULL) - Protect username
- `password` (TEXT NOT NULL) - Encrypted with Fernet
- `verify_ssl` (BOOLEAN DEFAULT FALSE) - SSL verification toggle
- `is_connected` (BOOLEAN DEFAULT FALSE) - Current connection status
- `last_connected_at` (TIMESTAMP) - Last successful connection
- `last_error` (TEXT) - Last error message
- `created_at` (TIMESTAMP) - Creation timestamp
- `updated_at` (TIMESTAMP) - Last update timestamp

**And** the `cameras` table is extended with:
- `source_type` (TEXT DEFAULT 'rtsp') - Values: 'rtsp', 'usb', 'protect'
- `protect_controller_id` (TEXT FK) - References protect_controllers.id
- `protect_camera_id` (TEXT) - Native Protect camera ID
- `protect_camera_type` (TEXT) - 'camera' or 'doorbell'
- `smart_detection_types` (TEXT) - JSON array of enabled types
- `is_doorbell` (BOOLEAN DEFAULT FALSE)

**And** API endpoints are created at `/api/v1/protect`:
- `POST /protect/controllers` - Create controller (validates before saving)
- `GET /protect/controllers` - List all controllers
- `GET /protect/controllers/{id}` - Get single controller
- `PUT /protect/controllers/{id}` - Update controller
- `DELETE /protect/controllers/{id}` - Delete controller (with cascade)

**And** all endpoints return consistent `{ data, meta }` response format

**Prerequisites:** None (first Phase 2 story)

**Technical Notes:**
- Use SQLAlchemy model in `backend/app/models/protect_controller.py`
- Create Alembic migration for schema changes
- Pydantic schemas in `backend/app/schemas/protect.py`
- Router in `backend/app/api/v1/protect.py`
- Password encryption uses existing `backend/app/utils/encryption.py`
- Add index on `cameras.protect_camera_id` for lookups

---

### Story 1.2: Implement Controller Connection Validation and Test Endpoint

**As a** user,
**I want** to test my Protect controller connection before saving,
**So that** I can verify credentials are correct and the controller is reachable.

**Acceptance Criteria:**

**Given** I have entered controller hostname and credentials
**When** I click "Test Connection" in the UI
**Then** the system attempts to connect to the Protect controller using `uiprotect` library

**And** if connection succeeds:
- Response includes: `{ success: true, message: "Connected successfully", firmware_version: "3.x.x", camera_count: 6 }`
- Connection is closed after test (not persisted)

**And** if connection fails:
- Response includes: `{ success: false, message: "Authentication failed" }` or appropriate error
- Specific error messages for: invalid credentials, host unreachable, SSL error, timeout

**And** API endpoint `POST /protect/controllers/{id}/test` or `POST /protect/controllers/test` (for unsaved):
- Accepts: `{ host, port, username, password, verify_ssl }`
- Timeout: 10 seconds maximum
- Does not save credentials on test-only requests

**And** NFR3 is met: Connection test completes within 10 seconds

**Prerequisites:** Story 1.1 (database model and endpoints)

**Technical Notes:**
- Use `uiprotect` library: `from uiprotect import ProtectApiClient`
- Async connection: `await client.connect()`
- Handle exceptions: `AuthError`, `ConnectionError`, `TimeoutError`
- Log connection attempts (without credentials)
- Create `backend/app/services/protect_service.py` with `test_connection()` method

---

### Story 1.3: Build Controller Configuration UI in Settings Page

**As a** user,
**I want** a form in Settings to add and configure my UniFi Protect controller,
**So that** I can connect my Protect system through the dashboard.

**Acceptance Criteria:**

**Given** I navigate to Settings page
**When** I click on "UniFi Protect" section/tab
**Then** I see the UniFi Protect configuration area

**And** if no controller is configured:
- Empty state message: "Connect your UniFi Protect controller to auto-discover cameras"
- "Add Controller" button prominently displayed

**And** the controller form includes:
- Name field (text input, placeholder: "Home UDM Pro", required)
- Host/IP field (text input, placeholder: "192.168.1.1 or unifi.local", required)
- Username field (text input, required)
- Password field (password input, required)
- Verify SSL checkbox (default: unchecked, helper text: "Enable for controllers with valid SSL certificates")

**And** form buttons:
- "Test Connection" button (accent color, triggers validation)
- "Save" button (primary color, disabled until form valid)
- "Cancel" button (secondary, only shown when editing)

**And** connection status indicator shows:
- Green dot + "Connected" when connected
- Yellow dot + "Connecting..." with spinner during connection
- Red dot + "Connection Error" with error details tooltip when failed
- Gray dot + "Not configured" when no controller saved

**And** form validation:
- Host: Required, valid hostname or IP format
- Username: Required, min 1 character
- Password: Required, min 1 character
- Real-time validation on blur

**And** responsive behavior:
- Full width on mobile (<640px)
- Two-column layout on desktop (form left, status right)

**Prerequisites:** Story 1.2 (test endpoint)

**Technical Notes:**
- Create `frontend/components/protect/ControllerForm.tsx`
- Create `frontend/components/protect/ConnectionStatus.tsx`
- Use existing shadcn/ui form components (Input, Button, Switch)
- TanStack Query mutation for save/test operations
- Toast notifications for success/error feedback
- Follow UX spec Section 10.2 wireframes

---

### Story 1.4: Implement WebSocket Connection Manager with Auto-Reconnect

**As a** backend service,
**I want** to maintain a persistent WebSocket connection to the Protect controller,
**So that** I can receive real-time events without polling.

**Acceptance Criteria:**

**Given** a Protect controller is configured and saved
**When** the backend service starts or controller is added
**Then** the system establishes a WebSocket connection to the controller

**And** WebSocket connection lifecycle:
- Initial connection attempt on startup/save
- Connection state tracked in database (`is_connected` field)
- `last_connected_at` updated on successful connection

**And** auto-reconnect behavior (FR15):
- On disconnect: Wait 1 second, then retry
- Exponential backoff: 1s → 2s → 4s → 8s → 16s → 30s (max)
- Maximum reconnect attempts: Unlimited (keep trying)
- NFR3: First reconnect attempt within 5 seconds of disconnect

**And** graceful shutdown:
- Properly close WebSocket on server shutdown
- Mark controller as disconnected in database
- No resource leaks

**And** status broadcasting:
- WebSocket message `PROTECT_CONNECTION_STATUS` sent to frontend on state change
- Message format: `{ type: "PROTECT_CONNECTION_STATUS", data: { controller_id, status, error }, timestamp }`

**And** error handling:
- Log all connection errors with context (no credentials in logs)
- Update `last_error` field in database
- Continue operation even if one controller fails

**Prerequisites:** Story 1.2 (connection validation)

**Technical Notes:**
- Extend `ProtectService` with `connect()`, `disconnect()`, `_reconnect_with_backoff()` methods
- Use `asyncio.Task` for background WebSocket listener
- Store active connections in `app.state.protect_connections` dict
- Use `uiprotect` library's built-in WebSocket: `client.subscribe_websocket()`
- Integrate with FastAPI lifespan events for startup/shutdown

---

### Story 1.5: Add Controller Edit and Delete Functionality

**As a** user,
**I want** to edit or remove my Protect controller configuration,
**So that** I can update credentials or disconnect the integration.

**Acceptance Criteria:**

**Given** I have a Protect controller configured
**When** I view the Settings → UniFi Protect section
**Then** I see my controller with "Edit" and "Remove" options

**And** when editing:
- Form pre-populates with existing values (password field shows "••••••••")
- Password field is optional when editing (only update if changed)
- "Test Connection" re-validates with new settings
- "Save" updates controller and reconnects WebSocket if credentials changed

**And** when removing (FR5):
- Confirmation modal: "Remove UniFi Protect Controller? This will disconnect all Protect cameras and stop receiving events."
- Destructive action button (red)
- On confirm: Disconnect WebSocket, delete controller record, cascade delete Protect cameras
- Toast: "Controller removed successfully"

**And** API endpoints support:
- `PUT /protect/controllers/{id}` - Partial update (only changed fields)
- `DELETE /protect/controllers/{id}` - Delete with confirmation flag

**And** cascade behavior:
- Deleting controller removes associated cameras from `cameras` table
- Historical events remain (with `source_type: 'protect'`) for audit trail

**Prerequisites:** Story 1.3 (controller UI)

**Technical Notes:**
- Add `updateController` and `deleteController` mutations
- Use shadcn/ui AlertDialog for delete confirmation
- Password field logic: Empty = no change, value = update
- Trigger `protect_service.reconnect()` if connection settings changed

---

## Epic 2: Camera Discovery & Configuration

**Goal:** Enable automatic discovery of cameras from the connected UniFi Protect controller and allow users to selectively enable cameras for AI analysis with per-camera event filtering.

**Value:** Zero manual camera configuration - cameras appear automatically, users just select which ones to monitor.

---

### Story 2.1: Implement Camera Auto-Discovery from Protect Controller

**As a** system,
**I want** to automatically discover all cameras from a connected Protect controller,
**So that** users don't need to manually configure RTSP URLs for each camera.

**Acceptance Criteria:**

**Given** a Protect controller is connected
**When** connection is established (or user clicks "Refresh")
**Then** the system fetches all cameras from the controller within 10 seconds (NFR1)

**And** for each discovered camera, extract:
- `protect_camera_id` - Unique ID from Protect
- `name` - Camera name as configured in Protect
- `type` - Camera model (e.g., "G4 Doorbell Pro", "G4 Pro", "G3 Flex")
- `is_doorbell` - Boolean based on camera type
- `is_online` - Current connection status in Protect
- `smart_detection_capabilities` - What types this camera can detect

**And** discovery results are:
- Returned immediately via API
- NOT automatically saved to cameras table (user must enable)
- Cached for 60 seconds to avoid repeated API calls

**And** API endpoint `GET /protect/controllers/{id}/cameras` returns:
```json
{
  "data": [
    {
      "protect_camera_id": "abc123",
      "name": "Front Door",
      "type": "doorbell",
      "model": "G4 Doorbell Pro",
      "is_online": true,
      "is_enabled_for_ai": false,
      "smart_detection_capabilities": ["person", "vehicle", "package"]
    }
  ],
  "meta": { "count": 6, "controller_id": "..." }
}
```

**And** error handling:
- If discovery fails, return cached results (if available) with warning
- Log discovery failures for debugging

**Prerequisites:** Story 1.4 (WebSocket connection)

**Technical Notes:**
- Use `uiprotect` library: `await client.get_cameras()`
- Add `discover_cameras()` method to `ProtectService`
- Camera capabilities vary by model - handle gracefully
- Doorbell detection: Check `camera.type` or `camera.feature_flags`

---

### Story 2.2: Build Discovered Camera List UI with Enable/Disable

**As a** user,
**I want** to see all cameras discovered from my Protect controller and choose which to enable for AI analysis,
**So that** I can control which cameras generate events.

**Acceptance Criteria:**

**Given** I'm on Settings → UniFi Protect section with a connected controller
**When** the controller connects successfully
**Then** I see "Discovered Cameras (N found)" section with a list of cameras

**And** each camera card displays:
- Enable checkbox (left side)
- Camera icon (doorbell icon for doorbells, camera icon for others)
- Camera name (bold)
- Camera type/model (muted text, e.g., "G4 Doorbell Pro")
- Status indicator (green dot = online, red dot = offline)
- "Configure Filters" button (right side, only shown when enabled)

**And** camera list behavior:
- Enabled cameras sorted to top, then alphabetical
- Disabled cameras shown at 50% opacity with "(Disabled)" label
- Offline cameras show "Offline" badge regardless of enabled state
- Loading state: Skeleton cards while fetching

**And** enable/disable toggle (FR10):
- Toggling ON: Creates camera record in database with `source_type: 'protect'`
- Toggling OFF: Marks camera as disabled (keeps record for settings persistence)
- Toggle persists immediately (optimistic update with rollback on error)
- Toast confirmation: "Camera enabled" / "Camera disabled"

**And** empty state:
- If no cameras discovered: "No cameras found. Check your Protect controller."
- If controller disconnected: "Connect your controller to discover cameras"

**And** responsive layout:
- Single column on mobile
- Two columns on tablet/desktop

**Prerequisites:** Story 2.1 (camera discovery API)

**Technical Notes:**
- Create `frontend/components/protect/DiscoveredCameraList.tsx`
- Create `frontend/components/protect/DiscoveredCameraCard.tsx`
- Use TanStack Query for camera list with 60-second cache
- Optimistic updates for enable/disable toggle
- Follow UX spec Section 10.2 wireframes

---

### Story 2.3: Implement Per-Camera Event Type Filtering

**As a** user,
**I want** to configure which event types each camera should analyze,
**So that** I can reduce noise by filtering out unwanted detections.

**Acceptance Criteria:**

**Given** I have an enabled Protect camera
**When** I click "Configure Filters" on that camera
**Then** I see an event type filter popover/dropdown

**And** filter options include (FR11):
- Person (checkbox, default: checked)
- Vehicle (checkbox, default: checked)
- Package (checkbox, default: checked)
- Animal (checkbox, default: unchecked)
- All Motion (checkbox, default: unchecked) - mutually exclusive with others

**And** "All Motion" behavior:
- When checked: Disables and unchecks other options
- Helper text: "Analyzes all motion events, ignores smart detection filtering"
- When unchecked: Re-enables other options

**And** filter persistence (FR13):
- Changes saved on "Apply" button click
- "Cancel" reverts to saved state
- Settings stored in `cameras.smart_detection_types` as JSON array
- Settings persist across app restarts

**And** API endpoint `PUT /protect/controllers/{id}/cameras/{camera_id}/filters`:
- Body: `{ smart_detection_types: ["person", "vehicle"] }`
- Response: Updated camera record

**And** visual feedback:
- Active filters shown as badge count on camera card: "3 filters"
- Or inline text: "Person, Vehicle, Package"

**Prerequisites:** Story 2.2 (camera list UI)

**Technical Notes:**
- Create `frontend/components/protect/EventTypeFilter.tsx`
- Use shadcn/ui Popover or DropdownMenu
- Store as JSON array: `["person", "vehicle", "package"]`
- Empty array or `["motion"]` means all motion
- Follow UX spec Section 10.3 wireframes

---

### Story 2.4: Add Camera Status Sync and Refresh Functionality

**As a** user,
**I want** camera online/offline status to update in real-time and manually refresh the list,
**So that** I can see current camera availability.

**Acceptance Criteria:**

**Given** I'm viewing the discovered cameras list
**When** a camera goes online or offline in Protect
**Then** the status indicator updates within 30 seconds

**And** manual refresh:
- "Refresh" button in Discovered Cameras header
- Clicking triggers new discovery from controller
- Loading spinner during refresh
- Toast: "Cameras refreshed" or error message

**And** status sync mechanism:
- WebSocket events from Protect include camera status changes
- Backend broadcasts `CAMERA_STATUS_CHANGED` message to frontend
- Frontend updates individual camera status without full refresh

**And** offline camera handling:
- Offline cameras still shown in list (not hidden)
- Events from offline cameras are not expected
- Tooltip: "Camera is offline in UniFi Protect"

**And** new camera detection:
- If Protect has cameras not in our list, show "New" badge
- User must explicitly enable new cameras

**Prerequisites:** Story 2.2 (camera list UI)

**Technical Notes:**
- Handle `ws_camera_update` events from uiprotect
- Debounce rapid status changes (max 1 update per 5 seconds per camera)
- Consider polling fallback if WebSocket events unreliable

---

## Epic 3: Real-Time Event Processing

**Goal:** Receive real-time motion and smart detection events from UniFi Protect via WebSocket, process them through the AI pipeline, and store enriched events.

**Value:** Events arrive in real-time (< 2 seconds) instead of polling delays, with intelligent filtering based on user preferences.

---

### Story 3.1: Implement Protect Event Listener and Event Handler

**As a** backend service,
**I want** to receive and process real-time events from the Protect WebSocket,
**So that** motion detections trigger AI analysis immediately.

**Acceptance Criteria:**

**Given** a WebSocket connection to Protect is established
**When** motion or smart detection occurs on an enabled camera
**Then** the system receives the event within 1 second

**And** event handler processes incoming Protect events (FR16):
- Identify event type: motion, smart_detect_person, smart_detect_vehicle, smart_detect_package, smart_detect_animal, ring (doorbell)
- Look up camera by `protect_camera_id`
- Check if camera is enabled for AI analysis
- If not enabled, discard event silently

**And** event filtering applies (FR17):
- Load camera's `smart_detection_types` configuration
- If event type matches configured types, proceed
- If event type not in configured types, discard silently
- "All Motion" configuration processes all event types

**And** event deduplication:
- Track last event time per camera
- Apply existing cooldown logic (default 60 seconds)
- Prevent duplicate events from rapid-fire detections

**And** logging:
- Log event received (camera name, event type, timestamp)
- Log filter decisions (passed/filtered with reason)
- No PII or credentials in logs

**Prerequisites:** Story 1.4 (WebSocket connection), Story 2.3 (event filtering)

**Technical Notes:**
- Create `backend/app/services/protect_event_handler.py`
- Use `uiprotect` callback: `client.subscribe_websocket(callback=handle_event)`
- Event types from uiprotect: `WSAction.ADD`, `WSAction.UPDATE` for motion events
- Access smart detection via `event.smart_detect_types`

---

### Story 3.2: Implement Snapshot Retrieval from Protect API

**As a** backend service,
**I want** to fetch a snapshot image when an event passes filtering,
**So that** I can send it to the AI provider for description.

**Acceptance Criteria:**

**Given** an event has passed the filtering stage
**When** the event handler requests a snapshot
**Then** the system fetches the snapshot from Protect API within 1 second (NFR4)

**And** snapshot retrieval (FR18):
- Use Protect API to get snapshot at event timestamp
- If event-time snapshot unavailable, get current snapshot
- Image format: JPEG
- Resolution: Full resolution from camera (up to 4K)
- Resize to max 1920x1080 for AI processing (reduce costs)

**And** snapshot handling:
- Convert to base64 for AI API submission
- Store thumbnail (320x180) for event record
- Clean up full-size image after processing

**And** error handling:
- If snapshot fails, retry once after 500ms
- If still fails, log error and skip event (don't crash)
- Track snapshot failure rate for monitoring

**And** performance:
- Snapshot retrieval completes within 1 second (NFR4)
- Concurrent snapshots limited to 3 per controller

**Prerequisites:** Story 3.1 (event listener)

**Technical Notes:**
- Use `uiprotect`: `await camera.get_snapshot()`
- Or with timestamp: `await camera.get_snapshot(dt=event_timestamp)`
- PIL/Pillow for image resizing
- Consider caching controller auth token (refresh on 401)

---

### Story 3.3: Integrate Protect Events with Existing AI Pipeline

**As a** backend service,
**I want** Protect events to flow through the same AI pipeline as RTSP events,
**So that** all events receive AI descriptions consistently.

**Acceptance Criteria:**

**Given** a snapshot has been retrieved from Protect
**When** the event handler submits it for AI analysis
**Then** the existing AI service processes it using configured providers

**And** AI submission (FR19):
- Use existing `AIService.analyze_frame()` method
- Pass snapshot as base64-encoded image
- Include context: camera name, event type (person/vehicle/package/animal/motion)
- Use existing fallback chain (OpenAI → Grok → Gemini → Claude)

**And** event storage (FR20):
- Create event record in `events` table
- Set `source_type: 'protect'`
- Set `protect_event_id` to Protect's native event ID
- Set `smart_detection_type` to the Protect detection type
- Store AI description, confidence, objects_detected
- Store thumbnail_path for saved thumbnail

**And** end-to-end latency (NFR2):
- Total time from Protect detection to stored event < 2 seconds
- Track and log processing_time_ms

**And** WebSocket broadcast:
- Broadcast `EVENT_CREATED` to frontend
- Include all event details for real-time UI update

**Prerequisites:** Story 3.2 (snapshot retrieval)

**Technical Notes:**
- Reuse `backend/app/services/event_processor.py` pipeline
- Add `source_type` and `protect_*` fields to Event model
- Ensure existing RTSP flow is unaffected
- Add metrics: events_processed_total{source="protect"}

---

### Story 3.4: Add Event Source Type Display in Dashboard

**As a** user,
**I want** to see which camera system captured each event,
**So that** I can distinguish between Protect and RTSP/USB camera events.

**Acceptance Criteria:**

**Given** I'm viewing the event timeline
**When** I look at event cards
**Then** I see a source type indicator for each event (FR36)

**And** source type badge displays:
- UniFi Protect: Shield icon + "Protect" text (muted styling)
- RTSP: Camera icon + "RTSP" text
- USB: USB icon + "USB" text
- Position: Top-right of event card, next to timestamp

**And** smart detection badge displays (for Protect events):
- Person: Blue badge with person icon
- Vehicle: Purple badge with car icon
- Package: Orange badge with box icon
- Animal: Green badge with paw icon
- Motion: Gray badge with motion waves icon
- Position: Below AI description, alongside existing object badges

**And** filtering enhancement:
- Event timeline filter includes "Source" dropdown
- Options: All, UniFi Protect, RTSP, USB
- Filter persists in URL query params

**Prerequisites:** Story 3.3 (event storage)

**Technical Notes:**
- Create `frontend/components/events/SourceTypeBadge.tsx`
- Create `frontend/components/events/SmartDetectionBadge.tsx`
- Update `EventCard` component to include new badges
- Add `source_type` filter to events API endpoint
- Follow UX spec Section 10.5

---

## Epic 4: Doorbell & Multi-Camera Features

**Goal:** Handle doorbell-specific events with distinct UX and implement multi-camera event correlation for comprehensive scene understanding.

**Value:** Doorbell rings get priority attention, and users can see when the same person/event was captured by multiple cameras.

---

### Story 4.1: Implement Doorbell Ring Event Detection and Handling

**As a** system,
**I want** to detect and process doorbell ring events distinctly from motion events,
**So that** users receive immediate, prioritized notifications when someone rings the doorbell.

**Acceptance Criteria:**

**Given** I have a UniFi Protect doorbell enabled
**When** someone presses the doorbell button
**Then** the system detects this as a "ring" event (FR21)

**And** ring event detection:
- Event type from Protect: `ring` or doorbell-specific event
- Immediately fetch snapshot (don't wait for motion)
- Flag event as `is_doorbell_ring: true`

**And** AI prompt modification (FR23):
- Use doorbell-specific prompt: "Describe who is at the front door. Include their appearance, what they're wearing, and if they appear to be a delivery person, visitor, or solicitor."
- This replaces generic motion prompt for ring events

**And** event storage:
- Set `is_doorbell_ring: true` in event record
- Set `smart_detection_type: 'ring'`
- Priority flag for notification system

**And** distinct notification (FR22):
- WebSocket message type: `DOORBELL_RING`
- Higher priority than motion events
- Include: event_id, camera_id, camera_name, thumbnail_url

**Prerequisites:** Story 3.3 (event pipeline)

**Technical Notes:**
- Doorbell events may have different structure in uiprotect
- Check `event.type == 'ring'` or similar
- Create specific handler in `ProtectEventHandler.process_doorbell_ring()`

---

### Story 4.2: Build Doorbell Event Card with Distinct Styling

**As a** user,
**I want** doorbell ring events to stand out in my timeline,
**So that** I can quickly identify when someone was at my door.

**Acceptance Criteria:**

**Given** a doorbell ring event appears in the timeline
**When** I view the event timeline
**Then** the doorbell event card has distinct styling

**And** doorbell card appearance:
- Header: "🔔 DOORBELL RING" label (replaces camera name position)
- Accent border: Cyan left border (3px) to stand out
- Camera name shown below header
- Timestamp shows "Just now" / relative time

**And** doorbell card content:
- Larger thumbnail (or same size with prominence)
- AI description focused on "who is at the door"
- Person badge always shown (if person detected)

**And** notification bell integration:
- Doorbell rings appear at top of notification dropdown
- Sound notification (if enabled) different from motion
- Badge shows doorbell icon for ring notifications

**And** responsive behavior:
- Same layout on mobile and desktop
- Full-width card on mobile timeline

**Prerequisites:** Story 4.1 (doorbell detection)

**Technical Notes:**
- Create `DoorbellEventCard` variant or conditional styling in `EventCard`
- Use accent color from design system (#0ea5e9 cyan)
- Doorbell icon: 🔔 or Heroicons bell icon
- Follow UX spec Section 10.7

---

### Story 4.3: Implement Multi-Camera Event Correlation Service

**As a** system,
**I want** to detect when multiple cameras capture the same real-world event,
**So that** I can link related events together for comprehensive scene understanding.

**Acceptance Criteria:**

**Given** multiple Protect cameras are enabled
**When** a person/vehicle triggers events on multiple cameras within a short time window
**Then** the system correlates these events (FR24)

**And** correlation logic:
- Time window: 10 seconds (configurable)
- Same or similar smart detection type (person → person, vehicle → vehicle)
- Different cameras (same camera excluded)
- Same controller (stricter correlation)

**And** correlation implementation (FR25):
- Generate `correlation_group_id` (UUID) for first event in group
- Apply same `correlation_group_id` to correlated events
- Store `correlated_event_ids` JSON array on each event

**And** correlation service:
- Maintain in-memory buffer of recent events (last 60 seconds)
- O(n) scan for correlation candidates
- Async check (doesn't block event storage)

**And** edge cases:
- Event correlates with multiple existing events → Join the group
- Two events correlate simultaneously → Same group ID
- User can disable correlation via settings (future)

**Prerequisites:** Story 3.3 (event storage)

**Technical Notes:**
- Create `backend/app/services/correlation_service.py`
- Buffer: `collections.deque` with maxlen for memory bounds
- Correlation check runs after event storage (fire-and-forget)
- Update events with correlation info via database UPDATE

---

### Story 4.4: Display Correlated Events in Dashboard

**As a** user,
**I want** to see when events are correlated across cameras,
**So that** I can understand the complete picture of what happened.

**Acceptance Criteria:**

**Given** events have been correlated
**When** I view a correlated event in the timeline
**Then** I see a correlation indicator (FR26)

**And** correlation indicator displays:
- Link chain icon (🔗) at bottom of event card
- Text: "Also captured by: [Camera Name], [Camera Name]"
- Clickable camera names that scroll to/highlight that event

**And** correlation visual grouping:
- Correlated events share subtle visual connector
- Options: Shared background tint, or connecting line, or grouped together
- User can expand/collapse correlated group

**And** correlation in event detail modal:
- "Related Events" section showing thumbnails from other cameras
- Click thumbnail to switch to that event

**And** API support:
- `GET /events/{id}` includes `correlated_events` array
- Each with: id, camera_name, thumbnail_url, timestamp

**Prerequisites:** Story 4.3 (correlation service)

**Technical Notes:**
- Create `frontend/components/events/CorrelationIndicator.tsx`
- Use correlation_group_id to fetch related events
- Smooth scroll to correlated event on click
- Follow UX spec Section 10.5

---

## Epic 5: xAI Grok Provider

**Goal:** Add xAI Grok as an additional AI provider option, integrated into the existing multi-provider fallback chain.

**Value:** Users have more AI provider choices, and Grok offers competitive vision capabilities as an alternative to OpenAI/Claude/Gemini.

---

### Story 5.1: Implement xAI Grok Provider in AI Service

**As a** backend developer,
**I want** to add xAI Grok as an AI provider option,
**So that** users can choose Grok for event descriptions.

**Acceptance Criteria:**

**Given** the AI service supports multiple providers
**When** I add xAI Grok as a provider
**Then** it follows the same interface as existing providers (FR31)

**And** Grok provider implementation (FR30):
- Uses OpenAI-compatible API at `https://api.x.ai/v1`
- Model: `grok-2-vision-1212` (vision-capable)
- Same request/response format as OpenAI
- Supports base64-encoded images in messages

**And** provider integration:
- Add `grok` to `AIService.PROVIDERS` list
- Implement `_call_grok()` method
- Use `AsyncOpenAI` client with custom `base_url`

**And** configuration:
- API key stored encrypted: `ai_api_key_grok`
- Model selection (future): grok-2-vision, grok-2-vision-1212
- Default timeout: 30 seconds

**And** fallback behavior (NFR7):
- If Grok fails, fall back to next provider within 2 seconds
- Retry logic: 2 retries with 500ms delay
- Track failures for provider health monitoring

**And** usage tracking:
- Log Grok API calls to `ai_usage` table
- Track: tokens_used, response_time_ms, success/failure

**Prerequisites:** None (independent of Protect integration)

**Technical Notes:**
- Extend `backend/app/services/ai_service.py`
- Use existing `openai` package: `AsyncOpenAI(base_url="https://api.x.ai/v1", api_key=...)`
- API docs: https://docs.x.ai/docs/guides/image-understanding
- Handle rate limits (429 responses)

---

### Story 5.2: Build Grok Provider Configuration UI

**As a** user,
**I want** to configure xAI Grok in the AI Providers settings,
**So that** I can use Grok for event descriptions.

**Acceptance Criteria:**

**Given** I navigate to Settings → AI Providers
**When** I view the provider list
**Then** I see xAI Grok as an available provider (FR27)

**And** Grok appears in provider list:
- Row: "xAI Grok" with Grok icon/logo
- Status: "Not configured" (muted) or "Configured ✓" (green)
- Actions: "Setup" button (if not configured) or "Edit" button

**And** Grok configuration form:
- API Key field (password input, required)
- "Test" button to validate API key (FR28)
- "Save" button (primary, disabled until valid)
- "Remove" button (destructive, with confirmation)

**And** API key validation:
- Test makes actual API call with simple request
- Success: Green checkmark + "API key valid"
- Failure: Red X + specific error (invalid key, rate limited, etc.)

**And** drag-to-reorder (FR29):
- Provider list has drag handles
- User can reorder fallback priority
- Order saved to settings: `ai_provider_order: ["openai", "grok", "gemini", "anthropic"]`

**Prerequisites:** Story 5.1 (Grok provider implementation)

**Technical Notes:**
- Add Grok section to existing AI Providers UI
- Reuse existing provider form patterns (consistent UX)
- Use dnd-kit or similar for drag-to-reorder
- Store order in system_settings table
- Follow UX spec Section 10.4

---

### Story 5.3: Add Grok to Fallback Chain and Test Integration

**As a** system,
**I want** Grok integrated into the AI fallback chain,
**So that** it's used according to user-configured priority.

**Acceptance Criteria:**

**Given** Grok is configured with valid API key
**When** an event needs AI description
**Then** Grok is used based on its position in the fallback chain

**And** fallback chain behavior:
- Read `ai_provider_order` from settings
- Attempt providers in order until one succeeds
- Skip providers without valid API keys
- Default order: OpenAI → Grok → Gemini → Anthropic

**And** Grok-specific handling:
- Handle Grok-specific errors (rate limits, model unavailable)
- Respect Grok rate limits (queue if needed)
- Track Grok usage separately in AI usage stats

**And** integration testing:
- Unit test: Grok provider mock responses
- Integration test: Grok in fallback chain
- E2E test: Configure Grok, trigger event, verify description

**And** monitoring:
- Log which provider was used for each event
- Dashboard shows provider usage breakdown
- Alert if Grok has high failure rate

**Prerequisites:** Story 5.2 (configuration UI)

**Technical Notes:**
- Update `AIService.get_description()` to use ordered chain
- Add `provider_used` field to event record (for analytics)
- Consider provider health tracking (circuit breaker pattern)

---

## Epic 6: Coexistence & Polish

**Goal:** Ensure UniFi Protect cameras work seamlessly alongside existing RTSP/USB cameras, with unified experience and thorough testing of all Phase 2 features.

**Value:** Users with mixed camera setups get a consistent experience, and all Phase 2 features are production-ready.

---

### Story 6.1: Verify RTSP/USB Camera Coexistence

**As a** user,
**I want** my existing RTSP and USB cameras to continue working alongside Protect cameras,
**So that** I can use both camera types in my system.

**Acceptance Criteria:**

**Given** I have both Protect cameras and RTSP/USB cameras configured
**When** both camera types detect motion
**Then** events from all sources appear in the same timeline (FR32, FR33, FR34)

**And** coexistence verification:
- RTSP camera events continue working (no regression)
- USB camera events continue working (no regression)
- Protect camera events work alongside them
- No duplicate events (Protect camera not also configured as RTSP)

**And** unified timeline (FR34):
- All events sorted by timestamp (newest first)
- Source type badge distinguishes camera type
- Filter by source type works correctly
- Search includes events from all sources

**And** alert rules (FR35):
- Existing alert rules evaluate events from all sources
- Rule conditions work for Protect events (object types, etc.)
- Webhooks trigger for Protect events
- No rule changes needed for Protect integration

**And** performance:
- Adding Protect cameras doesn't slow RTSP processing
- Event timeline loads efficiently with mixed sources

**Prerequisites:** Story 3.4 (source type display)

**Technical Notes:**
- Add integration tests for mixed camera scenarios
- Verify no code paths that assume single camera type
- Test concurrent events from multiple sources
- Check database indexes for query performance

---

### Story 6.2: Enhance Cameras Page with Source Grouping

**As a** user,
**I want** to see all my cameras organized by source type,
**So that** I can manage different camera systems effectively.

**Acceptance Criteria:**

**Given** I have cameras from multiple sources
**When** I view the Cameras page
**Then** I can optionally group cameras by source

**And** camera page enhancements:
- Tab filter: [All] [UniFi Protect (4)] [RTSP (1)] [USB (0)]
- Camera cards show source type badge
- Protect cameras show additional info (model, firmware if available)

**And** "Add Camera" flow:
- Dropdown or choice: "Manual (RTSP/USB)" vs "UniFi Protect"
- "UniFi Protect" option redirects to Settings → UniFi Protect
- "Manual" opens existing camera form

**And** Protect camera cards:
- Status reflects WebSocket connection status
- "Configure" links to Settings → UniFi Protect section
- Cannot edit RTSP URL (managed by Protect)

**And** responsive layout:
- Tab filter horizontal scroll on mobile
- Camera grid adapts to screen size

**Prerequisites:** Story 6.1 (coexistence verification)

**Technical Notes:**
- Update `frontend/app/cameras/page.tsx`
- Add source grouping logic to camera list
- Use URL query param for active filter: `?source=protect`
- Follow UX spec Section 10.6

---

### Story 6.3: Implement Phase 2 Error Handling and Edge Cases

**As a** system,
**I want** graceful error handling for all Phase 2 features,
**So that** the system remains stable and informative when issues occur.

**Acceptance Criteria:**

**Given** various error conditions can occur
**When** errors happen
**Then** the system handles them gracefully (NFR6)

**And** controller connection errors:
- "Unable to connect" → Yellow banner, auto-retry in progress
- "Authentication failed" → Red banner, prompt to check credentials
- "Controller unreachable" → Red banner, manual retry button
- Connection restored → Green toast "Reconnected"

**And** camera discovery errors:
- "No cameras found" → Helpful message, check controller
- Partial failure → Show discovered cameras, note missing

**And** WebSocket errors:
- Connection lost → Yellow toast, auto-reconnect
- Reconnected → Brief green toast
- Max retries exceeded → Red banner, manual reconnect option

**And** API errors (Grok, Protect):
- Rate limited → Queue request, retry later
- Provider down → Fall back to next provider
- All providers down → Store event without description, flag for retry

**And** UI error states:
- Forms show inline validation errors
- API errors show toast notifications
- Network errors show retry option

**Prerequisites:** Story 5.3 (Grok integration), Story 4.4 (correlation display)

**Technical Notes:**
- Review all API calls for error handling
- Add error boundaries to React components
- Implement retry logic with exponential backoff
- Log errors with context for debugging
- Follow UX spec Section 10.9

---

### Story 6.4: Phase 2 Integration Testing and Documentation

**As a** developer and user,
**I want** comprehensive testing and documentation for Phase 2 features,
**So that** the release is production-ready and users can self-serve.

**Acceptance Criteria:**

**Given** all Phase 2 features are implemented
**When** preparing for release
**Then** integration tests cover all critical paths

**And** integration tests include:
- Controller connection lifecycle (connect, reconnect, disconnect)
- Camera discovery and enable/disable
- Event flow from Protect to dashboard
- Doorbell ring detection and display
- Multi-camera correlation
- Grok provider configuration and fallback
- RTSP/Protect coexistence

**And** performance tests verify:
- NFR1: Camera discovery < 10 seconds
- NFR2: Event latency < 2 seconds
- NFR3: WebSocket reconnect < 5 seconds
- NFR4: Snapshot retrieval < 1 second

**And** documentation updates:
- README updated with Phase 2 features
- CLAUDE.md updated with new endpoints and services
- Settings page help text for UniFi Protect section
- Troubleshooting guide for common Protect issues

**And** release checklist:
- All acceptance criteria verified
- No critical bugs
- Performance targets met
- Documentation complete

**Prerequisites:** Story 6.3 (error handling)

**Technical Notes:**
- Add pytest integration tests in `tests/integration/`
- Add Playwright E2E tests for critical paths
- Update CLAUDE.md with Phase 2 architecture
- Consider video walkthrough for Protect setup

---

## FR Coverage Matrix

| FR | Description | Epic | Story |
|----|-------------|------|-------|
| FR1 | Add controller by hostname/IP and credentials | 1 | 1.1, 1.3 |
| FR2 | Validate controller connection before saving | 1 | 1.2 |
| FR3 | Store credentials encrypted with Fernet | 1 | 1.1 |
| FR4 | Edit controller connection settings | 1 | 1.5 |
| FR5 | Remove controller with confirmation | 1 | 1.5 |
| FR6 | Test controller connectivity from UI | 1 | 1.2, 1.3 |
| FR7 | Display controller connection status | 1 | 1.3, 1.4 |
| FR8 | Auto-discover cameras from controller | 2 | 2.1 |
| FR9 | View discovered cameras with names/types | 2 | 2.2 |
| FR10 | Enable/disable cameras for AI analysis | 2 | 2.2 |
| FR11 | Configure event type filters per camera | 2 | 2.3 |
| FR12 | Distinguish camera types (camera vs doorbell) | 2 | 2.1, 2.2 |
| FR13 | Persist camera settings across restarts | 2 | 2.3 |
| FR14 | Maintain WebSocket connection to controller | 1 | 1.4 |
| FR15 | Auto-reconnect WebSocket with exponential backoff | 1 | 1.4 |
| FR16 | Receive real-time events via WebSocket | 3 | 3.1 |
| FR17 | Filter events based on camera configuration | 3 | 3.1 |
| FR18 | Fetch snapshot from Protect API on event | 3 | 3.2 |
| FR19 | Submit snapshot to AI provider | 3 | 3.3 |
| FR20 | Store event with AI description | 3 | 3.3 |
| FR21 | Detect doorbell ring events | 4 | 4.1 |
| FR22 | Generate distinct doorbell notification | 4 | 4.1, 4.2 |
| FR23 | AI analysis of who is at door | 4 | 4.1 |
| FR24 | Detect multi-camera event correlation | 4 | 4.3 |
| FR25 | Link correlated events together | 4 | 4.3 |
| FR26 | Display correlated events in dashboard | 4 | 4.4 |
| FR27 | Add xAI Grok as AI provider | 5 | 5.2 |
| FR28 | Validate Grok API key on save | 5 | 5.2 |
| FR29 | Configure Grok position in fallback chain | 5 | 5.2 |
| FR30 | Send images to Grok API for description | 5 | 5.1 |
| FR31 | Grok follows same interface as other providers | 5 | 5.1 |
| FR32 | Protect and RTSP/USB cameras operate simultaneously | 6 | 6.1 |
| FR33 | All camera types feed unified event pipeline | 6 | 6.1 |
| FR34 | Dashboard displays events from all sources | 6 | 6.1 |
| FR35 | Alert rules apply to all camera sources | 6 | 6.1 |
| FR36 | Users can identify camera source type | 3 | 3.4 |

**NFR Coverage:**
- NFR1-NFR4 (Performance): Stories 2.1, 3.2, 3.3, 6.4
- NFR5-NFR8 (Reliability): Stories 1.4, 5.1, 6.3
- NFR9-NFR12 (Security): Stories 1.1, 5.1
- NFR13-NFR16 (Integration): Stories 3.3, 5.1, 6.1

---

## Summary

**Phase 2 Epic Breakdown Complete**

| Metric | Value |
|--------|-------|
| Total Epics | 6 |
| Total Stories | 24 |
| Functional Requirements Covered | 36/36 (100%) |
| Non-Functional Requirements Covered | 16/16 (100%) |

**Epic Sizing:**
- Epic 1: 5 stories (Controller foundation)
- Epic 2: 4 stories (Camera discovery)
- Epic 3: 4 stories (Event processing)
- Epic 4: 4 stories (Doorbell & correlation)
- Epic 5: 3 stories (xAI Grok)
- Epic 6: 4 stories (Coexistence & polish)

**Recommended Sequence:**
1. Epic 1 → Epic 2 → Epic 3 → Epic 4 (Protect integration path)
2. Epic 5 can run in parallel with Epics 1-4 (independent)
3. Epic 6 after all others (integration testing)

**Next Steps in BMad Method:**
1. UX Design ✅ (Section 10 already added to ux-design-specification.md)
2. Architecture ✅ (Phase 2 Additions already added to architecture.md)
3. Sprint Planning → Run `sprint-planning` workflow
4. Implementation → Run `dev-story` workflow for each story

---

_For implementation: Use the `create-story` workflow to generate individual story implementation plans from this epic breakdown._

_This document incorporates UX Design (Section 10) and Architecture (Phase 2 Additions) details that were completed prior to epic breakdown._
