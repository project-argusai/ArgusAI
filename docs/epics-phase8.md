# ArgusAI - Phase 8 Epic Breakdown

**Author:** Brent
**Date:** 2025-12-20
**Project Level:** Enterprise
**Target Scale:** Production

---

## Overview

This document provides the complete epic and story breakdown for ArgusAI Phase 8, decomposing the accumulated backlog items into implementable stories. Phase 8 focuses on bug fixes, video analysis enhancements, AI improvements, and native Apple app foundations.

**Living Document Notice:** This is the initial version. It will be updated after UX Design and Architecture workflows add interaction and technical details to stories.

### Epic Summary

| Epic | Title | Stories | Priority | Focus |
|------|-------|---------|----------|-------|
| P8-1 | Bug Fixes & Stability | 3 | P2 | Critical bug fixes |
| P8-2 | Video Analysis Enhancements | 5 | P2-P3 | Frame sampling improvements |
| P8-3 | AI & Settings Improvements | 3 | P3-P4 | UX polish and AI features |
| P8-4 | Native Apple Apps Foundation | 4 | P3 | Research and architecture |

**Total Stories:** 15

---

## Functional Requirements Inventory

| FR ID | Description | Source | Priority |
|-------|-------------|--------|----------|
| FR1 | Re-analyse function must work without errors | BUG-005 | P2 |
| FR2 | Installation script must support non-ARM64 systems | BUG-006 | P2 |
| FR3 | Push notifications must work for all events, not just first | BUG-007 | P2 |
| FR4 | Store and display all frames used for AI analysis | IMP-006 | P3 |
| FR5 | Configurable number of frames for analysis (5/10/15/20) | IMP-007 | P3 |
| FR6 | Hide MQTT form fields when integration disabled | IMP-008 | P4 |
| FR7 | Download and store full motion capture videos | FF-019 | P3 |
| FR8 | Implement adaptive/content-aware frame sampling | FF-020 | P2 |
| FR9 | Configurable frame sampling strategy selection | FF-021 | P3 |
| FR10 | Query-adaptive frame selection for re-analysis | FF-022 | P4 |
| FR11 | AI-assisted prompt refinement using accuracy feedback | FF-023 | P2 |
| FR12 | Native Apple device applications (iPhone, iPad, Watch, TV, macOS) | FF-024 | P3 |
| FR13 | Cloud relay service for remote Apple app connectivity | FF-025 | P3 |

---

## FR Coverage Map

| Epic | Functional Requirements Covered |
|------|--------------------------------|
| P8-1 (Bug Fixes & Stability) | FR1, FR2, FR3 |
| P8-2 (Video Analysis Enhancements) | FR4, FR5, FR8, FR9, FR10 |
| P8-3 (AI & Settings Improvements) | FR6, FR7, FR11 |
| P8-4 (Native Apple Apps Foundation) | FR12, FR13 |

---

## Epic P8-1: Bug Fixes & Stability

**Goal:** Resolve critical bugs affecting core functionality - re-analysis, installation, and push notifications.

**Business Value:** Users can reliably use key features without errors, improving trust and usability.

**FR Coverage:** FR1, FR2, FR3

---

### Story P8-1.1: Fix Re-Analyse Function Error

As a **user**,
I want **the re-analyse button on event cards to work correctly**,
So that **I can regenerate AI descriptions for events when needed**.

**Acceptance Criteria:**

**Given** I am viewing an event card with a re-analyse button
**When** I click the re-analyse button
**Then** the system should:
- Show a loading indicator during processing
- Send the event to the AI service for re-analysis
- Update the event description with the new AI response
- Display a success toast notification
- Update the event card with the new description

**And** if the re-analysis fails:
- Display a clear error message explaining the failure
- Log the error with stack trace for debugging
- Allow retry without page refresh

**Technical Notes:**
- Investigate `/api/v1/events/{id}/reanalyze` endpoint
- Check if event thumbnail/frames are being passed correctly to AI service
- Verify API client error handling in `frontend/lib/api-client.ts`
- Test with events that have thumbnails vs those without
- Ensure proper async/await handling

**Prerequisites:** None

**Estimated Complexity:** Small (2-4 hours)

---

### Story P8-1.2: Fix Installation Script for Non-ARM64 Systems

As a **user with an Intel/AMD system**,
I want **the installation script to work on my x86_64 machine**,
So that **I can deploy ArgusAI on any common hardware**.

