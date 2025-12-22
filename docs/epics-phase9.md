# ArgusAI Phase 9 - Epic Breakdown

**Author:** Brent
**Date:** 2025-12-22
**Phase:** 9 - AI Accuracy, Stability & Developer Experience
**PRD Reference:** [PRD-phase9.md](./PRD-phase9.md)

---

## Overview

This document provides the complete epic and story breakdown for ArgusAI Phase 9, decomposing the requirements from the PRD into implementable stories. Phase 9 focuses on bug fixes, AI accuracy improvements, and developer experience enhancements.

**Living Document Notice:** This is the initial version. It will be updated after Architecture workflow adds technical details to stories.

### Epic Summary

| Epic | Title | Stories | Priority | FRs Covered |
|------|-------|---------|----------|-------------|
| P9-1 | Critical Bug Fixes | 8 | P1 | FR1-FR7 |
| P9-2 | Frame Capture & Video Analysis | 7 | P2 | FR8-FR15 |
| P9-3 | AI Context & Accuracy | 6 | P2 | FR16-FR24 |
| P9-4 | Entity Management | 6 | P2 | FR25-FR32 |
| P9-5 | Infrastructure & DevOps | 6 | P2 | FR33-FR40 |
| P9-6 | Documentation & UX Polish | 8 | P3 | FR41-FR50 |

**Total: 6 Epics, 41 Stories**

---

## Functional Requirements Inventory

### Bug Fixes (FR1-FR7)
- **FR1:** GitHub Actions CI pipeline passes all tests on every PR
- **FR2:** Push notifications work reliably for all events, not just the first
- **FR3:** Protect camera filter settings persist after page refresh and server restart
- **FR4:** Re-analyse function successfully re-processes event descriptions
- **FR5:** AI-assisted prompt refinement submits to AI provider and displays results
- **FR6:** AI-assisted prompt refinement modal shows which AI model is being used
- **FR7:** AI-assisted prompt refinement has save/replace button to apply refined prompt

### Frame Capture & Video Analysis (FR8-FR15)
- **FR8:** Frame capture timing is optimized to capture actual motion activity
- **FR9:** System can extract frames using adaptive sampling based on motion/changes
- **FR10:** Users can configure number of frames for AI analysis (5, 10, 15, 20)
- **FR11:** All frames used for AI analysis are stored and retrievable
- **FR12:** Event cards show clickable thumbnails that open frame gallery
- **FR13:** Frame gallery displays all analyzed frames with navigation
- **FR14:** Users can choose frame sampling strategy (uniform, adaptive, hybrid)
- **FR15:** Adaptive sampling prioritizes high-activity frames over static frames

### AI Context & Accuracy (FR16-FR24)
- **FR16:** AI prompt includes camera name for contextual descriptions
- **FR17:** AI prompt includes time of day/date for temporal context
- **FR18:** System attempts to read timestamp/camera name from frame overlay
- **FR19:** System falls back to database metadata if overlay not readable
- **FR20:** Users can mark package detections as false positives
- **FR21:** Package false positive feedback is stored for prompt refinement
- **FR22:** Users can provide thumbs up/down feedback on daily summaries
- **FR23:** Users can customize summary generation prompt in Settings
- **FR24:** Summary feedback data appears in AI Accuracy statistics

### Entity Management (FR25-FR32)
- **FR25:** Vehicle entities are separated by make/model/color
- **FR26:** Each unique vehicle creates a distinct entity with its own event history
- **FR27:** Entity detail page shows list of all linked events
- **FR28:** Users can remove events from entities (unlink misattributed events)
- **FR29:** Users can add events to existing entities from event cards
- **FR30:** Users can move events between entities
- **FR31:** Users can merge duplicate entities
- **FR32:** Manual entity adjustments are stored to improve future matching

### Infrastructure & DevOps (FR33-FR40)
- **FR33:** System supports SSL/HTTPS connections
- **FR34:** Let's Encrypt/Certbot integration available in install script
- **FR35:** Self-signed certificate generation available as option
- **FR36:** n8n instance can be deployed alongside ArgusAI
- **FR37:** n8n workflows integrate with Claude Code CLI
- **FR38:** n8n workflows execute BMAD method workflows
- **FR39:** n8n provides dashboard for pipeline monitoring
- **FR40:** n8n implements approval gates for human review

### Documentation & UX Polish (FR41-FR50)
- **FR41:** README.md reflects all implemented phases and features
- **FR42:** README includes current installation instructions
- **FR43:** GitHub Pages site has landing page with project overview
- **FR44:** GitHub Pages site has documentation section
- **FR45:** GitHub Pages deploys automatically on push to main
- **FR46:** Events page buttons don't overlap with header controls
- **FR47:** MQTT form fields hidden when integration is disabled
- **FR48:** Skip to content link available for keyboard users
- **FR49:** Camera list uses React.memo for performance
- **FR50:** Test connection endpoint validates camera before save

---

## FR Coverage Map

| FR | Description | Epic | Story |
|----|-------------|------|-------|
| FR1 | CI pipeline passes tests | P9-1 | 1.1 |
| FR2 | Push notifications reliable | P9-1 | 1.2 |
| FR3 | Filter settings persist | P9-1 | 1.3 |
| FR4 | Re-analyse works | P9-1 | 1.4 |
| FR5 | Prompt refinement submits | P9-1 | 1.5 |
| FR6 | Show AI model in modal | P9-1 | 1.6 |
| FR7 | Save/replace button | P9-1 | 1.7 |
| FR8 | Frame timing optimized | P9-2 | 2.1 |
| FR9 | Adaptive sampling | P9-2 | 2.2, 2.3 |
| FR10 | Configurable frame count | P9-2 | 2.4 |
| FR11 | Store all frames | P9-2 | 2.5 |
| FR12 | Clickable thumbnails | P9-2 | 2.6 |
| FR13 | Frame gallery | P9-2 | 2.6 |
| FR14 | Sampling strategy setting | P9-2 | 2.7 |
| FR15 | Prioritize activity frames | P9-2 | 2.3 |
| FR16 | Camera name in prompt | P9-3 | 3.1 |
| FR17 | Time of day in prompt | P9-3 | 3.1 |
| FR18 | Read frame overlay | P9-3 | 3.2 |
| FR19 | Fallback to metadata | P9-3 | 3.2 |
| FR20 | Mark false positives | P9-3 | 3.3 |
| FR21 | Store feedback | P9-3 | 3.3 |
| FR22 | Summary feedback buttons | P9-3 | 3.4 |
| FR23 | Summary prompt setting | P9-3 | 3.5 |
| FR24 | Summary in AI Accuracy | P9-3 | 3.6 |
| FR25 | Vehicle separation | P9-4 | 4.1 |
| FR26 | Distinct vehicle entities | P9-4 | 4.1 |
| FR27 | Entity event list | P9-4 | 4.2 |
| FR28 | Unlink events | P9-4 | 4.3 |
| FR29 | Add to entity | P9-4 | 4.4 |
| FR30 | Move between entities | P9-4 | 4.4 |
| FR31 | Merge entities | P9-4 | 4.5 |
| FR32 | Store adjustments | P9-4 | 4.6 |
| FR33 | SSL/HTTPS support | P9-5 | 5.1 |
| FR34 | Let's Encrypt | P9-5 | 5.2 |
| FR35 | Self-signed certs | P9-5 | 5.2 |
| FR36 | n8n deployment | P9-5 | 5.3 |
| FR37 | Claude Code integration | P9-5 | 5.4 |
| FR38 | BMAD integration | P9-5 | 5.5 |
| FR39 | n8n dashboard | P9-5 | 5.6 |
| FR40 | Approval gates | P9-5 | 5.6 |
| FR41 | README features | P9-6 | 6.1 |
| FR42 | README install | P9-6 | 6.1 |
| FR43 | GH Pages landing | P9-6 | 6.2 |
| FR44 | GH Pages docs | P9-6 | 6.3 |
| FR45 | GH Pages auto-deploy | P9-6 | 6.4 |
| FR46 | Button positioning | P9-6 | 6.5 |
| FR47 | Hide MQTT form | P9-6 | 6.6 |
| FR48 | Skip to content | P9-6 | 6.7 |
| FR49 | Camera list memo | P9-6 | 6.8 |
| FR50 | Test connection | P9-6 | 6.8 |

