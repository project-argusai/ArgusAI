# Live Object AI Classifier - Phase 3 Epic Breakdown

**Author:** Brent
**Date:** 2025-12-05
**Project Level:** Brownfield (extending Phase 1 + Phase 2)
**Target Scale:** Home security / AI vision analysis

---

## Overview

This document provides the complete epic and story breakdown for Phase 3, decomposing the requirements from the [PRD-phase3.md](./PRD-phase3.md) into implementable stories.

**Living Document Notice:** This is the initial version. It will be updated after Architecture workflow adds technical details to stories.

### Epic Summary

| Epic | Title | Scope | Stories | FRs Covered |
|------|-------|-------|---------|-------------|
| **P3-1** | Motion Clip Download Infrastructure | MVP | 5 | FR1-FR5 |
| **P3-2** | Multi-Frame Analysis Mode | MVP | 6 | FR6-FR13 |
| **P3-3** | Analysis Mode Configuration | MVP | 5 | FR14-FR18, FR38 |
| **P3-4** | Native Video Analysis | Growth | 5 | FR19-FR22, FR42 |
| **P3-5** | Audio Analysis for Doorbells | Growth | 3 | FR23-FR26 |
| **P3-6** | Confidence Scoring & Quality | Growth | 4 | FR27-FR31, FR40 |
| **P3-7** | Cost Monitoring Dashboard | Growth | 6 | FR32-FR37, FR39, FR41 |

**Total:** 7 Epics, 34 Stories

---

## Functional Requirements Inventory

### Video Clip Management (FR1-FR5)
- **FR1:** System can download motion clips from UniFi Protect for any event
- **FR2:** System stores clips temporarily during analysis
- **FR3:** System automatically cleans up clips after successful analysis
- **FR4:** System retries failed clip downloads with exponential backoff
- **FR5:** System handles clip download failures gracefully with fallback to snapshot

### Frame Extraction (FR6-FR9)
- **FR6:** System can extract multiple frames from video clips
- **FR7:** System selects frames at configurable intervals (e.g., evenly spaced)
- **FR8:** System can extract 3-10 frames per clip based on configuration
- **FR9:** System filters out blurry or empty frames when possible

### Multi-Image AI Analysis (FR10-FR13)
- **FR10:** AI service accepts multiple images for a single analysis request
- **FR11:** AI service uses mode-specific prompts optimized for frame sequences
- **FR12:** AI service supports multi-image across all configured providers
- **FR13:** System tracks token/cost usage for multi-image requests

### Analysis Mode Configuration (FR14-FR18)
- **FR14:** Each camera has a configurable analysis mode setting
- **FR15:** Users can choose between single_frame, multi_frame, and video_native modes
- **FR16:** UI displays mode descriptions, trade-offs, and estimated costs
- **FR17:** System applies configured mode when processing events from that camera
- **FR18:** System falls back to simpler modes if configured mode fails

### Native Video Analysis - Growth (FR19-FR22)
- **FR19:** System can send video clips directly to video-capable AI providers
- **FR20:** System detects which providers support video input
- **FR21:** System converts video format if provider requires specific format
- **FR22:** System handles video size/duration limits per provider

### Audio Analysis - Growth (FR23-FR26)
- **FR23:** System can extract audio track from video clips
- **FR24:** System can transcribe audio using speech-to-text
- **FR25:** System includes audio context in AI description prompt
- **FR26:** System handles clips with no audio gracefully

### Confidence Scoring - Growth (FR27-FR31)
- **FR27:** AI service returns confidence score with each description
- **FR28:** System detects vague or uncertain descriptions
- **FR29:** Low-confidence events are flagged in the dashboard
- **FR30:** Users can trigger re-analysis with higher-quality mode
- **FR31:** Confidence scores are stored with events for analytics

### Cost Monitoring - Growth (FR32-FR37)
- **FR32:** System tracks AI API usage per request
- **FR33:** System aggregates usage by camera, day, and provider
- **FR34:** Dashboard displays current usage and costs
- **FR35:** Users can set daily/monthly cost caps
- **FR36:** System alerts users when approaching cost limits
- **FR37:** System can pause AI analysis when cap is reached

### Event Display Updates (FR38-FR42)
- **FR38:** Event cards show which analysis mode was used
- **FR39:** Event cards can display key frames used for analysis (optional)
- **FR40:** Event cards show confidence indicator when available
- **FR41:** Timeline supports filtering by analysis mode
- **FR42:** Event cards show which AI provider generated the description

---

## FR Coverage Map

| FR | Description | Epic | Story |
|----|-------------|------|-------|
| FR1 | Download motion clips from Protect | P3-1 | P3-1.1 |
| FR2 | Store clips temporarily | P3-1 | P3-1.2 |
| FR3 | Auto cleanup clips | P3-1 | P3-1.2 |
| FR4 | Retry with exponential backoff | P3-1 | P3-1.3 |
| FR5 | Fallback to snapshot on failure | P3-1 | P3-1.4 |
| FR6 | Extract multiple frames | P3-2 | P3-2.1 |
| FR7 | Configurable frame intervals | P3-2 | P3-2.1 |
| FR8 | Extract 3-10 frames | P3-2 | P3-2.1 |
| FR9 | Filter blurry frames | P3-2 | P3-2.2 |
| FR10 | AI accepts multiple images | P3-2 | P3-2.3 |
| FR11 | Mode-specific prompts | P3-2 | P3-2.4 |
| FR12 | Multi-image all providers | P3-2 | P3-2.3 |
| FR13 | Track token usage | P3-2 | P3-2.5 |
| FR14 | Camera analysis mode setting | P3-3 | P3-3.1 |
| FR15 | Three mode choices | P3-3 | P3-3.2 |
| FR16 | UI with trade-off info | P3-3 | P3-3.3 |
| FR17 | Apply mode on processing | P3-3 | P3-3.5 |
| FR18 | Fallback chain | P3-3 | P3-3.5 |
| FR19 | Send video to providers | P3-4 | P3-4.2, P3-4.3 |
| FR20 | Detect provider capabilities | P3-4 | P3-4.1 |
| FR21 | Convert video format | P3-4 | P3-4.2, P3-4.3 |
| FR22 | Handle size/duration limits | P3-4 | P3-4.2, P3-4.3 |
| FR23 | Extract audio from clips | P3-5 | P3-5.1 |
| FR24 | Transcribe audio | P3-5 | P3-5.2 |
| FR25 | Include audio in prompt | P3-5 | P3-5.3 |
| FR26 | Handle no audio | P3-5 | P3-5.1 |
| FR27 | Return confidence score | P3-6 | P3-6.1 |
| FR28 | Detect vague descriptions | P3-6 | P3-6.2 |
| FR29 | Flag low confidence | P3-6 | P3-6.3 |
| FR30 | Re-analyze action | P3-6 | P3-6.4 |
| FR31 | Store confidence scores | P3-6 | P3-6.1 |
| FR32 | Track AI usage | P3-7 | P3-7.1 |
| FR33 | Aggregate by camera/day/provider | P3-7 | P3-7.1 |
| FR34 | Display costs dashboard | P3-7 | P3-7.2 |
| FR35 | Set cost caps | P3-7 | P3-7.3 |
| FR36 | Alert on approaching limits | P3-7 | P3-7.4 |
| FR37 | Pause on cap reached | P3-7 | P3-7.3 |
| FR38 | Show analysis mode on cards | P3-3 | P3-3.4 |
| FR39 | Display key frames | P3-7 | P3-7.5 |
| FR40 | Show confidence indicator | P3-6 | P3-6.3 |
| FR41 | Filter by analysis mode | P3-7 | P3-7.6 |
| FR42 | Show AI provider on cards | P3-4 | P3-4.5 |