**Acceptance Criteria:**

**Given** I am running the installation script on a non-ARM64 system (x86_64/amd64)
**When** the script executes
**Then** the system should:
- Detect the CPU architecture automatically (`uname -m`)
- Install architecture-appropriate dependencies
- Use correct Python/pip paths for the platform
- Complete installation without architecture-specific errors

**And** the script should handle:
- macOS Intel (x86_64)
- Linux x86_64 (Ubuntu, Debian)
- Homebrew vs apt-get package managers
- Python version differences

**Technical Notes:**
- Review `install.sh` for hardcoded ARM64 paths (e.g., `/opt/homebrew/`)
- Add architecture detection: `ARCH=$(uname -m)`
- Use conditional paths: Intel macOS uses `/usr/local/`, ARM uses `/opt/homebrew/`
- Test on both ARM64 and x86_64 systems
- Consider using `$(brew --prefix)` for portable Homebrew paths

**Prerequisites:** None

**Estimated Complexity:** Small (2-4 hours)

---

### Story P8-1.3: Fix Push Notifications Only Working Once

As a **user with push notifications enabled**,
I want **to receive notifications for every new event**,
So that **I am alerted consistently, not just the first time**.

**Acceptance Criteria:**

**Given** I have enabled push notifications and subscribed successfully
**When** multiple events are created over time
**Then** I should receive a push notification for each event that matches my notification settings

**And** the system should:
- Maintain valid push subscription after first notification
- Not invalidate or overwrite subscription on subsequent events
- Handle subscription refresh if needed
- Log notification delivery status for each event

**Technical Notes:**
- Investigate service worker registration persistence in `frontend/public/sw.js`
- Check if `PushSubscription` is being overwritten or invalidated
- Review backend push sending logic in `backend/app/services/push_notification_service.py`
- Verify VAPID key consistency between sends
- Check browser notification throttling limits
- Test with Chrome DevTools → Application → Service Workers
- Ensure `event_processor.py` calls push service for every qualifying event

**Prerequisites:** None

**Estimated Complexity:** Medium (4-8 hours)

---

## Epic P8-2: Video Analysis Enhancements

**Goal:** Improve video frame extraction, storage, and analysis capabilities with adaptive sampling and user configurability.

**Business Value:** Better AI descriptions through smarter frame selection, reduced costs, and user control over analysis depth.

**FR Coverage:** FR4, FR5, FR8, FR9, FR10

---

### Story P8-2.1: Store All Analysis Frames During Event Processing

As a **user**,
I want **all frames used for AI analysis to be stored**,
So that **I can review exactly what the AI saw when generating descriptions**.

**Acceptance Criteria:**

**Given** an event is being processed with multi-frame analysis
**When** frames are extracted for AI analysis
**Then** the system should:
- Save all extracted frames to `data/frames/{event_id}/` directory
- Store frame metadata (timestamp offset, frame number) in database
- Create frame records linked to the event
- Apply same retention policy as thumbnails

**And** the database should store:
- `event_id` (FK to events)
- `frame_number` (1, 2, 3...)
- `frame_path` (relative path to frame file)
- `timestamp_offset_ms` (offset from event start)
- `created_at`

**Technical Notes:**
- Modify `frame_extraction_service.py` to persist frames instead of just returning them
- Add `EventFrame` model in `backend/app/models/`
- Create Alembic migration for `event_frames` table
- Update `event_processor.py` to save frames during analysis
- Implement cleanup in retention job for old frames
- Consider storage impact: ~50KB per frame × 10 frames = ~500KB per event

**Prerequisites:** None

**Estimated Complexity:** Medium (4-8 hours)

---

### Story P8-2.2: Display Analysis Frames Gallery on Event Cards

As a **user**,
I want **to click on an event thumbnail to see all frames that were analyzed**,
So that **I understand what the AI used to generate the description**.

**Acceptance Criteria:**

**Given** I am viewing an event card with stored analysis frames
**When** I click on the event thumbnail
**Then** a modal/lightbox should open showing:
- All frames used for analysis in sequence
- Navigation arrows (prev/next) between frames
- Frame number indicator (e.g., "3 of 10")
- Timestamp offset for each frame
- Close button (X) and click-outside-to-close

**And** the gallery should:
- Load frames lazily for performance
- Support keyboard navigation (arrow keys, Escape to close)
- Be responsive on mobile (swipe gestures)
- Show placeholder if no frames available (single-frame mode events)