---

## Epic P9-1: Critical Bug Fixes

**Goal:** Resolve all P1/P2 bugs to stabilize the platform and restore CI/CD pipeline health.

**Value:** Users experience reliable functionality without unexpected errors. Development team can merge PRs with confidence.

**Backlog Items:** BUG-005, BUG-007, BUG-008, BUG-009, BUG-010, BUG-011

---

### Story P9-1.1: Fix GitHub Actions CI Tests

As a **developer**,
I want **the CI pipeline to pass all tests consistently**,
So that **I can merge PRs with confidence and catch regressions early**.

**Acceptance Criteria:**

**Given** a pull request is opened or updated
**When** GitHub Actions CI workflow runs
**Then** all backend pytest tests execute successfully
**And** all frontend tests execute successfully
**And** ESLint and TypeScript checks pass
**And** the workflow completes in under 10 minutes

**Given** a test fails in CI
**When** I review the failure logs
**Then** the error message clearly identifies the failing test and reason
**And** the failure is reproducible locally

**Prerequisites:** None (highest priority)

**Technical Notes:**
- Review `.github/workflows/ci.yml` for configuration issues
- Check for environment differences between local and CI (Node version, Python version)
- Identify flaky tests and add retry logic or fix root cause
- Ensure test fixtures and mocks are up to date with recent code changes
- Consider adding test isolation to prevent cross-test contamination
- Backlog: BUG-010

---

### Story P9-1.2: Fix Push Notifications Persistence

As a **user**,
I want **push notifications to work for every event, not just the first one**,
So that **I'm reliably notified of all activity at my property**.

**Acceptance Criteria:**

**Given** I have enabled push notifications and granted browser permission
**When** a new event is detected (person, vehicle, package, etc.)
**Then** I receive a push notification with event details
**And** this works for the 1st, 2nd, 10th, and 100th event
**And** notifications continue working after page refresh
**And** notifications continue working after browser restart

**Given** push notifications stop working
**When** I check the browser console
**Then** there are no service worker errors related to push subscription

**Prerequisites:** P9-1.1 (CI must pass)

**Technical Notes:**
- Investigate service worker lifecycle and subscription persistence
- Check if push subscription is being recreated unnecessarily
- Verify VAPID keys are consistent across restarts
- Test with multiple browsers (Chrome, Firefox, Safari)
- Add logging to track subscription state changes
- Check for browser throttling of notifications
- Backlog: BUG-007

---

### Story P9-1.3: Fix Protect Camera Filter Settings Persistence

As a **user**,
I want **my camera filter settings (person, vehicle, package, animal, ring) to persist**,
So that **I don't have to reconfigure them every time I refresh the page**.

**Acceptance Criteria:**

**Given** I configure filter settings for a Protect camera (enable/disable person, vehicle, etc.)
**When** I click Save
**Then** the settings are saved to the backend database
**And** a success toast notification appears

**Given** I have saved filter settings
**When** I refresh the page
**Then** the filter checkboxes reflect my saved settings
**And** the settings match what's stored in the database

**Given** I have saved filter settings
**When** the server restarts
**Then** my filter settings are preserved and loaded correctly

**Prerequisites:** P9-1.1

**Technical Notes:**
- Debug `PUT /api/v1/protect/controllers/{id}/cameras/{cam}/filters` endpoint
- Verify database model has columns for filter settings
- Check SQLAlchemy session commit is called
- Verify frontend reads filters from API response on page load
- Add database migration if schema changes needed
- Backlog: BUG-008

---

### Story P9-1.4: Fix Re-Analyse Function

As a **user**,
I want **to re-analyse events to get updated AI descriptions**,
So that **I can improve descriptions after adjusting prompts or when AI had errors**.

**Acceptance Criteria:**

**Given** I view an event card with an existing description
**When** I click the "Re-analyse" button
**Then** a loading indicator appears
**And** the event is re-processed by the AI
**And** the new description replaces the old one
**And** a success toast appears with "Description updated"

**Given** re-analysis fails (API error, timeout)
**When** the error occurs
**Then** an error toast displays with a helpful message
**And** the original description is preserved
**And** the error is logged for debugging

**Prerequisites:** P9-1.1

**Technical Notes:**
- Debug the re-analyse API endpoint (likely `POST /api/v1/events/{id}/reanalyse`)
- Check if the endpoint exists and is properly routed
- Verify AI service is called with correct parameters
- Ensure event record is updated in database after re-analysis
- Add proper error handling and user feedback
- Backlog: BUG-005

---

### Story P9-1.5: Fix Prompt Refinement API Submission

As a **user**,
I want **the AI-assisted prompt refinement to actually submit to the AI provider**,
So that **I get intelligent suggestions for improving my prompts**.

**Acceptance Criteria:**

**Given** I click "Refine Prompt" in Settings > AI Models
**When** the modal opens
**Then** I see a loading indicator while the AI processes
**And** within 30 seconds, I see the AI's suggested prompt refinement
**And** the suggestion is based on my current prompt and feedback data

**Given** the AI refinement API fails
**When** an error occurs
**Then** an error message displays in the modal
**And** I can close the modal and try again

**Prerequisites:** P9-1.1

**Technical Notes:**
- Verify API endpoint for prompt refinement exists and is called
- Check network tab in browser dev tools for actual API calls
- Ensure AI provider is configured and API key is valid
- Pass feedback data (thumbs up/down history) to refinement request
- Add loading state management in React component
- Backlog: BUG-009

---

### Story P9-1.6: Show AI Model in Prompt Refinement Modal

As a **user**,
I want **to see which AI model is being used for prompt refinement**,
So that **I understand what's generating the suggestions**.

**Acceptance Criteria:**