---

## Epic P3-1: Motion Clip Download Infrastructure

**Goal:** Enable the system to download motion video clips from UniFi Protect for any smart detection event, providing the foundation for all video-based analysis features.

**FRs Covered:** FR1, FR2, FR3, FR4, FR5

---

### Story P3-1.1: Implement ClipService for Protect Video Downloads

**As a** system operator,
**I want** the backend to download motion clips from UniFi Protect,
**So that** video content is available for AI analysis.

**Acceptance Criteria:**

**Given** a Protect smart detection event with camera_id and event timestamps
**When** ClipService.download_clip() is called
**Then** the system downloads the MP4 clip via uiprotect library
**And** saves it to `data/clips/{event_id}.mp4`
**And** returns the file path on success or None on failure

**Given** the uiprotect library is available
**When** downloading a clip for a 10-30 second motion event
**Then** download completes within 10 seconds (NFR1)
**And** uses existing controller credentials from ProtectService

**Given** clip download is requested
**When** the Protect controller is unreachable
**Then** the method returns None without raising exception
**And** logs the failure with event_id and error details

**Prerequisites:** None (foundational story)

**Technical Notes:**
- Create `backend/app/services/clip_service.py`
- Use uiprotect's `get_camera_video()` or equivalent method (spike needed)
- Store clips in `data/clips/` directory (create if not exists)
- Filename pattern: `{event_id}.mp4`
- Add PyAV to requirements if not present for video handling
- Reuse ProtectService's authenticated client connection

---

### Story P3-1.2: Add Temporary Clip Storage Management

**As a** system administrator,
**I want** temporary clip storage to be automatically managed,
**So that** disk space doesn't fill up with old video files.

**Acceptance Criteria:**

**Given** a clip file exists in `data/clips/`
**When** `ClipService.cleanup_clip(event_id)` is called
**Then** the file `{event_id}.mp4` is deleted
**And** method returns True on success, False if file not found

**Given** clips older than 1 hour exist (NFR7)
**When** `ClipService.cleanup_old_clips()` is called
**Then** all clips with mtime > 1 hour are deleted
**And** returns count of deleted files

**Given** the clips directory
**When** total size exceeds 1GB (NFR9)
**Then** oldest clips are deleted until under 900MB
**And** warning is logged about storage pressure

**Given** system startup
**When** ClipService initializes
**Then** `data/clips/` directory is created if not exists
**And** cleanup_old_clips() runs to clear stale files

**Prerequisites:** P3-1.1

**Technical Notes:**
- Add `CLIP_STORAGE_PATH` to settings (default: `data/clips`)
- Add `MAX_CLIP_AGE_HOURS` setting (default: 1)
- Add `MAX_CLIP_STORAGE_MB` setting (default: 1024)
- Use pathlib for cross-platform path handling
- Schedule cleanup in background task (every 15 minutes)

---

### Story P3-1.3: Implement Retry Logic with Exponential Backoff

**As a** system,
**I want** failed clip downloads to retry automatically,
**So that** transient network issues don't cause permanent failures.

**Acceptance Criteria:**

**Given** a clip download fails on first attempt
**When** retry logic is enabled
**Then** system retries up to 3 times (NFR5)
**And** waits 1s, 2s, 4s between attempts (exponential backoff)
**And** logs each retry attempt with attempt number

**Given** all 3 retry attempts fail
**When** final attempt completes
**Then** method returns None
**And** logs "Clip download failed after 3 attempts" with event_id

**Given** retry attempt 2 succeeds
**When** download completes
**Then** method returns the file path
**And** logs "Clip download succeeded on attempt 2"

**Prerequisites:** P3-1.1

**Technical Notes:**
- Use tenacity library (already in requirements) or implement manually
- Decorator pattern: `@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=4))`
- Catch specific exceptions: ConnectionError, TimeoutError, uiprotect exceptions
- Don't retry on 404/not-found errors (clip doesn't exist)

---

### Story P3-1.4: Integrate Clip Download into Event Pipeline

**As a** system,
**I want** clip downloads to happen automatically for Protect events,
**So that** video is available when AI analysis needs it.

**Acceptance Criteria:**

**Given** a Protect smart detection event is received
**When** the event is processed by EventProcessor
**Then** ClipService.download_clip() is called before AI analysis
**And** clip path is passed to AI service if download succeeds

**Given** clip download fails after retries
**When** fallback is triggered (FR5)
**Then** system uses existing thumbnail/snapshot for AI analysis
**And** event is flagged with `fallback_reason: "clip_download_failed"`
**And** processing continues without interruption (NFR8)

**Given** clip download succeeds
**When** AI analysis completes
**Then** ClipService.cleanup_clip() is called
**And** temporary file is removed

**Given** multiple events arrive simultaneously
**When** clips are being downloaded
**Then** each event's clip download is independent
**And** one failure doesn't block others (NFR8)

**Prerequisites:** P3-1.1, P3-1.2, P3-1.3

**Technical Notes:**
- Modify `backend/app/services/event_processor.py`
- Add clip_path to event processing context
- Add `fallback_reason` field to Event model (migration needed)
- Ensure async/await for non-blocking downloads
- Consider download queue if >5 concurrent downloads

---

### Story P3-1.5: Add Clip Download API Endpoint for Testing

**As a** developer,
**I want** an API endpoint to test clip downloads,
**So that** I can verify Protect clip retrieval works correctly.

**Acceptance Criteria:**

**Given** a valid Protect camera_id and event timestamps
**When** `POST /api/v1/protect/test-clip-download` is called
**Then** system attempts to download a clip
**And** returns `{success: true, file_size_bytes: N, duration_seconds: N}`

**Given** clip download fails
**When** API endpoint is called
**Then** returns `{success: false, error: "description"}`
**And** HTTP 200 (test result, not server error)

**Given** camera_id doesn't belong to any controller
**When** API endpoint is called
**Then** returns `{success: false, error: "Camera not found in any Protect controller"}`