**Technical Notes:**
- Create `FrameGalleryModal` component in `frontend/components/events/`
- Use Radix Dialog for accessible modal
- Fetch frames via `GET /api/v1/events/{id}/frames` endpoint
- Add API endpoint in `backend/app/api/v1/events.py`
- Consider using react-image-gallery or building custom
- Add loading skeleton while frames load

**Prerequisites:** P8-2.1

**Estimated Complexity:** Medium (4-8 hours)

---

### Story P8-2.3: Add Configurable Frame Count Setting

As a **user**,
I want **to configure how many frames are extracted for AI analysis**,
So that **I can balance description quality against AI costs**.

**Acceptance Criteria:**

**Given** I am on Settings → General tab
**When** I see the "Analysis Frame Count" setting
**Then** I should be able to select from: 5, 10, 15, or 20 frames

**And** when changing the value:
- A warning modal should appear explaining cost implications
- Modal text: "More frames may improve description accuracy but will increase AI costs. Each frame is sent to the AI provider for analysis."
- Modal has "Cancel" and "Confirm" buttons
- Setting is saved only after confirmation

**And** the setting should:
- Default to 10 frames (current behavior)
- Persist in system settings
- Apply to all future event processing
- Be passed to frame extraction service

**Technical Notes:**
- Add `analysis_frame_count` to system settings schema
- Create dropdown/select in `frontend/components/settings/GeneralSettings.tsx`
- Create `CostWarningModal` component for confirmation
- Update `frame_extraction_service.py` to use configurable count
- Add API endpoint to get/set this setting if not exists
- Validate value is one of [5, 10, 15, 20]

**Prerequisites:** None

**Estimated Complexity:** Small (2-4 hours)

---

### Story P8-2.4: Implement Adaptive Frame Sampling

As a **system**,
I want **to select frames based on content changes rather than fixed intervals**,
So that **analysis captures key moments while reducing redundant frames**.

**Acceptance Criteria:**