**Given** I open the prompt refinement modal
**When** the modal is displayed
**Then** I see text like "Using: OpenAI GPT-4o" or "Using: Claude 3 Haiku"
**And** this reflects the actual AI provider configured in position 1

**Given** no AI provider is configured
**When** I try to open the modal
**Then** I see a message "Please configure an AI provider first"
**And** a link to the AI provider settings

**Prerequisites:** P9-1.5

**Technical Notes:**
- Fetch current AI provider from settings API
- Display provider name in modal header or subtitle
- Handle case where no provider is configured
- Use same provider selection logic as event description
- Backlog: BUG-009

---

### Story P9-1.7: Add Save/Replace Button to Prompt Refinement

As a **user**,
I want **a clear way to accept and save the refined prompt**,
So that **I can apply AI suggestions to my actual prompt configuration**.

**Acceptance Criteria:**

**Given** the AI has generated a refined prompt suggestion
**When** I review the suggestion in the modal
**Then** I see three buttons: "Accept & Save", "Resubmit", and "Cancel"

**Given** I click "Accept & Save"
**When** the action completes
**Then** my prompt setting is updated with the new prompt
**And** the modal closes
**And** a success toast appears "Prompt updated successfully"
**And** the Settings page reflects the new prompt

**Given** I click "Resubmit"
**When** I've made edits to the suggested prompt
**Then** the edited version is sent back to AI for further refinement

**Prerequisites:** P9-1.5, P9-1.6

**Technical Notes:**
- Add button group to modal footer
- "Accept & Save" calls settings update API
- "Resubmit" re-calls refinement API with modified prompt
- Add confirmation for overwriting existing prompt
- Preserve original prompt in case user wants to revert
- Backlog: BUG-009

---

### Story P9-1.8: Fix Vehicle Entity Make/Model Separation

As a **user**,
I want **different vehicles to be tracked as separate entities**,
So that **I can see the history of each vehicle (e.g., my car vs delivery trucks)**.

**Acceptance Criteria:**

**Given** the AI describes a "white Toyota Camry" in one event
**And** the AI describes a "black Ford F-150" in another event
**When** I view the Entities page
**Then** I see two separate vehicle entities, not one combined "Vehicle" entity
**And** each entity shows its identifying characteristics (color, make, model)

**Given** the same vehicle appears in multiple events
**When** I view that vehicle's entity
**Then** all events for that specific vehicle are grouped together
**And** different vehicles are not mixed in

**Prerequisites:** P9-1.1

**Technical Notes:**
- Enhance entity extraction regex to parse color + make + model
- Pattern: `(white|black|red|blue|silver|gray|green)\s+(\w+)\s+(\w+)`
- Create entity signature combining color-make-model for matching
- Update entity clustering logic to use vehicle signature
- Add vehicle-specific fields to entity model if needed
- Backlog: BUG-011

---

## Epic P9-2: Frame Capture & Video Analysis

**Goal:** Improve video analysis quality by capturing the right frames at the right time and providing intelligent frame selection.

**Value:** Users see AI descriptions that match actual activity, not empty frames. Reduced AI costs through smart frame selection.

**Backlog Items:** IMP-006, IMP-007, IMP-011, FF-020, FF-021

---

### Story P9-2.1: Investigate and Fix Frame Capture Timing

As a **user**,
I want **captured frames to show the actual motion activity**,
So that **AI descriptions match what triggered the event**.

**Acceptance Criteria:**

**Given** a motion event is triggered (person walking, vehicle arriving)
**When** frames are extracted for AI analysis
**Then** at least 80% of frames show the subject in frame
**And** frames are not captured too early (before activity) or too late (after activity)

**Given** a Protect smart detection event
**When** I view the captured thumbnail and frames
**Then** the frames show the detected subject (person, vehicle, package)
**And** the subject is clearly visible, not entering/exiting frame edge

**Prerequisites:** P9-1.1

**Technical Notes:**
- Analyze timing between Protect event timestamp and clip availability
- Add configurable delay (0-5 seconds) before frame extraction
- Test different offset values for person, vehicle, package events
- Consider using motion detection timestamp vs event start time
- Log timing data to identify optimal extraction window
- May need different timing for different event types
- Backlog: IMP-011

---

### Story P9-2.2: Implement Similarity-Based Frame Filtering

As a **system**,
I want **to skip redundant frames that look nearly identical**,
So that **AI analyzes diverse frames without wasting tokens on duplicates**.

**Acceptance Criteria:**

**Given** a video clip is being processed for frame extraction
**When** frames are extracted
**Then** consecutive frames with >95% similarity are filtered out
**And** only visually distinct frames are retained for analysis

**Given** 100 raw frames are extracted
**When** similarity filtering is applied
**Then** typically 20-50 unique frames remain
**And** the remaining frames represent key visual changes

**Prerequisites:** P9-2.1

**Technical Notes:**
- Implement SSIM (Structural Similarity Index) comparison
- Alternative: histogram comparison for faster processing
- Threshold: 0.95 similarity = skip frame
- Process frames sequentially, compare to last kept frame
- OpenCV: `cv2.compareHist()` or `skimage.metrics.structural_similarity`
- Backlog: FF-020

---

### Story P9-2.3: Add Motion Scoring to Frame Selection

As a **system**,
I want **to prioritize frames with high motion activity**,
So that **AI sees the most important moments of the event**.

**Acceptance Criteria:**

**Given** frames have been filtered for similarity
**When** motion scoring is applied
**Then** each frame receives a motion score (0-100)
**And** frames with high scores are prioritized for AI analysis

**Given** a target of 10 frames for AI analysis
**When** selection occurs
**Then** the 10 frames with highest combined score (motion + uniqueness) are selected
**And** frames are ordered chronologically for context

**Prerequisites:** P9-2.2

**Technical Notes:**
- Calculate motion magnitude using optical flow (cv2.calcOpticalFlowFarneback)
- Alternative: frame differencing with threshold
- Combined score = motion_score * (1 - similarity_to_previous)
- Normalize scores to 0-100 range
- Select top N frames where N = user's configured frame count
- Backlog: FF-020

---

### Story P9-2.4: Add Configurable Frame Count Setting

As a **user**,
I want **to configure how many frames are analyzed per event**,
So that **I can balance AI accuracy vs cost**.

**Acceptance Criteria:**

**Given** I navigate to Settings > General
**When** I view the Analysis settings section
**Then** I see a "Frames per Analysis" dropdown with options: 5, 10, 15, 20

**Given** I change the frame count from 10 to 15
**When** I click Save
**Then** a warning modal appears explaining higher frame count = higher AI costs
**And** I must confirm to proceed
**And** the setting is saved

**Given** new events are processed
**When** AI analysis runs
**Then** the configured number of frames is used

**Prerequisites:** P9-2.1

**Technical Notes:**
- Add `analysis_frame_count` to system settings model
- Default value: 10 frames
- Add dropdown in GeneralSettings component
- Pass frame count to frame extraction service
- Warning modal text: "More frames may improve accuracy but increases AI API costs by approximately X%"
- Backlog: IMP-007