**Prerequisites:** P3-1.1

**Technical Notes:**
- Add to `backend/app/api/v1/protect.py`
- Endpoint for dev/testing only (consider auth requirement)
- Clean up test clip after response
- Return video metadata (duration, resolution) if available

---

## Epic P3-2: Multi-Frame Analysis Mode

**Goal:** Extract key frames from video clips and enable AI service to analyze multiple images together, producing richer descriptions that capture action and narrative.

**FRs Covered:** FR6, FR7, FR8, FR9, FR10, FR11, FR12, FR13

---

### Story P3-2.1: Implement FrameExtractor Service

**As a** system,
**I want** to extract multiple frames from video clips,
**So that** AI can analyze a sequence of images showing action over time.

**Acceptance Criteria:**

**Given** a valid MP4 clip file path
**When** `FrameExtractor.extract_frames(clip_path, frame_count=5)` is called
**Then** returns a list of 5 JPEG-encoded frame bytes
**And** extraction completes within 2 seconds for 10-second clips (NFR2)

**Given** a 10-second video clip
**When** extracting 5 frames with "evenly_spaced" strategy (FR7)
**Then** frames are extracted at 0s, 2.5s, 5s, 7.5s, 10s
**And** first and last frames are always included

**Given** frame_count parameter between 3-10 (FR8)
**When** extraction is called
**Then** exactly that many frames are returned
**And** spacing adjusts proportionally to clip duration

**Given** an invalid or corrupted video file
**When** extraction is attempted
**Then** returns empty list
**And** logs error with file path and reason

**Prerequisites:** P3-1.1 (clips available)

**Technical Notes:**
- Create `backend/app/services/frame_extractor.py`
- Use PyAV (av library) for video decoding - faster than OpenCV for this
- Output JPEG bytes at 80% quality (balance size/quality)
- Resize frames to max 1280px width for AI efficiency
- Handle various codecs: H.264, H.265

---

### Story P3-2.2: Add Blur Detection for Frame Filtering

**As a** system,
**I want** to filter out blurry or empty frames,
**So that** AI receives the clearest images for analysis.

**Acceptance Criteria:**

**Given** an extracted frame
**When** `FrameExtractor._is_frame_usable(frame)` is called
**Then** returns False if Laplacian variance < 100 (blurry)
**And** returns False if frame is >90% single color (empty/black)
**And** returns True for clear, content-rich frames

**Given** 5 frames extracted where 2 are blurry
**When** filtering is enabled (default)
**Then** blurry frames are replaced with adjacent timestamps
**And** at least `min_frames` (3) are always returned

**Given** all frames in a clip are blurry
**When** filtering runs
**Then** returns best available frames (highest variance)
**And** logs warning "All frames below quality threshold"

**Given** blur detection is disabled via parameter
**When** extraction is called with `filter_blur=False`
**Then** all extracted frames are returned regardless of quality

**Prerequisites:** P3-2.1

**Technical Notes:**
- Laplacian variance: `cv2.Laplacian(gray, cv2.CV_64F).var()`
- Single color detection: check std deviation of pixel values
- Keep blur detection optional (some users may prefer speed)
- Add `FRAME_BLUR_THRESHOLD` setting (default: 100)

---

### Story P3-2.3: Extend AIService for Multi-Image Analysis

**As a** system,
**I want** AIService to accept multiple images in one request,
**So that** AI can analyze frame sequences together.

**Acceptance Criteria:**

**Given** a list of 3-5 image bytes
**When** `AIService.describe_images(images: List[bytes], prompt: str)` is called
**Then** all images are sent to the AI provider in a single request
**And** returns a single description covering all frames

**Given** multi-image request to OpenAI
**When** API is called
**Then** images are sent as multiple image_url content blocks
**And** each image is base64 encoded with proper MIME type

**Given** multi-image request to Claude
**When** API is called
**Then** images are sent as multiple image content blocks
**And** uses claude-3-haiku or configured model

**Given** multi-image request to Gemini
**When** API is called
**Then** images are sent using Gemini's multi-part format
**And** handles Gemini's specific image requirements

**Given** multi-image request to Grok
**When** API is called
**Then** images are sent using Grok's vision API format

**Prerequisites:** None (extends existing AIService)

**Technical Notes:**
- Modify `backend/app/services/ai_service.py`
- Add `describe_images()` method alongside existing `describe_image()`
- Each provider has different multi-image API format
- OpenAI: array of content objects with type "image_url"
- Claude: array of content objects with type "image"
- Gemini: inline_data parts in contents array
- Grok: follows OpenAI-compatible format

---

### Story P3-2.4: Create Multi-Frame Prompts Optimized for Sequences

**As a** system,
**I want** specialized prompts for frame sequence analysis,
**So that** AI understands it's analyzing action over time.

**Acceptance Criteria:**

**Given** multi-frame analysis mode
**When** AI is called with multiple images
**Then** prompt explicitly states "These frames are from a security camera video, shown in chronological order"
**And** asks for description of "what happened" not just "what is shown"

**Given** 5 frames from a motion event
**When** multi-frame prompt is used
**Then** AI is instructed to describe:
  - Who/what is present
  - What action occurred (arrival, departure, delivery, etc.)
  - Direction of movement
  - Sequence of events
**And** response captures temporal narrative

**Given** frames showing a person
**When** multi-frame prompt processes them
**Then** description includes action verbs ("walked", "placed", "picked up")
**And** avoids static descriptions ("person is standing")

**Given** user's custom description prompt exists
**When** multi-frame analysis runs
**Then** custom prompt is appended after system's multi-frame instructions

**Prerequisites:** P3-2.3

**Technical Notes:**
- Create `MULTI_FRAME_SYSTEM_PROMPT` constant
- Example: "You are analyzing a sequence of {n} frames from a security camera, shown in chronological order. Describe what happened - focus on actions, movement direction, and the narrative of events. Be specific about what the subject did, not just what is visible."
- Store prompts in `backend/app/prompts/` or settings
- Allow prompt customization via settings

---

### Story P3-2.5: Track Token Usage for Multi-Image Requests

**As a** system administrator,
**I want** accurate token tracking for multi-image requests,
**So that** cost estimates remain accurate.

**Acceptance Criteria:**

**Given** a multi-image AI request completes
**When** usage is tracked
**Then** AIUsage record includes total tokens (input + output)
**And** token count reflects all images sent

**Given** OpenAI vision request with 5 images
**When** response is received
**Then** `usage.prompt_tokens` and `usage.completion_tokens` are recorded
**And** stored in ai_usage table with analysis_mode="multi_frame"

**Given** provider doesn't return token counts (some Gemini responses)
**When** usage is tracked
**Then** estimate tokens based on image count and response length
**And** flag estimate with `is_estimated: true`

