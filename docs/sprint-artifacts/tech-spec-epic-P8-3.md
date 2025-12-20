# Epic Technical Specification: AI & Settings Improvements

Date: 2025-12-20
Author: Brent
Epic ID: P8-3
Status: Draft

---

## Overview

Epic P8-3 enhances the ArgusAI settings experience and adds AI-powered prompt optimization. This epic addresses three distinct improvements: hiding irrelevant MQTT configuration when disabled (UX polish), enabling optional full motion video storage from Protect cameras, and implementing AI-assisted prompt refinement that uses user feedback data to suggest prompt improvements.

These enhancements address backlog items IMP-008, FF-019, and FF-023, improving settings usability and enabling users to optimize AI descriptions through an intelligent feedback loop.

## Objectives and Scope

### In Scope

- **P8-3.1**: Conditionally hide MQTT form fields when integration toggle is OFF
- **P8-3.2**: Add toggle to download/store full motion videos with storage warning and video player modal
- **P8-3.3**: Create AI-assisted prompt refinement workflow using feedback data

### Out of Scope

- MQTT functionality changes (only visibility)
- Video transcoding or format conversion
- Automated prompt optimization (user must approve changes)
- Video streaming to external services

## System Architecture Alignment

### Architecture Decisions (from architecture-phase8.md)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Video Storage | Original MP4 from Protect | No re-encoding overhead |
| Video Location | `data/videos/{event_id}.mp4` | Consistent with frame storage |
| Video Format | MP4 (H.264) | Protect native format |

### Components Referenced

| Component | Location | Stories Affected |
|-----------|----------|------------------|
| MQTT/Home Assistant Settings | `frontend/components/settings/HomeAssistantSettings.tsx` | P8-3.1 |
| General Settings | `frontend/components/settings/GeneralSettings.tsx` | P8-3.2 |
| Protect Event Handler | `backend/app/services/protect_event_handler.py` | P8-3.2 |
| AI Settings | `frontend/components/settings/AISettings.tsx` | P8-3.3 |
| AI Service | `backend/app/services/ai_service.py` | P8-3.3 |
| Events API | `backend/app/api/v1/events.py` | P8-3.2 |
| AI API | `backend/app/api/v1/ai.py` | P8-3.3 |

### New Components

| Component | Location | Purpose |
|-----------|----------|---------|
| VideoStorageService | `backend/app/services/video_storage_service.py` | Download/store videos |
| VideoPlayerModal | `frontend/components/video/VideoPlayerModal.tsx` | Video playback + download |
| PromptRefinementModal | `frontend/components/settings/PromptRefinementModal.tsx` | AI prompt refinement UI |

---

## Detailed Design

### Services and Modules

| Service/Module | Responsibility | Stories |
|----------------|----------------|---------|
| `HomeAssistantSettings.tsx` | Conditional MQTT field visibility | P8-3.1 |
| `VideoStorageService` | Download clips from Protect, store locally | P8-3.2 |
| `protect_event_handler.py` | Trigger video download when enabled | P8-3.2 |
| `VideoPlayerModal` | HTML5 video player with download button | P8-3.2 |
| `ai.py` (API) | New `/refine-prompt` endpoint | P8-3.3 |
| `PromptRefinementModal` | Display and iterate on AI suggestions | P8-3.3 |

### Data Models and Contracts

#### Modified Model: Event

```python
# Add to backend/app/models/event.py

# New field for video storage
video_path = Column(String, nullable=True)  # Relative path: videos/{event_id}.mp4
```

#### New Settings Keys

```python
# System settings schema additions
{
    "store_motion_videos": False,           # Enable video storage
    "video_retention_days": 30,             # Separate from event retention
}
```

#### Prompt Refinement Request/Response

```python
# backend/app/schemas/ai.py

class PromptRefinementRequest(BaseModel):
    current_prompt: str
    include_feedback: bool = True
    max_feedback_samples: int = 50

class PromptRefinementResponse(BaseModel):
    suggested_prompt: str
    changes_summary: str
    feedback_analyzed: int
    positive_examples: int
    negative_examples: int
```