---

### Story P9-2.5: Store All Analysis Frames to Filesystem

As a **system**,
I want **to persist all frames used for AI analysis**,
So that **users can review what the AI saw**.

**Acceptance Criteria:**

**Given** an event is analyzed with 10 frames
**When** analysis completes
**Then** all 10 frames are saved to `data/frames/{event_id}/`
**And** frames are named sequentially: `frame_001.jpg`, `frame_002.jpg`, etc.
**And** frame metadata (timestamp, motion score) is stored in event record

**Given** an event with stored frames
**When** the event is deleted
**Then** associated frames are also deleted from filesystem

**Prerequisites:** P9-2.3

**Technical Notes:**
- Create frames directory structure: `data/frames/{event_id}/`
- Save frames as JPEG with 85% quality (balance size/quality)
- Add `frame_paths` JSON field to Event model
- Include frame metadata: `[{path, timestamp, motion_score}, ...]`
- Add cleanup logic in event deletion handler
- Consider retention policy (delete frames older than X days)
- Backlog: IMP-006

---

### Story P9-2.6: Build Frame Gallery Modal Component

As a **user**,
I want **to click on an event thumbnail to see all analyzed frames**,
So that **I can understand what the AI saw and verify accuracy**.

**Acceptance Criteria:**

**Given** I view an event card with a thumbnail
**When** I click on the thumbnail
**Then** a modal opens showing all frames used for analysis
**And** frames are displayed in a navigable gallery format

**Given** the frame gallery is open
**When** I navigate between frames
**Then** I can use left/right arrows or click thumbnails
**And** I see the frame number (e.g., "3 of 10")
**And** I see the frame's motion score if available

**Given** the frame gallery is open
**When** I press Escape or click outside
**Then** the modal closes

**Prerequisites:** P9-2.5

**Technical Notes:**
- Create `FrameGalleryModal` component using Radix Dialog
- Add click handler to event card thumbnail
- Fetch frame paths from event API response
- Use Swiper or simple state-based navigation
- Lazy load images for performance
- Add keyboard navigation (arrow keys)
- Mobile: support swipe gestures
- Backlog: IMP-006

---

### Story P9-2.7: Add Frame Sampling Strategy Setting

As a **user**,
I want **to choose how frames are selected for analysis**,
So that **I can optimize for my specific use case**.

**Acceptance Criteria:**

**Given** I navigate to Settings > General
**When** I view the Analysis settings section
**Then** I see a "Frame Sampling Strategy" dropdown with options:
- Uniform (fixed interval - predictable)
- Adaptive (content-aware - better quality)
- Hybrid (dense extraction + adaptive filtering)

**Given** I select a strategy and save
**When** new events are processed
**Then** the selected strategy is used for frame extraction

**Given** I hover over each option
**When** I view the tooltip
**Then** I see a brief explanation of the strategy and tradeoffs

**Prerequisites:** P9-2.3, P9-2.4

**Technical Notes:**
- Add `frame_sampling_strategy` to system settings
- Default: "adaptive" for new installs
- Uniform: extract every Nth frame (simple, predictable cost)
- Adaptive: similarity + motion scoring (better quality)
- Hybrid: extract dense, then filter (best quality, more processing)
- Pass strategy to frame extraction service
- Backlog: FF-021

---

## Epic P9-3: AI Context & Accuracy

**Goal:** Improve AI description accuracy by providing contextual information and collecting user feedback.

**Value:** More relevant descriptions ("Front door at 7am" vs generic), reduced false positives, self-improving system.

**Backlog Items:** IMP-012, IMP-013, IMP-014, FF-023

---

### Story P9-3.1: Add Camera and Time Context to AI Prompt

As a **system**,
I want **to include camera name and time of day in AI prompts**,
So that **descriptions have appropriate context**.

**Acceptance Criteria:**

**Given** an event is being analyzed
**When** the AI prompt is constructed
**Then** it includes: "This footage is from the [Camera Name] camera at [Time] on [Date]"
**And** this context appears before the description request

**Given** a camera named "Front Door"
**And** an event at 7:15 AM on December 22, 2025
**When** the AI generates a description
**Then** it may reference the context naturally (e.g., "Early morning visitor at the front door...")

**Prerequisites:** P9-1.1

**Technical Notes:**
- Modify AI prompt template in `ai_service.py`
- Fetch camera name from event's camera relationship
- Format time as human-readable (e.g., "7:15 AM", "2:30 PM")
- Consider time-of-day categories: morning, afternoon, evening, night
- Add camera location field if available
- Backlog: IMP-012

---

### Story P9-3.2: Attempt Frame Overlay Text Extraction

As a **system**,
I want **to read timestamp/camera name embedded in video frames**,
So that **I can use the camera's own metadata when available**.

**Acceptance Criteria:**

**Given** a frame with visible timestamp overlay (common in security cameras)
**When** OCR is attempted on the frame
**Then** extracted text is parsed for date/time patterns
**And** if successful, overlay data supplements database metadata

**Given** OCR extraction fails or no overlay exists
**When** context is needed
**Then** the system falls back to database metadata (event timestamp, camera name)
**And** no error is thrown

**Prerequisites:** P9-3.1

**Technical Notes:**
- Use pytesseract or easyocr for text extraction
- Target regions: top-left, bottom-left, bottom-right corners
- Pattern matching for timestamps: `\d{2}[:/]\d{2}[:/]\d{2}`
- Cache OCR results per camera (overlay location is consistent)
- Make OCR optional (can be CPU intensive)
- Fallback to DB metadata is the default behavior
- Backlog: IMP-012

---

### Story P9-3.3: Implement Package False Positive Feedback

As a **user**,
I want **to mark package detections as incorrect**,
So that **the system learns what is and isn't a package in my context**.

**Acceptance Criteria:**

**Given** an event is classified as "package" detection
**When** I view the event card
**Then** I see a "Not a package" button in addition to thumbs up/down

**Given** I click "Not a package"
**When** the feedback is submitted
**Then** the feedback is stored with event ID and correction type
**And** a toast confirms "Feedback recorded"
**And** the button changes to "Marked as not a package"

**Given** multiple "not a package" feedbacks exist
**When** AI-assisted prompt refinement runs
**Then** the false positive examples are included in the refinement request

**Prerequisites:** P9-1.7

**Technical Notes:**
- Add `correction_type` field to feedback model
- Create "Not a package" button for package events only
- Store correction with event reference for context
- Include in prompt refinement: "Users have marked these as NOT packages: [examples]"
- Consider threshold before including in prompts (e.g., 3+ corrections)
- Backlog: IMP-013

---

### Story P9-3.4: Add Summary Feedback Buttons

As a **user**,
I want **to rate daily summaries with thumbs up/down**,
So that **the system can improve summary quality over time**.

**Acceptance Criteria:**

**Given** I view a daily activity summary
**When** I see the summary card
**Then** I see thumbs up and thumbs down buttons below the summary text