**Given** cost tracking is enabled
**When** multi-image request completes
**Then** estimated cost is calculated using provider's per-token rates
**And** cost is stored with the AIUsage record

**Prerequisites:** P3-2.3

**Technical Notes:**
- Modify `backend/app/models/ai_usage.py` to add `analysis_mode` field
- Token estimation: ~85 tokens per image (low-res) or ~765 tokens (high-res) for OpenAI
- Claude: ~1,334 tokens per image
- Add migration for analysis_mode column
- Cost rates from architecture.md CostTracker

---

### Story P3-2.6: Integrate Multi-Frame Analysis into Event Pipeline

**As a** system,
**I want** events to use multi-frame analysis when clips are available,
**So that** users get richer descriptions automatically.

**Acceptance Criteria:**

**Given** a Protect event with successfully downloaded clip
**When** camera's analysis_mode is "multi_frame"
**Then** FrameExtractor extracts frames from clip
**And** AIService.describe_images() is called with frames
**And** event description captures the action narrative

**Given** frame extraction fails
**When** multi-frame analysis is attempted
**Then** system falls back to single thumbnail analysis
**And** event.fallback_reason = "frame_extraction_failed"

**Given** multi-frame AI request fails
**When** fallback is triggered
**Then** system retries with single-frame using thumbnail
**And** event.fallback_reason = "multi_frame_ai_failed"

**Given** event processing completes
**When** event is saved
**Then** event.analysis_mode records actual mode used
**And** event.frame_count_used records number of frames sent

**Prerequisites:** P3-1.4, P3-2.1, P3-2.3, P3-2.4

**Technical Notes:**
- Modify EventProcessor to check camera.analysis_mode
- Add `analysis_mode` and `frame_count_used` to Event model (migration)
- Fallback chain: multi_frame → single_frame (existing behavior)
- Latency target: 3x single-frame max (NFR3)

---

## Epic P3-3: Analysis Mode Configuration

**Goal:** Give users per-camera control over analysis depth, with clear trade-off explanations and automatic fallback behavior.

**FRs Covered:** FR14, FR15, FR16, FR17, FR18, FR38

---

### Story P3-3.1: Add Analysis Mode Field to Camera Model

**As a** system,
**I want** cameras to store their analysis mode preference,
**So that** each camera can be configured independently.

**Acceptance Criteria:**

**Given** the Camera database model
**When** schema is updated
**Then** `analysis_mode` field exists with type VARCHAR(20)
**And** valid values: 'single_frame', 'multi_frame', 'video_native'
**And** default value is 'single_frame' for existing cameras

**Given** a new camera is created
**When** no analysis_mode is specified
**Then** defaults to 'single_frame'

**Given** a Protect camera is discovered
**When** auto-added to system
**Then** defaults to 'multi_frame' (balanced choice per UX principles)

**Given** camera.analysis_mode is 'video_native'
**When** camera is non-Protect (RTSP/USB)
**Then** system treats as 'single_frame' (no clip source)

**Prerequisites:** None

**Technical Notes:**
- Add migration: `alembic revision -m "add_camera_analysis_mode"`
- Add `analysis_mode` to Camera model in `backend/app/models/camera.py`
- Add to CameraResponse schema in `backend/app/schemas/camera.py`
- Add to CameraUpdate schema for PATCH updates
- Consider adding `frame_count` field (default 5) for multi_frame mode

---

### Story P3-3.2: Add Analysis Mode to Camera API

**As a** user,
**I want** to update camera analysis mode via API,
**So that** I can configure each camera's analysis depth.

**Acceptance Criteria:**

**Given** `PATCH /api/v1/cameras/{id}` with `{"analysis_mode": "multi_frame"}`
**When** request is processed
**Then** camera's analysis_mode is updated
**And** response includes updated analysis_mode value

**Given** invalid analysis_mode value like "super_frame"
**When** PATCH request is made
**Then** returns 422 Validation Error
**And** message explains valid options

**Given** `GET /api/v1/cameras/{id}`
**When** response is returned
**Then** includes `analysis_mode` field

**Given** `GET /api/v1/cameras`
**When** listing all cameras
**Then** each camera includes `analysis_mode` field

**Prerequisites:** P3-3.1

**Technical Notes:**
- Update camera CRUD in `backend/app/api/v1/cameras.py`
- Add Literal type validation in schema: `Literal['single_frame', 'multi_frame', 'video_native']`
- Ensure Protect-only modes validated (video_native requires Protect source)

---

### Story P3-3.3: Build Analysis Mode Selector UI Component

**As a** user,
**I want** a clear UI to select analysis mode per camera,
**So that** I understand the trade-offs and can make informed choices.

**Acceptance Criteria:**

**Given** camera settings panel
**When** user views a Protect camera
**Then** Analysis Mode selector is visible with 3 options
**And** each option shows: name, quality level, speed, relative cost

**Given** analysis mode options displayed
**When** user hovers/focuses an option
**Then** tooltip explains: "Single Frame: Fastest, lowest cost. Uses event thumbnail only."
**And** "Multi-Frame: Balanced. Extracts 5 frames from video clip."
**And** "Video Native: Best quality, higher cost. Sends full video to AI."

**Given** user selects "Video Native" for non-Protect camera
**When** option is clicked
**Then** shows warning: "Video Native requires UniFi Protect camera"
**And** selection is prevented or shows as disabled

**Given** user changes analysis mode
**When** save is clicked
**Then** PATCH API updates camera
**And** success toast confirms change

**Prerequisites:** P3-3.2

**Technical Notes:**
- Create `frontend/components/cameras/AnalysisModeSelector.tsx`
- Use shadcn/ui RadioGroup or Select component
- Add to existing camera edit modal/panel
- Icons: single frame (image icon), multi-frame (images icon), video (video icon)
- Show cost indicators: $ (single), $$ (multi), $$$ (video)

---

### Story P3-3.4: Display Analysis Mode on Event Cards

**As a** user,
**I want** to see which analysis mode was used for each event,
**So that** I understand why description quality varies.

**Acceptance Criteria:**

**Given** an event card in the timeline
**When** event has analysis_mode stored
**Then** small badge shows mode: "SF" / "MF" / "VN"
**And** badge has appropriate icon

**Given** event used fallback (e.g., multi_frame → single_frame)
**When** event card is displayed
**Then** badge shows actual mode used (single_frame)
**And** subtle indicator shows fallback occurred
**And** tooltip explains: "Fell back to Single Frame: clip download failed"

**Given** event has no analysis_mode (legacy events)
**When** displayed
**Then** no badge shown or shows "—"

**Given** user clicks analysis mode badge
**When** interaction occurs
**Then** shows popover with full details:
  - Mode used
  - Frame count (if multi-frame)
  - Fallback reason (if any)
  - Tokens used

**Prerequisites:** P3-2.6 (events have analysis_mode)