### APIs and Interfaces

#### P8-3.2: Video Endpoints

**GET /api/v1/events/{event_id}/video**

Stream or download event video.

```
GET /api/v1/events/{event_id}/video

Response (200):
Content-Type: video/mp4
Content-Disposition: inline; filename="{event_id}.mp4"
[Binary MP4 data - streamed]

Response (404):
{
  "detail": "Video not available for this event"
}
```

**GET /api/v1/events/{event_id}/video/download**

Force download of video file.

```
GET /api/v1/events/{event_id}/video/download

Response (200):
Content-Type: video/mp4
Content-Disposition: attachment; filename="argusai-event-{event_id}.mp4"
[Binary MP4 data]
```

#### P8-3.3: Prompt Refinement Endpoint

**POST /api/v1/ai/refine-prompt**

Request AI to suggest prompt improvements.

```
POST /api/v1/ai/refine-prompt

Request:
{
  "current_prompt": "Describe what you see in this security camera image...",
  "include_feedback": true,
  "max_feedback_samples": 50
}

Response (200):
{
  "suggested_prompt": "You are analyzing a home security camera image. Describe:\n1. People present (count, appearance, actions)\n2. Vehicles (type, color, location)\n3. Packages or deliveries\n4. Any unusual or concerning activity\n\nBe specific and concise...",
  "changes_summary": "Added structured format, incorporated feedback patterns: users prefer specific person counts, vehicle details emphasized based on positive feedback",
  "feedback_analyzed": 47,
  "positive_examples": 32,
  "negative_examples": 15
}

Response (400):
{
  "detail": "No feedback data available for refinement"
}
```

### Workflows and Sequencing

#### P8-3.1: MQTT Form Visibility

```
User opens Settings > Home Assistant tab
  → Check MQTT enabled state
  → If enabled=false:
    → Hide all MQTT config fields
    → Show only "Enable MQTT Integration" toggle
  → If enabled=true:
    → Show all MQTT config fields with animation
    → Display saved values
  → User toggles MQTT enabled
    → If toggling ON:
      → Animate fields into view
      → Restore saved values
    → If toggling OFF:
      → Animate fields out of view
      → Preserve values in form state (don't clear)
```

#### P8-3.2: Video Storage Flow

```
Event captured from Protect
  → protect_event_handler.py receives event
  → Check system setting: store_motion_videos
  → If enabled:
    → Call video_storage_service.download_video(event)
      → Use uiprotect to get motion clip
      → Save to data/videos/{event_id}.mp4
      → Update event.video_path
    → Continue with normal processing
  → If disabled:
    → Skip video download
    → Continue with normal processing

User views Event Card with video
  → Check event.video_path exists
  → If exists:
    → Show video icon on card
    → User clicks video icon
    → VideoPlayerModal opens
    → Fetch video via streaming endpoint
    → Display HTML5 video player
    → User can play/pause/download
    → User closes modal
```

#### P8-3.3: Prompt Refinement Flow

```
User opens Settings > AI Models tab
  → User clicks "Refine Prompt with AI" button
  → PromptRefinementModal opens
  → Modal shows current prompt (read-only)
  → Modal shows "Analyzing feedback..." loading state
  → POST /api/v1/ai/refine-prompt
    → Backend gathers feedback data:
      SELECT * FROM events
      WHERE feedback IS NOT NULL
      ORDER BY created_at DESC
      LIMIT 50
    → Build meta-prompt with:
      - Current prompt
      - Positive examples (thumbs up)
      - Negative examples (thumbs down + corrections)
      - Instructions for improvement
    → Send to position 1 AI provider
    → Parse response
    → Return suggested prompt
  → Modal displays:
    → AI-suggested prompt (editable)
    → Changes summary
    → Feedback stats
  → User options:
    → "Resubmit" - Send current edit back for more refinement
    → "Accept" - Save as new prompt
    → "Cancel" - Discard and close
```