**Given** I click thumbs up on a summary
**When** the feedback is submitted
**Then** the button shows selected state (filled icon)
**And** feedback is stored with summary ID and rating
**And** a brief toast appears "Thanks for the feedback!"

**Given** I click thumbs down on a summary
**When** a modal appears
**Then** I can optionally provide a correction or suggestion
**And** the feedback is stored with my notes

**Prerequisites:** P9-1.1

**Technical Notes:**
- Create `SummaryFeedbackButtons` component (similar to event feedback)
- Add `summary_feedback` table: id, summary_id, rating, correction_text, created_at
- API endpoint: `POST /api/v1/summaries/{id}/feedback`
- Reuse FeedbackButtons styling for consistency
- Backlog: IMP-014

---

### Story P9-3.5: Add Summary Prompt Customization

As a **user**,
I want **to customize the prompt used for generating summaries**,
So that **I can adjust the style and content of daily summaries**.

**Acceptance Criteria:**

**Given** I navigate to Settings > AI Models
**When** I scroll to the prompt section
**Then** I see a "Summary Prompt" textarea separate from the event description prompt
**And** it has a default value that generates current summary style

**Given** I edit the summary prompt
**When** I save changes
**Then** new summaries use my custom prompt
**And** existing summaries are not affected

**Given** I want to reset to default
**When** I click "Reset to Default"
**Then** the summary prompt reverts to the system default

**Prerequisites:** P9-3.4

**Technical Notes:**
- Add `summary_prompt` to system settings
- Default prompt template focused on daily digest style
- Include placeholder variables: {events_count}, {date}, {cameras}
- Add "Reset to Default" button
- Validate prompt has reasonable length (50-2000 chars)
- Backlog: IMP-014

---

### Story P9-3.6: Include Summary Feedback in AI Accuracy Stats

As a **user**,
I want **to see summary accuracy statistics alongside event accuracy**,
So that **I can track overall AI performance**.

**Acceptance Criteria:**

**Given** I navigate to Settings > AI Accuracy
**When** I view the accuracy statistics
**Then** I see a "Summary Accuracy" section
**And** it shows: total summaries, thumbs up count, thumbs down count, accuracy percentage

**Given** summary feedback has been collected
**When** I view the trend over time
**Then** I see summary accuracy charted alongside event accuracy

**Prerequisites:** P9-3.4, P9-3.5

**Technical Notes:**
- Add summary stats to AI accuracy API endpoint
- Calculate: accuracy = thumbs_up / (thumbs_up + thumbs_down) * 100
- Add summary stats card to AIAccuracySettings component
- Include in existing chart if using time-series visualization
- Handle case of no feedback yet (show "No feedback collected")
- Backlog: IMP-014

---

## Epic P9-4: Entity Management

**Goal:** Enable users to correct and manage entity assignments to improve recognition accuracy.

**Value:** Users can fix entity mistakes, leading to better "known visitor" detection and more useful entity history.

**Backlog Items:** BUG-011, IMP-015, IMP-016

---

### Story P9-4.1: Improve Vehicle Entity Extraction Logic

As a **system**,
I want **to extract detailed vehicle attributes from AI descriptions**,
So that **vehicles are properly separated into distinct entities**.

**Acceptance Criteria:**

**Given** an AI description containing "A white Toyota Camry pulled into the driveway"
**When** entity extraction runs
**Then** an entity is created/matched with:
- Type: vehicle
- Color: white
- Make: Toyota
- Model: Camry
- Signature: "white-toyota-camry"

**Given** two descriptions mentioning the same vehicle signature
**When** entity matching runs
**Then** both events are linked to the same entity

**Given** descriptions of different vehicles
**When** entity matching runs
**Then** separate entities are created for each unique vehicle

**Prerequisites:** P9-1.8

**Technical Notes:**
- Enhance regex patterns for vehicle extraction
- Common colors: white, black, silver, gray, red, blue, green, brown
- Handle partial matches (just color + make, or make + model)
- Create `vehicle_signature` field for matching
- Case-insensitive matching
- Consider fuzzy matching for OCR errors (Toyata → Toyota)
- Backlog: BUG-011

---

### Story P9-4.2: Build Entity Event List View

As a **user**,
I want **to see all events associated with an entity**,
So that **I can review the entity's history and verify correct grouping**.

**Acceptance Criteria:**

**Given** I view an entity detail page
**When** I scroll to the events section
**Then** I see a list of all events linked to this entity
**And** events are sorted by date (newest first)
**And** each event shows: thumbnail, description snippet, date/time

**Given** an entity has 50+ events
**When** I view the event list
**Then** events are paginated (20 per page)
**And** I can navigate between pages

**Prerequisites:** P9-4.1

**Technical Notes:**
- Create `EntityEventList` component
- Fetch events via `GET /api/v1/entities/{id}/events`
- Add pagination parameters: page, limit
- Reuse EventCard component in compact mode
- Add total count header: "47 events"
- Backlog: IMP-015

---

### Story P9-4.3: Implement Event-Entity Unlinking

As a **user**,
I want **to remove incorrectly assigned events from an entity**,
So that **entity history only contains relevant events**.

**Acceptance Criteria:**

**Given** I view an entity's event list
**When** I see an event that doesn't belong
**Then** I see a "Remove" button on that event row

**Given** I click "Remove" on an event
**When** confirmation dialog appears and I confirm
**Then** the event is unlinked from this entity
**And** the event still exists but has no entity association
**And** a toast confirms "Event removed from entity"

**Given** I accidentally remove an event
**When** I realize the mistake
**Then** I can re-add it via the event card (Story P9-4.4)

**Prerequisites:** P9-4.2

**Technical Notes:**
- Add "Remove" button with trash icon to event rows
- API: `DELETE /api/v1/entities/{id}/events/{event_id}`
- Set event's entity_id to NULL, don't delete event
- Add confirmation dialog to prevent accidents
- Log the manual correction for future ML training
- Backlog: IMP-015

---

### Story P9-4.4: Implement Event-Entity Assignment

As a **user**,
I want **to assign unlinked events to existing entities**,
So that **I can correct entity groupings**.

**Acceptance Criteria:**

**Given** I view an event card with no entity assigned
**When** I click "Add to Entity"
**Then** a modal opens with a searchable list of entities

**Given** the entity selection modal is open
**When** I search for "Toyota"
**Then** I see matching entities (e.g., "White Toyota Camry")
**And** I can select one to assign the event

**Given** I select an entity and confirm
**When** the assignment completes
**Then** the event is linked to the selected entity
**And** a toast confirms "Event added to [Entity Name]"
**And** the event card updates to show the entity link

**Prerequisites:** P9-4.2, P9-4.3

**Technical Notes:**
- Add "Add to Entity" button to event cards without entities
- Add "Move to Entity" button to event cards with entities
- Create `EntitySelectModal` component with search
- API: `POST /api/v1/events/{id}/entity` with entity_id
- Search endpoint: `GET /api/v1/entities?search=query`
- Log manual assignment for ML training
- Backlog: IMP-015