**Technical Notes:**
- Create `frontend/components/events/AnalysisModeBadge.tsx`
- Add to EventCard component
- Colors: single=gray, multi=blue, video=purple
- Keep badges small to not clutter timeline

---

### Story P3-3.5: Implement Automatic Fallback Chain

**As a** system,
**I want** automatic fallback when configured mode fails,
**So that** events always get descriptions even if video analysis fails.

**Acceptance Criteria:**

**Given** camera configured for video_native
**When** video analysis fails (provider error, format issue)
**Then** system automatically tries multi_frame
**And** if that fails, tries single_frame
**And** event.fallback_reason records why each step failed

**Given** camera configured for multi_frame
**When** clip download fails
**Then** system falls back to single_frame using thumbnail
**And** event.fallback_reason = "clip_download_failed"

**Given** fallback chain exhausted (single_frame also fails)
**When** AI is completely unavailable
**Then** event description = "AI analysis unavailable"
**And** event is saved without description
**And** alert logged for operator

**Given** successful fallback
**When** event is saved
**Then** event.analysis_mode = actual mode used (not configured mode)
**And** event.fallback_reason explains the fallback

**Prerequisites:** P3-2.6, P3-3.1

**Technical Notes:**
- Implement in EventProcessor
- Fallback chain: video_native → multi_frame → single_frame → no description
- Track each failure reason in comma-separated fallback_reason
- Example: "video_native:provider_unsupported,multi_frame:clip_download_timeout"

---

## Epic P3-4: Native Video Analysis

**Goal:** Enable sending full video clips directly to AI providers that support video input, achieving the highest quality descriptions.

**FRs Covered:** FR19, FR20, FR21, FR22

---

### Story P3-4.1: Add Provider Video Capability Detection

**As a** system,
**I want** to know which AI providers support video input,
**So that** video_native mode routes to capable providers.

**Acceptance Criteria:**

**Given** AIService provider configuration
**When** capability is checked
**Then** returns capability matrix:
  - OpenAI GPT-4o: video=true, max_duration=60s
  - Claude: video=false
  - Gemini: video=true, max_duration=60s
  - Grok: video=false (TBD)

**Given** video_native analysis requested
**When** provider doesn't support video
**Then** that provider is skipped in fallback chain
**And** next video-capable provider is tried

**Given** no video-capable providers configured
**When** video_native mode is selected
**Then** system falls back to multi_frame immediately
**And** logs "No video-capable providers available"

**Prerequisites:** None

**Technical Notes:**
- Add `PROVIDER_CAPABILITIES` constant to ai_service.py
- Structure: `{"openai": {"video": True, "max_video_duration": 60, "max_video_size_mb": 20}}`
- Check capabilities before attempting video analysis
- Update as provider capabilities change

---

### Story P3-4.2: Implement Video Upload to OpenAI

**As a** system,
**I want** to send video clips to OpenAI GPT-4o,
**So that** users get video-native analysis from OpenAI.

**Acceptance Criteria:**

**Given** a video clip under 20MB and 60 seconds
**When** `AIService.describe_video(video_path, prompt)` is called for OpenAI
**Then** video is uploaded using OpenAI's file API
**And** vision request references the uploaded file
**And** description is returned

**Given** video exceeds OpenAI limits (>20MB or >60s)
**When** video analysis is attempted
**Then** returns None with error "Video exceeds OpenAI limits"
**And** triggers fallback to multi_frame

**Given** video format is not supported
**When** analysis is attempted
**Then** system converts to supported format (MP4/H.264)
**And** retries with converted file

**Given** video upload succeeds
**When** analysis completes
**Then** uploaded file is deleted from OpenAI (cleanup)

**Prerequisites:** P3-4.1

**Technical Notes:**
- OpenAI video via base64 in content array (like images but with video)
- Or use file upload API if available
- Check latest OpenAI API docs for video handling
- May need to use gpt-4o specifically (not gpt-4o-mini)

---

### Story P3-4.3: Implement Video Upload to Gemini

**As a** system,
**I want** to send video clips to Google Gemini,
**So that** users get video-native analysis from Gemini.

**Acceptance Criteria:**

**Given** a video clip under Gemini's limits
**When** `AIService.describe_video()` is called for Gemini
**Then** video is sent using Gemini's video API format
**And** description is returned

**Given** video needs format conversion for Gemini
**When** original format unsupported
**Then** converts to supported format using PyAV
**And** retries with converted file

**Given** Gemini video analysis completes
**When** response is received
**Then** token usage is tracked
**And** cost estimate is calculated

**Prerequisites:** P3-4.1

**Technical Notes:**
- Gemini 1.5 Pro supports video natively
- Use google.generativeai library
- Video uploaded inline or via File API
- Check duration/size limits in Gemini docs

---

### Story P3-4.4: Integrate Video Native Mode into Pipeline

**As a** system,
**I want** video_native mode to work end-to-end,
**So that** configured cameras use full video analysis.

**Acceptance Criteria:**

**Given** camera with analysis_mode='video_native'
**When** Protect event is processed
**Then** clip is downloaded
**And** sent directly to video-capable provider
**And** description captures full video narrative

**Given** video_native analysis succeeds
**When** event is saved
**Then** event.analysis_mode = 'video_native'
**And** event.frame_count_used = null (video, not frames)

**Given** video_native provider fails
**When** fallback triggers
**Then** tries next video-capable provider
**And** if none available, falls back to multi_frame

**Given** all video providers exhausted
**When** fallback continues
**Then** extracts frames and uses multi_frame
**And** event.fallback_reason includes "video_native:all_providers_failed"

**Prerequisites:** P3-4.2, P3-4.3, P3-3.5

**Technical Notes:**
- Modify EventProcessor video_native branch
- Provider order for video: OpenAI → Gemini (configurable)
- Video analysis may be slower - ensure async handling
- Consider timeout: 30s for video analysis

---

### Story P3-4.5: Add AI Provider Badge to Event Cards

**As a** user viewing events,
**I want to** see which AI provider analyzed each event,
**So that** I can understand which AI service generated the description and correlate quality with providers.

**Acceptance Criteria:**

**Given** an event card in the timeline
**When** event has provider_used stored
**Then** small badge shows provider: OpenAI/Grok/Claude/Gemini
**And** badge has appropriate icon and color per provider

**Given** event with provider_used = "openai"
**When** displayed
**Then** shows green badge with sparkle icon labeled "OpenAI"

**Given** event with provider_used = "grok"
**When** displayed
**Then** shows orange badge with zap icon labeled "Grok"

**Given** event with provider_used = "claude"
**When** displayed
**Then** shows amber badge with message icon labeled "Claude"

**Given** event with provider_used = "gemini"
**When** displayed
**Then** shows blue badge with stars icon labeled "Gemini"

**Given** event has no provider_used (legacy events or null)
**When** displayed
**Then** no AI provider badge is shown