**Given** a video clip is being processed for frame extraction
**When** adaptive sampling mode is enabled
**Then** the system should:
- Calculate similarity between consecutive frames using SSIM or histogram comparison
- Skip frames that are >95% similar to previous selected frame
- Prioritize frames with high motion/change scores
- Still respect the configured frame count limit
- Ensure temporal coverage (don't cluster all frames at one moment)

**And** the adaptive algorithm should:
- Detect scene changes (shot boundaries)
- Weight frames by motion magnitude
- Ensure minimum temporal spacing (e.g., at least 500ms between frames)
- Fall back to uniform sampling if video is very static

**Technical Notes:**
- Add `AdaptiveFrameSampler` class in `backend/app/services/`
- Use OpenCV for SSIM calculation: `cv2.compare_ssim()`
- Use histogram comparison: `cv2.compareHist()`
- Consider optical flow for motion scoring
- Implement as strategy pattern alongside uniform sampling
- Add configuration flag to enable/disable adaptive mode
- Log frame selection decisions for debugging

**Prerequisites:** P8-2.3

**Estimated Complexity:** Large (8-16 hours)

---

### Story P8-2.5: Add Frame Sampling Strategy Selection in Settings

As a **user**,
I want **to choose between uniform and adaptive frame sampling**,
So that **I can optimize analysis for my specific camera content**.

**Acceptance Criteria:**

**Given** I am on Settings → General tab
**When** I see the "Frame Sampling Strategy" setting
**Then** I should be able to select from:
- **Uniform** (default) - Fixed interval extraction, predictable cost
- **Adaptive** - Content-aware selection, better for dynamic scenes
- **Hybrid** - Uniform extraction followed by adaptive filtering

**And** each option should show:
- Brief description of the strategy
- Recommended use case
- Trade-off summary (e.g., "Best for static cameras" vs "Best for busy areas")

**Technical Notes:**
- Add `frame_sampling_strategy` to system settings
- Create radio button group or select in settings UI
- Values: `uniform`, `adaptive`, `hybrid`
- Pass strategy to `frame_extraction_service.py`
- Default to `uniform` for backwards compatibility
- Consider per-camera override in future

**Prerequisites:** P8-2.4

**Estimated Complexity:** Small (2-4 hours)

---

## Epic P8-3: AI & Settings Improvements

**Goal:** Enhance AI prompt refinement workflow and improve settings UX with conditional form display.

**Business Value:** Users can optimize AI prompts using feedback data, and settings are cleaner with context-aware visibility.

**FR Coverage:** FR6, FR7, FR11

---

### Story P8-3.1: Hide MQTT Form When Integration Disabled

As a **user**,
I want **MQTT configuration fields hidden when the integration is disabled**,
So that **the settings page is less cluttered and shows only relevant options**.

**Acceptance Criteria:**

**Given** I am on Settings → Integrations or Home Assistant tab
**When** the "Enable MQTT Integration" toggle is OFF
**Then** all MQTT configuration fields should be hidden:
- Broker Host
- Broker Port
- Username
- Password
- Topic Prefix
- TLS settings
- Test Connection button

**And** when the toggle is switched ON:
- All MQTT fields should animate into view smoothly
- Previously saved values should be preserved and displayed
- Form validation should only apply to visible fields

**Technical Notes:**
- Update `MQTTSettings.tsx` or `HomeAssistantSettings.tsx` component
- Use conditional rendering based on `enabled` state
- Add CSS transition for smooth show/hide animation
- Ensure form state management doesn't reset values when hidden
- Test that saving with hidden fields doesn't clear MQTT config

**Prerequisites:** None

**Estimated Complexity:** Small (1-2 hours)

---

### Story P8-3.2: Add Full Motion Video Download Toggle

As a **user**,
I want **to optionally download and store full motion videos from Protect**,
So that **I can review complete clips, not just extracted frames**.

**Acceptance Criteria:**

**Given** I am on Settings → General tab
**When** I see the "Store Motion Videos" toggle
**Then** I should be able to enable full video storage

**And** when enabled:
- A storage warning modal should appear explaining disk usage implications
- Modal text: "Motion videos can consume significant storage (10-50MB per event). Ensure adequate disk space."
- Videos should be downloaded when Protect events are captured
- Videos stored in `data/videos/{event_id}.mp4`
- Videos should follow same retention policy as events

**And** on event cards when video is available:
- Show video icon/indicator
- Clicking opens video modal with:
  - Video player (HTML5)
  - Download button
  - Close button

**Technical Notes:**
- Add `store_motion_videos` to system settings
- Modify `protect_event_handler.py` to download clips via uiprotect
- Add `video_path` column to events table (nullable)
- Create `VideoPlayerModal` component
- Add video cleanup to retention job
- Consider storage monitoring/warning when disk usage high
- Use streaming for large videos to avoid memory issues

**Prerequisites:** None

**Estimated Complexity:** Large (8-16 hours)

---

### Story P8-3.3: Implement AI-Assisted Prompt Refinement

As a **user**,
I want **AI to suggest prompt improvements based on my feedback data**,
So that **I can optimize descriptions without manual trial-and-error**.

**Acceptance Criteria:**

**Given** I am on Settings → AI Models tab in the AI Description Prompt section
**When** I click "Refine Prompt with AI" button
**Then** the system should:
- Gather current prompt template
- Collect AI Accuracy feedback data (thumbs up/down, corrections)
- Send to position 1 AI provider with meta-prompt
- Open modal showing AI-suggested revised prompt

**And** the refinement modal should have:
- Read-only view of current prompt
- Editable text area with AI-suggested prompt
- "Resubmit" button to iterate on refinement
- "Accept" button to save the new prompt
- "Cancel" button to discard changes
- Character count indicator

**And** the meta-prompt should:
- Explain the context (home security camera descriptions)
- Include sample of positive feedback (thumbs up events)
- Include sample of negative feedback (thumbs down + corrections)
- Ask AI to improve prompt based on patterns

**Technical Notes:**
- Create `PromptRefinementModal` component
- Add `POST /api/v1/ai/refine-prompt` endpoint
- Gather feedback data: `SELECT * FROM events WHERE feedback IS NOT NULL LIMIT 50`
- Use position 1 AI provider from settings
- Structure meta-prompt to analyze feedback patterns
- Store prompt history for rollback (optional)
- Add loading state during AI processing

**Prerequisites:** None

**Estimated Complexity:** Large (8-16 hours)

---

## Epic P8-4: Native Apple Apps Foundation

**Goal:** Research and architect the foundation for native Apple device applications and cloud relay infrastructure.

**Business Value:** Enable future mobile/wearable access to ArgusAI from anywhere, expanding use cases significantly.

**FR Coverage:** FR12, FR13

---

### Story P8-4.1: Research Native Apple App Technologies

As a **product team**,
I want **a comprehensive research document on Apple app development approaches**,
So that **we can make informed technology decisions**.

**Acceptance Criteria:**

**Given** the need for apps on iPhone, iPad, Watch, Apple TV, and macOS
**When** research is complete
**Then** a document should cover:

**Technology Options:**
- SwiftUI (native, cross-Apple-platform code sharing)
- React Native (JavaScript, cross-platform including Android)
- Flutter (Dart, cross-platform)
- Capacitor/Ionic (web-based hybrid)

**Per-Platform Considerations:**
- iPhone: Push notifications, background refresh, widgets
- iPad: Split view, larger layouts, Apple Pencil
- Apple Watch: Complications, notifications, glances, limited UI
- Apple TV: Focus-based navigation, remote control, big screen
- macOS: Menu bar app, notification center, keyboard shortcuts

**API Requirements:**
- Authentication (how to securely store credentials)
- Real-time updates (WebSocket vs push)
- Image/video streaming
- Offline capabilities

**Recommendation:** Which approach best fits ArgusAI's needs

**Technical Notes:**
- Create `docs/research/apple-apps-technology.md`
- Include pros/cons table for each approach
- Estimate development effort per platform
- Consider team skills and maintainability
- Research App Store requirements and review process

**Prerequisites:** None

**Estimated Complexity:** Medium (4-8 hours research)

---

### Story P8-4.2: Design Cloud Relay Architecture

As a **architect**,
I want **a detailed design for the cloud relay service**,
So that **Apple apps can connect to local ArgusAI instances remotely**.

**Acceptance Criteria:**

**Given** the need for remote connectivity without port forwarding
**When** the architecture design is complete
**Then** a document should cover:

**Relay Architecture:**
- Connection flow (app → relay → local ArgusAI)
- Authentication and device pairing mechanism
- End-to-end encryption approach
- WebSocket or HTTP/2 tunneling

**Cloud Provider Options:**
- AWS (API Gateway, Lambda, WebSocket API)
- Google Cloud (Cloud Run, Cloud Functions)
- Cloudflare Tunnel (existing solution)
- Self-hosted relay server

**Security Considerations:**
- Device registration and pairing codes
- Token-based authentication
- Certificate pinning
- Rate limiting and abuse prevention

**Performance Optimization:**
- Thumbnail compression for mobile
- Video streaming optimization
- Connection keepalive strategies
- Fallback to local network when available

**Cost Estimates:** Per-user monthly costs for each provider option

**Technical Notes:**
- Create `docs/architecture/cloud-relay-design.md`
- Include sequence diagrams for connection flow
- Document API contracts between components
- Consider privacy implications (what data touches cloud)
- Plan for scaling (100 users, 1000 users, 10000 users)

**Prerequisites:** P8-4.1

**Estimated Complexity:** Medium (4-8 hours)

---

### Story P8-4.3: Create ArgusAI API Specification for Mobile

As a **developer**,
I want **a comprehensive API specification for mobile app consumption**,
So that **app developers have clear contracts to implement against**.

**Acceptance Criteria:**

**Given** the existing backend API
**When** the mobile API spec is complete
**Then** documentation should include:

**Authentication Endpoints:**
- `POST /api/v1/mobile/auth/pair` - Device pairing with code
- `POST /api/v1/mobile/auth/token` - Get access token
- `POST /api/v1/mobile/auth/refresh` - Refresh token

**Event Endpoints (mobile-optimized):**
- `GET /api/v1/mobile/events` - Paginated events with thumbnails
- `GET /api/v1/mobile/events/{id}` - Single event detail
- `GET /api/v1/mobile/events/recent` - Last N events (for widgets)

**Camera Endpoints:**
- `GET /api/v1/mobile/cameras` - Camera list with status
- `GET /api/v1/mobile/cameras/{id}/snapshot` - Current frame (compressed)

**Push Notification Registration:**
- `POST /api/v1/mobile/push/register` - Register APNS token
- `DELETE /api/v1/mobile/push/unregister` - Unregister device

**WebSocket Endpoint:**
- `wss://relay/ws/mobile` - Real-time event stream

**Technical Notes:**
- Create OpenAPI/Swagger spec in `docs/api/mobile-api.yaml`
- Design for bandwidth efficiency (mobile networks)
- Include response size estimates
- Document rate limits per endpoint
- Consider GraphQL for flexible queries (future)

**Prerequisites:** P8-4.1

**Estimated Complexity:** Medium (4-8 hours)

---

### Story P8-4.4: Prototype iPhone App Structure

As a **developer**,
I want **a basic iPhone app prototype demonstrating core connectivity**,
So that **we can validate the architecture before full development**.

**Acceptance Criteria:**

**Given** the technology decision from P8-4.1
**When** the prototype is complete
**Then** the app should demonstrate:

**Core Features:**
- Login/pairing screen with code entry
- Event list view showing recent events
- Event detail view with thumbnail and description
- Push notification receipt and display
- Pull-to-refresh for event updates

**Technical Validation:**
- Secure credential storage (Keychain)
- Background push notification handling
- Network error handling and retry
- Local network discovery (Bonjour/mDNS)

**Not In Scope (for prototype):**
- Full UI polish
- iPad/Watch/TV/Mac versions
- Video playback
- Settings screens

**Technical Notes:**
- Create new repo or subdirectory for iOS app
- Use SwiftUI for rapid prototyping
- Implement minimal API client
- Test on physical device (simulator has push limitations)
- Document findings and blockers
- Estimate effort for production-ready app

**Prerequisites:** P8-4.2, P8-4.3

**Estimated Complexity:** Large (16-24 hours)

---

## FR Coverage Matrix

| FR | Description | Epic | Story |
|----|-------------|------|-------|
| FR1 | Re-analyse function must work without errors | P8-1 | P8-1.1 |
| FR2 | Installation script must support non-ARM64 systems | P8-1 | P8-1.2 |
| FR3 | Push notifications must work for all events | P8-1 | P8-1.3 |
| FR4 | Store and display all frames used for AI analysis | P8-2 | P8-2.1, P8-2.2 |
| FR5 | Configurable number of frames for analysis | P8-2 | P8-2.3 |
| FR6 | Hide MQTT form fields when integration disabled | P8-3 | P8-3.1 |
| FR7 | Download and store full motion capture videos | P8-3 | P8-3.2 |
| FR8 | Implement adaptive/content-aware frame sampling | P8-2 | P8-2.4 |
| FR9 | Configurable frame sampling strategy selection | P8-2 | P8-2.5 |
| FR10 | Query-adaptive frame selection for re-analysis | P8-2 | Future (deferred - P4 priority) |
| FR11 | AI-assisted prompt refinement using accuracy feedback | P8-3 | P8-3.3 |
| FR12 | Native Apple device applications | P8-4 | P8-4.1, P8-4.4 |
| FR13 | Cloud relay service for remote connectivity | P8-4 | P8-4.2, P8-4.3 |

**Note:** FR10 (Query-Adaptive Frame Selection) is P4 priority and deferred to a future phase.

---

## Summary

### Epic Breakdown Summary

**Epic P8-1: Bug Fixes & Stability** (3 stories)
- Critical P2 bugs affecting re-analysis, installation, and push notifications
- Estimated: 8-16 hours total
- No dependencies, can start immediately

**Epic P8-2: Video Analysis Enhancements** (5 stories)
- Frame storage, display, and adaptive sampling
- Estimated: 20-40 hours total
- Sequential dependencies within epic

**Epic P8-3: AI & Settings Improvements** (3 stories)
- UX polish and AI prompt refinement
- Estimated: 17-34 hours total
- Mostly independent stories

**Epic P8-4: Native Apple Apps Foundation** (4 stories)
- Research, architecture, and prototype
- Estimated: 28-48 hours total
- Sequential dependencies, research-first approach

### Recommended Execution Order

1. **P8-1 (Bug Fixes)** - Start first, highest priority, enables reliable usage
2. **P8-3.1 (MQTT Hide)** - Quick win, low effort
3. **P8-2.1 → P8-2.2** - Frame storage and gallery
4. **P8-2.3** - Configurable frame count
5. **P8-3.3** - AI prompt refinement (high value)
6. **P8-2.4 → P8-2.5** - Adaptive sampling (complex)
7. **P8-3.2** - Video storage (large effort)
8. **P8-4** - Apple apps foundation (research phase)

### Total Estimated Effort

- **Minimum:** 73 hours
- **Maximum:** 138 hours
- **Stories:** 15

---

_For implementation: Use the `create-story` workflow to generate individual story implementation plans from this epic breakdown._

_This document will be updated after UX Design and Architecture workflows to incorporate interaction details and technical decisions._