---

## Non-Functional Requirements

### Performance

| Requirement | Target | Measurement |
|-------------|--------|-------------|
| MQTT form toggle animation | <300ms | CSS transition |
| Video download from Protect | <30 seconds for 30s clip | End-to-end timing |
| Video streaming start | <2 seconds | Time to first byte |
| Prompt refinement response | <15 seconds | AI processing time |

### Security

- Video files accessible only via authenticated API
- No direct filesystem access to videos
- MQTT credentials remain encrypted when hidden
- Prompt refinement uses existing AI provider authentication

### Reliability/Availability

- Video download failure should not block event processing
- Video streaming should support range requests for seeking
- Prompt refinement failure shows clear error message
- All modals handle loading and error states gracefully

### Observability

| Metric | Type | Description |
|--------|------|-------------|
| `videos_stored_total` | Counter | Total videos saved |
| `videos_storage_bytes` | Gauge | Total video storage size |
| `video_download_duration_ms` | Histogram | Protect download time |
| `prompt_refinements_requested` | Counter | Refinement usage |
| `prompt_refinements_accepted` | Counter | Refinements applied |

---

## Dependencies and Integrations

### Backend Dependencies

```
# requirements.txt - existing (no changes needed)
uiprotect>=6.0.0           # Video clip download
aiofiles>=23.0.0           # Async file operations
```

### Frontend Dependencies

```json
// package.json - no new dependencies needed
// Uses native HTML5 video element
```

### External Integrations

| Integration | Purpose | Story |
|-------------|---------|-------|
| UniFi Protect | Download motion clips | P8-3.2 |
| AI Providers | Prompt refinement | P8-3.3 |

### File System

```
data/
├── frames/                # From P8-2
├── thumbnails/            # Existing
└── videos/                # NEW directory
    └── {event_id}.mp4
```

---

## Acceptance Criteria (Authoritative)

### P8-3.1: Hide MQTT Form When Integration Disabled

| AC# | Acceptance Criteria |
|-----|---------------------|
| AC1.1 | Given MQTT toggle OFF, when viewing settings, then all MQTT config fields hidden |
| AC1.2 | Given MQTT toggle OFF, when toggling ON, then fields animate into view |
| AC1.3 | Given MQTT toggle ON, when toggling OFF, then fields animate out of view |
| AC1.4 | Given fields hidden, when re-enabling, then previously saved values preserved |
| AC1.5 | Given hidden fields, when saving settings, then MQTT config not cleared |

### P8-3.2: Add Full Motion Video Download Toggle

| AC# | Acceptance Criteria |
|-----|---------------------|
| AC2.1 | Given Settings > General, when viewing, then "Store Motion Videos" toggle visible |
| AC2.2 | Given toggle change, when enabling, then storage warning modal appears |
| AC2.3 | Given warning modal, when user confirms, then setting saved |
| AC2.4 | Given video storage enabled, when Protect event captured, then video downloaded |
| AC2.5 | Given video downloaded, when stored, then saved to `data/videos/{event_id}.mp4` |
| AC2.6 | Given event with video, when viewing card, then video icon displayed |
| AC2.7 | Given video icon click, when modal opens, then video player displayed |
| AC2.8 | Given video player, when playing, then video streams correctly |
| AC2.9 | Given video modal, when download clicked, then file downloads |
| AC2.10 | Given retention policy, when cleanup runs, then old videos deleted |

### P8-3.3: Implement AI-Assisted Prompt Refinement