**Given** user hovers AI provider badge
**When** tooltip appears
**Then** shows full provider name (e.g., "OpenAI GPT-4o mini")

**Prerequisites:** None (backend already tracks provider_used)

**Technical Notes:**
- Create `frontend/components/events/AIProviderBadge.tsx`
- Add to EventCard.tsx header row after AnalysisModeBadge
- Provider styling: OpenAI=green, Grok=orange, Claude=amber, Gemini=blue
- Follow existing AnalysisModeBadge pattern with Tooltip
- No backend changes needed - provider_used field already exists

---

## Epic P3-5: Audio Analysis for Doorbells

**Goal:** Extract and transcribe audio from doorbell events to provide richer context including spoken words.

**FRs Covered:** FR23, FR24, FR25, FR26

---

### Story P3-5.1: Implement Audio Extraction from Video Clips

**As a** system,
**I want** to extract audio tracks from video clips,
**So that** audio can be analyzed separately.

**Acceptance Criteria:**

**Given** a video clip with audio track
**When** `AudioExtractor.extract_audio(clip_path)` is called
**Then** returns audio as WAV or MP3 bytes
**And** extraction completes within 2 seconds

**Given** a video clip with no audio track
**When** extraction is attempted
**Then** returns None
**And** logs "No audio track found in clip"

**Given** audio track exists but is silent
**When** extraction and analysis occur
**Then** returns audio bytes
**And** downstream transcription handles silence

**Prerequisites:** P3-1.1 (clips available)

**Technical Notes:**
- Create `backend/app/services/audio_extractor.py`
- Use PyAV for audio extraction: `container.streams.audio[0]`
- Output format: WAV (16kHz, mono) for transcription compatibility
- Check audio levels to detect silent tracks

---

### Story P3-5.2: Integrate Speech-to-Text Transcription

**As a** system,
**I want** to transcribe audio from doorbell events,
**So that** spoken words are captured in descriptions.

**Acceptance Criteria:**

**Given** extracted audio bytes
**When** `AudioExtractor.transcribe(audio_bytes)` is called
**Then** returns text transcription
**And** uses OpenAI Whisper API or configured provider

**Given** audio contains speech
**When** transcription completes
**Then** returns accurate text of spoken words
**And** handles multiple speakers

**Given** audio is just ambient noise (no speech)
**When** transcription runs
**Then** returns empty string or "[ambient sounds]"
**And** doesn't fabricate words

**Given** transcription fails (API error)
**When** error occurs
**Then** returns None
**And** analysis continues without audio context

**Prerequisites:** P3-5.1

**Technical Notes:**
- Use OpenAI Whisper API: `client.audio.transcriptions.create()`
- Model: "whisper-1"
- Response format: text
- Consider local whisper.cpp for cost savings (future)

---

### Story P3-5.3: Include Audio Context in AI Descriptions

**As a** system,
**I want** AI descriptions to incorporate audio transcription,
**So that** doorbell events include what was said.

**Acceptance Criteria:**

**Given** doorbell event with audio transcription
**When** AI description is generated
**Then** prompt includes: "Audio transcription: '{transcription}'"
**And** AI incorporates speech into description

**Given** transcription "Amazon delivery"
**When** combined with video of person at door
**Then** description might be: "Delivery person arrived at front door, rang doorbell, and announced 'Amazon delivery'"

**Given** no audio or empty transcription
**When** AI prompt is built
**Then** audio context section is omitted
**And** description based on video only

**Given** camera is_doorbell=true
**When** processing event
**Then** audio extraction is attempted automatically
**And** non-doorbell cameras skip audio extraction

**Prerequisites:** P3-5.2, P3-2.4

**Technical Notes:**
- Modify multi-frame and video prompts to include audio section
- Only attempt audio for doorbell cameras (is_doorbell=true)
- Add `audio_transcription` field to Event model (optional)
- Track audio processing in event metadata

---

## Epic P3-6: Confidence Scoring & Quality Indicators

**Goal:** Provide visibility into AI description quality so users can identify and re-analyze uncertain events.

**FRs Covered:** FR27, FR28, FR29, FR30, FR31, FR40

---

### Story P3-6.1: Extract Confidence Score from AI Responses

**As a** system,
**I want** AI to return confidence scores with descriptions,
**So that** uncertain descriptions can be identified.

**Acceptance Criteria:**

**Given** AI analysis request
**When** prompt is sent
**Then** includes instruction: "Rate your confidence in this description from 0.0 to 1.0"
**And** requests JSON response format with description and confidence

**Given** AI response with confidence
**When** parsed
**Then** extracts `description` and `confidence` (0.0-1.0)
**And** stores both in event record

**Given** AI returns confidence < 0.5
**When** event is saved
**Then** flags event as `low_confidence: true`

**Given** AI doesn't return valid confidence
**When** parsing fails
**Then** defaults to `confidence: null`
**And** event is not flagged as low confidence

**Prerequisites:** P3-2.3

**Technical Notes:**
- Modify AI prompts to request JSON: `{"description": "...", "confidence": 0.85}`
- Parse with Pydantic model for validation
- Add `ai_confidence` field to Event model (Float, nullable)
- Add `low_confidence` boolean field

---

### Story P3-6.2: Detect Vague Descriptions

**As a** system,
**I want** to automatically detect vague AI descriptions,
**So that** ambiguous events are flagged for review.

**Acceptance Criteria:**

**Given** AI description text
**When** vagueness detection runs
**Then** flags descriptions containing:
  - "appears to be"
  - "possibly"
  - "unclear"
  - "cannot determine"
  - "something"
  - "motion detected" (without specifics)

**Given** description flagged as vague
**When** combined with low AI confidence
**Then** event.low_confidence = true regardless of score

**Given** description is specific: "Person in blue jacket delivered package"
**When** vagueness detection runs
**Then** not flagged as vague

**Prerequisites:** P3-6.1

**Technical Notes:**
- Create `description_quality.py` utility
- Regex patterns for vague phrases
- Word count threshold: <10 words may indicate vague
- Run after AI response, before saving event

---

### Story P3-6.3: Display Confidence Indicator on Event Cards

**As a** user,
**I want** to see confidence indicators on event cards,
**So that** I can identify events needing review.

**Acceptance Criteria:**

**Given** event with confidence score
**When** displayed in timeline
**Then** shows confidence indicator:
  - 0.8-1.0: Green checkmark (high)
  - 0.5-0.8: Yellow dot (medium)
  - 0.0-0.5: Red warning (low)

**Given** event flagged low_confidence
**When** displayed
**Then** shows subtle warning icon
**And** tooltip: "AI was uncertain about this description"

**Given** confidence is null (legacy or parsing failed)
**When** displayed
**Then** no confidence indicator shown