---

### Story P9-4.5: Implement Entity Merge

As a **user**,
I want **to merge duplicate entities**,
So that **the same person/vehicle isn't split across multiple entities**.

**Acceptance Criteria:**

**Given** I identify two entities that are the same (e.g., two entries for my car)
**When** I select both and click "Merge"
**Then** a confirmation shows which entity will be kept as primary
**And** I can choose which one to keep

**Given** I confirm the merge
**When** the operation completes
**Then** all events from the secondary entity move to the primary
**And** the secondary entity is deleted
**And** a toast confirms "Entities merged successfully"

**Prerequisites:** P9-4.4

**Technical Notes:**
- Add multi-select mode to entities list
- Show "Merge" button when 2 entities selected
- Merge dialog shows both entities with event counts
- User chooses which to keep (default: one with more events)
- API: `POST /api/v1/entities/merge` with primary_id, secondary_id
- Transaction: update all event entity_ids, then delete secondary
- Backlog: IMP-015

---

### Story P9-4.6: Store Manual Adjustments for Future Matching

As a **system**,
I want **to record all manual entity adjustments**,
So that **future AI/ML can learn from user corrections**.

**Acceptance Criteria:**

**Given** a user unlinks an event from an entity
**When** the action completes
**Then** an adjustment record is created with: event_id, old_entity_id, null, action="unlink", timestamp

**Given** a user assigns an event to an entity
**When** the action completes
**Then** an adjustment record is created with: event_id, null, new_entity_id, action="assign", timestamp

**Given** a user merges entities
**When** the action completes
**Then** adjustment records are created for each moved event

**Prerequisites:** P9-4.3, P9-4.4, P9-4.5

**Technical Notes:**
- Create `entity_adjustment` table: id, event_id, old_entity_id, new_entity_id, action, user_id, created_at
- Actions: "unlink", "assign", "move", "merge"
- This data enables future ML training on corrections
- Consider export endpoint for training data
- Foundation for IMP-016 (MCP server context)
- Backlog: IMP-015, IMP-016

---

## Epic P9-5: Infrastructure & DevOps

**Goal:** Establish secure connections and automated development pipelines.

**Value:** Production-ready security with HTTPS. 24/7 development capability with n8n automation.

**Backlog Items:** IMP-009, FF-027

---

### Story P9-5.1: Add SSL/HTTPS Support to Backend

As a **user**,
I want **to access ArgusAI over HTTPS**,
So that **my connection is secure and push notifications work (requires secure context)**.

**Acceptance Criteria:**

**Given** SSL certificates are configured
**When** I access ArgusAI
**Then** the connection is over HTTPS (TLS 1.2+)
**And** the browser shows a secure connection indicator

**Given** I access via HTTP
**When** HTTPS is enabled
**Then** I am redirected to HTTPS

**Given** certificates are not configured
**When** I start ArgusAI
**Then** it runs on HTTP with a warning in logs
**And** push notifications warn about requiring HTTPS

**Prerequisites:** P9-1.1

**Technical Notes:**
- Add SSL configuration to uvicorn startup
- Support certificate file paths: `SSL_CERT_FILE`, `SSL_KEY_FILE`
- Add HTTP to HTTPS redirect middleware
- Update CORS settings for HTTPS origin
- Document certificate location expectations
- Test with self-signed certs locally
- Backlog: IMP-009

---

### Story P9-5.2: Add Certificate Generation to Install Script

As a **user**,
I want **easy options for setting up SSL certificates**,
So that **I don't need to manually configure security**.

**Acceptance Criteria:**

**Given** I run the install script
**When** prompted for SSL configuration
**Then** I see options:
1. Let's Encrypt (requires domain)
2. Self-signed certificate
3. Skip (HTTP only)

**Given** I choose Let's Encrypt
**When** I provide my domain
**Then** certbot runs and obtains certificates
**And** auto-renewal is configured

**Given** I choose Self-signed
**When** certificate generation runs
**Then** a self-signed cert is created in `data/certs/`
**And** I'm warned about browser security warnings

**Prerequisites:** P9-5.1

**Technical Notes:**
- Add SSL section to install.sh
- Let's Encrypt: use certbot with standalone or webroot
- Self-signed: `openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem`
- Store certs in `data/certs/` directory
- Add certbot cron job for renewal
- Update nginx template for SSL termination option
- Backlog: IMP-009

---

### Story P9-5.3: Deploy n8n Instance

As a **developer**,
I want **n8n deployed alongside ArgusAI**,
So that **I can create automation workflows**.

**Acceptance Criteria:**

**Given** I want to use n8n automation
**When** I run the n8n setup script
**Then** n8n is installed via Docker or npm
**And** n8n is accessible at a configured port (default: 5678)
**And** n8n data is persisted in `data/n8n/`

**Given** n8n is running
**When** I access the n8n UI
**Then** I can create and manage workflows
**And** I can configure credentials securely

**Prerequisites:** P9-5.1

**Technical Notes:**
- Create `scripts/setup-n8n.sh`
- Docker: `docker run -d -p 5678:5678 -v ./data/n8n:/home/node/.n8n n8nio/n8n`
- Alternative: npm install n8n -g
- Add n8n to systemd service file
- Configure n8n webhook URL for external triggers
- Add n8n URL to ArgusAI configuration
- Backlog: FF-027

---

### Story P9-5.4: Create n8n Claude Code Integration

As a **developer**,
I want **n8n workflows to execute Claude Code CLI commands**,
So that **AI can generate and modify code automatically**.

**Acceptance Criteria:**

**Given** an n8n workflow triggers code generation
**When** the Claude Code node executes
**Then** it runs `claude-code` CLI with the specified prompt
**And** the output (code changes, responses) is captured

**Given** Claude Code makes file changes
**When** the workflow continues
**Then** subsequent nodes can access the changed files
**And** git status shows the modifications

**Prerequisites:** P9-5.3

**Technical Notes:**
- Create custom n8n node or use Execute Command node
- Claude Code CLI: `claude-code --prompt "Create function X"`
- Parse Claude Code output for success/failure
- Capture stdout/stderr for logging
- Handle authentication (API key in n8n credentials)
- Consider rate limiting to avoid API throttling
- Backlog: FF-027

---

### Story P9-5.5: Create n8n BMAD Workflow Integration

As a **developer**,
I want **n8n to execute BMAD method workflows**,
So that **story creation and development follow our methodology**.

**Acceptance Criteria:**

**Given** n8n receives a trigger (new story needed)
**When** the BMAD workflow node executes
**Then** it invokes the appropriate BMAD skill (create-story, dev-story, etc.)
**And** the workflow waits for completion

**Given** BMAD workflow completes
**When** n8n processes the result
**Then** it extracts story details, status, and artifacts
**And** subsequent nodes can act on this data

**Prerequisites:** P9-5.4