| AC# | Acceptance Criteria |
|-----|---------------------|
| AC3.1 | Given Settings > AI Models, when viewing, then "Refine Prompt with AI" button visible |
| AC3.2 | Given button click, when modal opens, then current prompt shown read-only |
| AC3.3 | Given modal open, when processing, then loading indicator displayed |
| AC3.4 | Given processing complete, when response received, then suggested prompt shown |
| AC3.5 | Given suggested prompt, when viewing, then changes summary displayed |
| AC3.6 | Given suggested prompt, when editing, then text area is editable |
| AC3.7 | Given "Resubmit" click, when processing, then new refinement requested |
| AC3.8 | Given "Accept" click, when confirmed, then new prompt saved to settings |
| AC3.9 | Given "Cancel" click, when confirmed, then modal closes without saving |
| AC3.10 | Given no feedback data, when requested, then helpful error message shown |

---

## Traceability Mapping

| AC | Spec Section | Component(s) | Test Idea |
|----|--------------|--------------|-----------|
| AC1.1-1.3 | Workflows | HomeAssistantSettings.tsx | Component tests for visibility |
| AC1.4-1.5 | Workflows | HomeAssistantSettings.tsx | Test state persistence |
| AC2.1-2.3 | APIs | GeneralSettings.tsx | Component test for toggle + modal |
| AC2.4-2.5 | Workflows | VideoStorageService, protect_event_handler | Integration test video download |
| AC2.6-2.9 | APIs | EventCard, VideoPlayerModal | Component tests for player |
| AC2.10 | Reliability | retention job | Test video cleanup |
| AC3.1-3.3 | APIs | AISettings, PromptRefinementModal | Component tests |
| AC3.4-3.6 | Workflows | PromptRefinementModal | Test refinement flow |
| AC3.7-3.9 | Workflows | PromptRefinementModal | Test user actions |
| AC3.10 | APIs | ai.py | Test empty feedback case |

---

## Risks, Assumptions, Open Questions

### Risks

| ID | Risk | Impact | Mitigation |
|----|------|--------|------------|
| R1 | Video storage consumes significant disk space | High | Storage warning, separate retention, monitoring |
| R2 | Protect video download may fail or timeout | Medium | Retry logic, don't block event processing |
| R3 | AI prompt refinement may suggest poor prompts | Medium | User must accept, show preview |
| R4 | Position 1 AI provider may be expensive for refinement | Low | Single call per refinement, user-initiated |

### Assumptions

| ID | Assumption |
|----|------------|
| A1 | uiprotect library can download motion clips |
| A2 | Events have feedback field for thumbs up/down |
| A3 | AI providers can handle meta-prompt for refinement |
| A4 | HTML5 video element supports MP4 from Protect |

### Open Questions

| ID | Question | Owner | Status |
|----|----------|-------|--------|
| Q1 | Should video retention be separate from event retention? | PM | Yes - architecture specifies 30 days |
| Q2 | What's typical Protect clip size? | Dev | 5-30MB based on duration |
| Q3 | Should we limit refinement to avoid AI costs? | PM | User-initiated only, no auto |

---

## Test Strategy Summary

### Test Levels

| Level | Framework | Coverage |
|-------|-----------|----------|
| Unit | pytest | VideoStorageService, prompt refinement logic |
| Integration | pytest + TestClient | Video and AI endpoints |
| Component | React Testing Library | Modals, settings components |
| E2E | Manual | Full video and refinement flows |

### Key Test Cases

**P8-3.1 (MQTT Visibility):**
- `test_mqtt_fields_hidden_when_disabled`
- `test_mqtt_fields_show_on_enable`
- `test_mqtt_values_preserved_after_toggle`

**P8-3.2 (Video Storage):**
- `test_video_download_from_protect`
- `test_video_stored_correctly`
- `test_video_streaming_endpoint`
- `test_video_player_modal_opens`
- `test_video_cleanup_on_retention`

**P8-3.3 (Prompt Refinement):**
- `test_refine_prompt_endpoint`
- `test_refinement_modal_flow`
- `test_refinement_with_no_feedback`
- `test_prompt_save_on_accept`

### Edge Cases

- Video download timeout
- Corrupt video file
- Empty feedback dataset
- AI provider error during refinement
- Large prompt text handling
- MQTT form state during rapid toggles