**Given** user hovers confidence indicator
**When** tooltip appears
**Then** shows: "Confidence: 85%" with explanation

**Prerequisites:** P3-6.1

**Technical Notes:**
- Create `frontend/components/events/ConfidenceIndicator.tsx`
- Add to EventCard next to analysis mode badge
- Keep subtle - don't dominate the card
- Color-blind friendly: use icons + colors

---

### Story P3-6.4: Add Re-Analyze Action for Low-Confidence Events

**As a** user,
**I want** to re-analyze events with higher quality settings,
**So that** uncertain descriptions can be improved.

**Acceptance Criteria:**

**Given** event card with low confidence
**When** user clicks "Re-analyze" button
**Then** modal offers:
  - "Re-analyze with Multi-Frame" (if was single)
  - "Re-analyze with Video Native" (if Protect camera)
  - "Re-analyze with same settings"

**Given** user selects re-analysis option
**When** confirmed
**Then** triggers new AI analysis
**And** shows loading state
**And** updates event with new description

**Given** re-analysis completes
**When** new description is received
**Then** event.description is updated
**And** event.ai_confidence is updated
**And** event.analysis_mode reflects new mode used
**And** event.reanalyzed_at timestamp is set

**Given** re-analysis fails
**When** error occurs
**Then** shows error message
**And** original description is preserved

**Prerequisites:** P3-6.3, P3-3.5

**Technical Notes:**
- Add `POST /api/v1/events/{id}/reanalyze` endpoint
- Request body: `{"analysis_mode": "video_native"}`
- Add `reanalyzed_at` timestamp to Event model
- Consider rate limiting re-analysis (cost control)

---

## Epic P3-7: Cost Monitoring Dashboard

**Goal:** Provide visibility into AI API usage and costs, with configurable caps to prevent surprise bills.

**FRs Covered:** FR32, FR33, FR34, FR35, FR36, FR37, FR39, FR41

---

### Story P3-7.1: Implement Cost Tracking Service

**As a** system,
**I want** to track AI usage costs accurately,
**So that** users can monitor their spending.

**Acceptance Criteria:**

**Given** AI request completes
**When** usage is recorded
**Then** CostTracker calculates estimated cost:
  - Tokens × cost_per_token for provider
  - Stores in ai_usage table

**Given** cost rates by provider
**When** configured
**Then** uses:
  - OpenAI: $0.00015/1K input, $0.0006/1K output
  - Grok: $0.0001/1K input, $0.0003/1K output
  - Claude: $0.00025/1K input, $0.00125/1K output
  - Gemini: Free tier or configured rate

**Given** daily usage aggregation
**When** queried
**Then** returns total cost by:
  - Date
  - Camera
  - Provider
  - Analysis mode

**Prerequisites:** P3-2.5

**Technical Notes:**
- Create `backend/app/services/cost_tracker.py`
- Add ai_usage table migration (if not exists from P3-2.5)
- Index on (date, camera_id, provider) for fast queries
- Store costs in USD with 6 decimal places

---

### Story P3-7.2: Build Cost Dashboard UI

**As a** user,
**I want** a dashboard showing AI usage and costs,
**So that** I can monitor spending patterns.

**Acceptance Criteria:**

**Given** settings page
**When** user navigates to "AI Usage" tab
**Then** sees dashboard with:
  - Today's cost (prominent)
  - This month's cost
  - Cost by camera (bar chart)
  - Cost by provider (pie chart)
  - Daily trend (line chart, last 30 days)

**Given** cost data available
**When** dashboard loads
**Then** shows actual vs estimated costs
**And** updates show ±20% accuracy indicator (NFR12)

**Given** no usage data
**When** dashboard loads
**Then** shows "No AI usage recorded yet"
**And** explains how usage tracking works

**Given** user clicks on camera in chart
**When** drilldown activates
**Then** shows detailed usage for that camera
**And** breakdown by analysis mode

**Prerequisites:** P3-7.1

**Technical Notes:**
- Create `frontend/components/settings/CostDashboard.tsx`
- Add to settings page as new tab
- Use recharts or similar for charts
- API: `GET /api/v1/system/ai-usage?period=30d`

---

### Story P3-7.3: Implement Daily/Monthly Cost Caps

**As a** user,
**I want** to set cost caps to prevent surprise bills,
**So that** AI analysis stops before exceeding my budget.

**Acceptance Criteria:**

**Given** settings UI
**When** user configures cost caps
**Then** can set:
  - Daily cap (e.g., $1.00)
  - Monthly cap (e.g., $20.00)
  - Or "No limit"

**Given** daily cost reaches 80% of cap
**When** threshold crossed
**Then** warning notification sent
**And** dashboard shows warning indicator

**Given** daily cost reaches cap
**When** new event needs AI analysis
**Then** AI analysis is skipped
**And** event saved with description: "AI analysis paused - daily cost cap reached"
**And** event.analysis_skipped_reason = "cost_cap_daily"

**Given** new day begins (midnight UTC)
**When** daily cap was reached
**Then** AI analysis resumes
**And** notification sent: "AI analysis resumed"

**Prerequisites:** P3-7.1, P3-7.2

**Technical Notes:**
- Add settings: `AI_DAILY_COST_CAP`, `AI_MONTHLY_COST_CAP`
- Store in system settings (JSON field)
- Check cap before AI analysis in EventProcessor
- Real-time enforcement (NFR13)

---

### Story P3-7.4: Add Cost Alerts and Notifications

**As a** user,
**I want** alerts when approaching cost limits,
**So that** I can adjust settings before analysis stops.

**Acceptance Criteria:**

**Given** cost reaches 50% of daily cap
**When** threshold crossed
**Then** info notification: "AI costs at 50% of daily cap"

**Given** cost reaches 80% of daily cap
**When** threshold crossed
**Then** warning notification: "AI costs at 80% of daily cap"
**And** shown prominently in UI

**Given** cost reaches 100% of cap
**When** analysis is paused
**Then** alert notification: "AI analysis paused - daily cap reached"
**And** suggests: "Increase cap in settings or wait until tomorrow"

**Given** user dismissed alert
**When** same threshold hit again (next cycle)
**Then** alert shown again

**Prerequisites:** P3-7.3

**Technical Notes:**
- Use existing notification system
- Notifications table for persistence
- WebSocket for real-time alerts
- Email alerts optional (future)

---

### Story P3-7.5: Display Key Frames Gallery on Event Detail

**As a** user,
**I want** to see the frames used for AI analysis,
**So that** I understand what the AI saw.

**Acceptance Criteria:**

**Given** event analyzed with multi_frame mode
**When** event detail view opened
**Then** shows gallery of extracted frames
**And** frames displayed in chronological order
**And** timestamp overlay on each frame

**Given** event used single_frame mode
**When** detail view opened
**Then** shows single thumbnail
**And** labeled "Single frame analysis"