**Technical Notes:**
- BMAD skills are invoked via Claude Code CLI
- Workflow: `claude-code --skill bmad:bmm:workflows:create-story`
- Parse output for story file path and content
- Chain workflows: create-story → story-context → dev-story
- Handle workflow failures gracefully
- Log all BMAD workflow executions
- Backlog: FF-027

---

### Story P9-5.6: Build n8n Monitoring Dashboard and Approval Gates

As a **developer**,
I want **to monitor pipeline status and approve changes before merge**,
So that **automation doesn't proceed without human oversight when needed**.

**Acceptance Criteria:**

**Given** n8n workflows are running
**When** I view the dashboard
**Then** I see: active workflows, recent executions, success/failure rates, queue depth

**Given** a workflow reaches an approval gate
**When** human review is required
**Then** the workflow pauses and sends notification (Slack/Discord/email)
**And** I can approve or reject via dashboard or notification link

**Given** I approve a pending workflow
**When** approval is recorded
**Then** the workflow resumes from the approval node
**And** the approval is logged with timestamp and approver

**Prerequisites:** P9-5.5

**Technical Notes:**
- Use n8n's built-in execution monitoring
- Create custom dashboard page or use n8n's native UI
- Approval gate: use Wait node with webhook resume
- Send notifications via n8n Slack/Discord/Email nodes
- Create approval API endpoint that resumes workflow
- Log all approvals for audit trail
- Backlog: FF-027

---

## Epic P9-6: Documentation & UX Polish

**Goal:** Update documentation to reflect current state and polish UI rough edges.

**Value:** New users can onboard easily. Existing users have smoother experience.

**Backlog Items:** IMP-004, IMP-005, IMP-008, IMP-010, IMP-017, FF-011, FF-026

---

### Story P9-6.1: Refactor README.md

As a **new user or contributor**,
I want **the README to accurately reflect current features**,
So that **I understand what ArgusAI can do and how to get started**.

**Acceptance Criteria:**

**Given** I view the README
**When** I read the feature list
**Then** it includes all implemented features through Phase 8:
- UniFi Protect integration
- Multi-frame video analysis
- Entity recognition
- Daily summaries
- Push notifications
- MQTT/Home Assistant
- HomeKit integration

**Given** I want to install ArgusAI
**When** I follow the installation section
**Then** instructions match the current install script
**And** prerequisites are accurate (Python 3.11+, Node 18+)

**Prerequisites:** P9-1.1

**Technical Notes:**
- Review existing README for outdated content
- Add feature badges for key capabilities
- Update architecture diagram if changed
- Add troubleshooting section for common issues
- Include links to /docs folder for detailed documentation
- Add contributor guidelines
- Backlog: IMP-017

---

### Story P9-6.2: Set Up GitHub Pages Infrastructure

As a **project maintainer**,
I want **GitHub Pages configured for the project**,
So that **we can host public documentation**.

**Acceptance Criteria:**

**Given** GitHub Pages is enabled
**When** content is pushed to the docs branch/folder
**Then** the site is built and deployed automatically

**Given** I choose a static site generator
**When** the infrastructure is set up
**Then** the generator (Jekyll/Hugo/Docusaurus) is configured
**And** build commands are documented

**Prerequisites:** P9-6.1

**Technical Notes:**
- Enable GitHub Pages in repo settings
- Choose generator: Docusaurus (React-based, good for docs)
- Create `docs-site/` folder or use `gh-pages` branch
- Add `.github/workflows/deploy-docs.yml` for CI
- Configure custom domain if desired
- Backlog: FF-026

---

### Story P9-6.3: Build GitHub Pages Landing Page

As a **visitor**,
I want **an attractive landing page explaining ArgusAI**,
So that **I can quickly understand if it meets my needs**.

**Acceptance Criteria:**

**Given** I visit the GitHub Pages URL
**When** the landing page loads
**Then** I see:
- Project name and tagline
- Hero image/screenshot
- Key features (3-5 bullet points)
- "Get Started" button linking to installation docs

**Given** I'm on mobile
**When** I view the landing page
**Then** it's responsive and readable

**Prerequisites:** P9-6.2

**Technical Notes:**
- Create index page with hero section
- Add feature grid with icons
- Include screenshot carousel or single hero image
- Add footer with GitHub link, license info
- Optimize images for web
- Backlog: FF-026

---

### Story P9-6.4: Create GitHub Pages Documentation Section

As a **user**,
I want **comprehensive documentation on the project site**,
So that **I can learn how to configure and use ArgusAI**.

**Acceptance Criteria:**

**Given** I navigate to the documentation section
**When** I view the sidebar/menu
**Then** I see organized categories:
- Getting Started
- Installation
- Configuration
- Features
- API Reference
- Troubleshooting

**Given** I search for a topic
**When** I enter a search query
**Then** relevant docs are shown

**Prerequisites:** P9-6.3

**Technical Notes:**
- Migrate/adapt content from /docs folder
- Use Docusaurus docs feature with sidebar
- Add search (Algolia DocSearch or local search)
- Include code examples with syntax highlighting
- Add version selector if maintaining multiple versions
- Backlog: FF-026

---

### Story P9-6.5: Fix Events Page Button Positioning

As a **user**,
I want **action buttons that don't overlap with navigation**,
So that **I can easily use both**.

**Acceptance Criteria:**

**Given** I view the Events page on desktop
**When** I look at the action buttons (Select All, Refresh, Delete)
**Then** they don't overlap with the top-right navigation/user buttons
**And** there's clear visual separation

**Given** I view the Events page on mobile
**When** I look at the action buttons
**Then** they're positioned appropriately without overlap
**And** touch targets are at least 44x44px

**Prerequisites:** P9-1.1

**Technical Notes:**
- Add margin-top to action bar: `mt-4` or `mt-6`
- Ensure header has fixed height for consistent spacing
- Test at various viewport widths (320px - 1920px)
- Adjust z-index if layering issues exist
- Backlog: IMP-010

---

### Story P9-6.6: Hide MQTT Form When Disabled

As a **user**,
I want **MQTT settings hidden when integration is disabled**,
So that **the UI is cleaner and less confusing**.

**Acceptance Criteria:**

**Given** MQTT integration is disabled (toggle off)
**When** I view Settings > Integrations
**Then** I only see the enable/disable toggle
**And** the configuration form (host, port, username, etc.) is hidden

**Given** I enable MQTT integration
**When** the toggle is turned on
**Then** the configuration form smoothly appears
**And** fields are ready for input

**Prerequisites:** P9-1.1