**Given** event used video_native mode
**When** detail view opened
**Then** shows "Full video analyzed"
**And** optionally shows video player or key frames

**Given** frames not stored (storage disabled)
**When** detail view opened
**Then** shows "Frames not stored"
**And** explains storage setting

**Prerequisites:** P3-2.6

**Technical Notes:**
- Store extracted frames temporarily or in event metadata
- Option to persist frames: `STORE_ANALYSIS_FRAMES` setting
- Frame storage: base64 in event JSON or separate files
- Consider thumbnail-only storage to save space

---

### Story P3-7.6: Add Analysis Mode Filter to Timeline

**As a** user,
**I want** to filter events by analysis mode,
**So that** I can review events with specific analysis types.

**Acceptance Criteria:**

**Given** event timeline view
**When** filter dropdown opened
**Then** includes "Analysis Mode" filter with options:
  - All modes
  - Single Frame only
  - Multi-Frame only
  - Video Native only
  - With fallback (events that fell back)
  - Low confidence

**Given** "Multi-Frame only" filter selected
**When** applied
**Then** only events with analysis_mode='multi_frame' shown

**Given** "With fallback" filter selected
**When** applied
**Then** only events with non-null fallback_reason shown

**Given** filter combined with other filters (camera, date)
**When** applied
**Then** all filters work together correctly

**Prerequisites:** P3-3.4, P3-6.3

**Technical Notes:**
- Add to existing timeline filter component
- API: `GET /api/v1/events?analysis_mode=multi_frame`
- Add `analysis_mode` and `has_fallback` query params
- Index on analysis_mode for performance

---

## FR Coverage Matrix

| FR | Description | Epic | Story |
|----|-------------|------|-------|
| FR1 | Download motion clips from Protect | P3-1 | P3-1.1 |
| FR2 | Store clips temporarily | P3-1 | P3-1.2 |
| FR3 | Auto cleanup clips | P3-1 | P3-1.2 |
| FR4 | Retry with exponential backoff | P3-1 | P3-1.3 |
| FR5 | Fallback to snapshot on failure | P3-1 | P3-1.4 |
| FR6 | Extract multiple frames | P3-2 | P3-2.1 |
| FR7 | Configurable frame intervals | P3-2 | P3-2.1 |
| FR8 | Extract 3-10 frames | P3-2 | P3-2.1 |
| FR9 | Filter blurry frames | P3-2 | P3-2.2 |
| FR10 | AI accepts multiple images | P3-2 | P3-2.3 |
| FR11 | Mode-specific prompts | P3-2 | P3-2.4 |
| FR12 | Multi-image all providers | P3-2 | P3-2.3 |
| FR13 | Track token usage | P3-2 | P3-2.5 |
| FR14 | Camera analysis mode setting | P3-3 | P3-3.1 |
| FR15 | Three mode choices | P3-3 | P3-3.2 |
| FR16 | UI with trade-off info | P3-3 | P3-3.3 |
| FR17 | Apply mode on processing | P3-3 | P3-3.5 |
| FR18 | Fallback chain | P3-3 | P3-3.5 |
| FR19 | Send video to providers | P3-4 | P3-4.2, P3-4.3 |
| FR20 | Detect provider capabilities | P3-4 | P3-4.1 |
| FR21 | Convert video format | P3-4 | P3-4.2, P3-4.3 |
| FR22 | Handle size/duration limits | P3-4 | P3-4.2, P3-4.3 |
| FR23 | Extract audio from clips | P3-5 | P3-5.1 |
| FR24 | Transcribe audio | P3-5 | P3-5.2 |
| FR25 | Include audio in prompt | P3-5 | P3-5.3 |
| FR26 | Handle no audio | P3-5 | P3-5.1 |
| FR27 | Return confidence score | P3-6 | P3-6.1 |
| FR28 | Detect vague descriptions | P3-6 | P3-6.2 |
| FR29 | Flag low confidence | P3-6 | P3-6.3 |
| FR30 | Re-analyze action | P3-6 | P3-6.4 |
| FR31 | Store confidence scores | P3-6 | P3-6.1 |
| FR32 | Track AI usage | P3-7 | P3-7.1 |
| FR33 | Aggregate by camera/day/provider | P3-7 | P3-7.1 |
| FR34 | Display costs dashboard | P3-7 | P3-7.2 |
| FR35 | Set cost caps | P3-7 | P3-7.3 |
| FR36 | Alert on approaching limits | P3-7 | P3-7.4 |
| FR37 | Pause on cap reached | P3-7 | P3-7.3 |
| FR38 | Show analysis mode on cards | P3-3 | P3-3.4 |
| FR39 | Display key frames | P3-7 | P3-7.5 |
| FR40 | Show confidence indicator | P3-6 | P3-6.3 |
| FR41 | Filter by analysis mode | P3-7 | P3-7.6 |
| FR42 | Show AI provider on cards | P3-4 | P3-4.5 |

**Coverage Validation:** All 42 FRs mapped to stories. ✓

---

## Summary

### Epic Breakdown Summary

**Phase 3 transforms the system from snapshot-based to video-aware AI analysis:**

**MVP (Epics P3-1, P3-2, P3-3):**
- 16 stories covering clip download, frame extraction, multi-image AI, and mode configuration
- Delivers core value: richer descriptions that capture action and narrative
- User control over cost/quality trade-off per camera

**Growth (Epics P3-4, P3-5, P3-6, P3-7):**
- 18 stories covering video native, audio analysis, confidence scoring, and cost monitoring
- Enhances quality with full video and audio context
- Provides operational visibility and cost control

**Dependencies:**
```
P3-1 (Clip Download) ─┬─> P3-2 (Multi-Frame) ─> P3-4 (Video Native)
                      ├─> P3-3 (Mode Config)
                      └─> P3-5 (Audio)

P3-2 ─> P3-6 (Confidence)
P3-2 ─> P3-7 (Cost Monitor)
```

**Recommended Implementation Order:**
1. P3-1.1 → P3-1.2 → P3-1.3 → P3-1.4 (foundation)
2. P3-2.1 → P3-2.2 → P3-2.3 → P3-2.4 (core improvement)
3. P3-3.1 → P3-3.2 → P3-3.3 (user control - can parallel with P3-2)
4. P3-2.5 → P3-2.6 (integration)
5. P3-3.4 → P3-3.5 (complete MVP)
6. Growth epics as prioritized

---

## Next Steps

**BMad Method Next Steps:**

1. **Architecture Review** - Validate technical decisions in architecture.md align with story requirements
2. **Sprint Planning** - Run `workflow sprint-planning` to create sprint status tracking
3. **Story Implementation** - Run `workflow create-story` to generate detailed story files for development

---

_This document will be updated as implementation reveals edge cases and technical details._

_For implementation: Use the `create-story` workflow to generate individual story implementation plans from this epic breakdown._