**Technical Notes:**
- Wrap MQTT form fields in conditional render
- Use CSS transition for smooth show/hide
- Preserve form values when hidden (don't reset)
- Apply same pattern to other optional integrations
- Backlog: IMP-008

---

### Story P9-6.7: Add Skip to Content Link

As a **keyboard user**,
I want **a skip link to bypass navigation**,
So that **I can quickly access main content**.

**Acceptance Criteria:**

**Given** I navigate to any page using keyboard
**When** I press Tab as first action
**Then** a "Skip to content" link becomes visible
**And** it's focused and clearly styled

**Given** I activate the skip link (Enter key)
**When** focus moves
**Then** it jumps to the main content area
**And** I can immediately interact with page content

**Prerequisites:** P9-1.1

**Technical Notes:**
- Add skip link as first focusable element in layout
- Style: visually hidden until focused (sr-only focus:not-sr-only)
- Link href="#main-content"
- Add id="main-content" to main content wrapper
- Ensure main content is focusable (tabindex="-1")
- Backlog: IMP-004

---

### Story P9-6.8: Add Camera List Optimizations and Test Connection

As a **user with many cameras**,
I want **the camera list to perform well**,
So that **the UI remains responsive**.

**Acceptance Criteria:**

**Given** I have 10+ cameras configured
**When** I view the Cameras page
**Then** the list renders without lag
**And** scrolling is smooth (60fps)

**Given** I'm adding a new camera
**When** I enter RTSP URL and credentials
**Then** I see a "Test Connection" button
**And** clicking it validates the camera without saving

**Given** I test a valid camera connection
**When** the test succeeds
**Then** I see "Connection successful" with a preview thumbnail
**And** I can proceed to save

**Prerequisites:** P9-1.1

**Technical Notes:**
- Wrap CameraCard in React.memo()
- Add virtualization if list > 20 items (react-window)
- Create `POST /api/v1/cameras/test` endpoint
- Test endpoint: connect to RTSP, grab frame, validate, return thumbnail
- Don't persist test camera to database
- Backlog: IMP-005, FF-011

---

## FR Coverage Matrix

| FR | Description | Epic | Story | Status |
|----|-------------|------|-------|--------|
| FR1 | CI pipeline passes | P9-1 | 1.1 | Pending |
| FR2 | Push notifications reliable | P9-1 | 1.2 | Pending |
| FR3 | Filter settings persist | P9-1 | 1.3 | Pending |
| FR4 | Re-analyse works | P9-1 | 1.4 | Pending |
| FR5 | Prompt refinement submits | P9-1 | 1.5 | Pending |
| FR6 | Show AI model | P9-1 | 1.6 | Pending |
| FR7 | Save/replace button | P9-1 | 1.7 | Pending |
| FR8 | Frame timing | P9-2 | 2.1 | Pending |
| FR9 | Adaptive sampling | P9-2 | 2.2, 2.3 | Pending |
| FR10 | Configurable frames | P9-2 | 2.4 | Pending |
| FR11 | Store frames | P9-2 | 2.5 | Pending |
| FR12 | Clickable thumbnails | P9-2 | 2.6 | Pending |
| FR13 | Frame gallery | P9-2 | 2.6 | Pending |
| FR14 | Sampling strategy | P9-2 | 2.7 | Pending |
| FR15 | Prioritize activity | P9-2 | 2.3 | Pending |
| FR16 | Camera in prompt | P9-3 | 3.1 | Pending |
| FR17 | Time in prompt | P9-3 | 3.1 | Pending |
| FR18 | Read overlay | P9-3 | 3.2 | Pending |
| FR19 | Fallback metadata | P9-3 | 3.2 | Pending |
| FR20 | Mark false positives | P9-3 | 3.3 | Pending |
| FR21 | Store feedback | P9-3 | 3.3 | Pending |
| FR22 | Summary feedback | P9-3 | 3.4 | Pending |
| FR23 | Summary prompt | P9-3 | 3.5 | Pending |
| FR24 | Summary in stats | P9-3 | 3.6 | Pending |
| FR25 | Vehicle separation | P9-4 | 4.1 | Pending |
| FR26 | Distinct entities | P9-4 | 4.1 | Pending |
| FR27 | Entity event list | P9-4 | 4.2 | Pending |
| FR28 | Unlink events | P9-4 | 4.3 | Pending |
| FR29 | Add to entity | P9-4 | 4.4 | Pending |
| FR30 | Move events | P9-4 | 4.4 | Pending |
| FR31 | Merge entities | P9-4 | 4.5 | Pending |
| FR32 | Store adjustments | P9-4 | 4.6 | Pending |
| FR33 | SSL/HTTPS | P9-5 | 5.1 | Pending |
| FR34 | Let's Encrypt | P9-5 | 5.2 | Pending |
| FR35 | Self-signed | P9-5 | 5.2 | Pending |
| FR36 | n8n deploy | P9-5 | 5.3 | Pending |
| FR37 | Claude Code | P9-5 | 5.4 | Pending |
| FR38 | BMAD integration | P9-5 | 5.5 | Pending |
| FR39 | n8n dashboard | P9-5 | 5.6 | Pending |
| FR40 | Approval gates | P9-5 | 5.6 | Pending |
| FR41 | README features | P9-6 | 6.1 | Pending |
| FR42 | README install | P9-6 | 6.1 | Pending |
| FR43 | GH Pages landing | P9-6 | 6.2, 6.3 | Pending |
| FR44 | GH Pages docs | P9-6 | 6.4 | Pending |
| FR45 | Auto-deploy | P9-6 | 6.2 | Pending |
| FR46 | Button positioning | P9-6 | 6.5 | Pending |
| FR47 | Hide MQTT form | P9-6 | 6.6 | Pending |
| FR48 | Skip to content | P9-6 | 6.7 | Pending |
| FR49 | Camera list memo | P9-6 | 6.8 | Pending |
| FR50 | Test connection | P9-6 | 6.8 | Pending |

**Coverage: 50/50 FRs mapped (100%)**

---

## Summary

### Epic Breakdown Summary

| Epic | Stories | Priority | Backlog Items |
|------|---------|----------|---------------|
| P9-1: Critical Bug Fixes | 8 | P1 | BUG-005, BUG-007, BUG-008, BUG-009, BUG-010, BUG-011 |
| P9-2: Frame Capture & Video | 7 | P2 | IMP-006, IMP-007, IMP-011, FF-020, FF-021 |
| P9-3: AI Context & Accuracy | 6 | P2 | IMP-012, IMP-013, IMP-014, FF-023 |
| P9-4: Entity Management | 6 | P2 | BUG-011, IMP-015, IMP-016 |
| P9-5: Infrastructure & DevOps | 6 | P2 | IMP-009, FF-027 |
| P9-6: Documentation & UX | 8 | P3 | IMP-004, IMP-005, IMP-008, IMP-010, IMP-017, FF-011, FF-026 |
| **Total** | **41** | | **26 backlog items** |

### Recommended Execution Order

1. **P9-1.1** - Fix CI first (unblocks all other work)
2. **P9-1.2 - P9-1.8** - Complete remaining bug fixes
3. **P9-2** - Frame capture improvements (high user impact)
4. **P9-3** - AI accuracy improvements (core value)
5. **P9-4** - Entity management (depends on P9-3)
6. **P9-5** - Infrastructure (can parallel with P9-4)
7. **P9-6** - Documentation & polish (lowest dependency)

---

_For implementation: Use the `create-story` workflow to generate individual story implementation plans from this epic breakdown._

_This document will be updated after Architecture workflow to incorporate technical decisions._
