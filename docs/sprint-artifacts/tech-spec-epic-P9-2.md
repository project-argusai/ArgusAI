# Epic Technical Specification: Frame Capture & Video Analysis

Date: 2025-12-22
Author: Brent
Epic ID: P9-2
Status: Draft

---

## Overview

Epic P9-2 focuses on improving the video analysis pipeline by fixing frame capture timing issues and implementing intelligent frame selection. Currently, captured frames often miss the actual motion activity, showing moments before or after the action. This epic introduces adaptive frame sampling using similarity detection and motion scoring, configurable frame counts, frame storage with gallery viewing, and user-selectable sampling strategies.

The improvements will ensure AI analyzes the most relevant frames, leading to more accurate descriptions while potentially reducing AI costs through smarter frame selection.

## Objectives and Scope

**In Scope:**
- Investigate and fix frame capture timing offset (IMP-011)
- Implement similarity-based frame filtering (FF-020)
- Add motion scoring to frame selection (FF-020)
- Add configurable frame count setting (IMP-007)
- Store all analysis frames to filesystem (IMP-006)
- Build frame gallery modal component (IMP-006)
- Add frame sampling strategy selection (FF-021)

**Out of Scope:**
- Query-adaptive frame selection (FF-022) - requires embedding infrastructure
- Full video storage and playback (partially implemented in Phase 8)
- AI model changes
- Real-time streaming analysis

## System Architecture Alignment

This epic builds on the Phase 8 architecture for frame storage and extends the frame extraction service:

| Component | Files Affected | Changes |
|-----------|---------------|---------|
| Frame Extraction | `backend/app/services/frame_extraction_service.py` | Add timing offset, adaptive sampling |
| Adaptive Sampler | `backend/app/services/adaptive_sampler.py` | Enhance with motion scoring |
| Frame Storage | `backend/app/services/frame_storage_service.py` | Already exists from P8 |
| Event Model | `backend/app/models/event.py` | Add timing metadata |
| Settings Model | `backend/app/models/settings.py` | Add frame config options |
| Settings API | `backend/app/api/v1/system.py` | Expose new settings |
| Settings UI | `frontend/components/settings/GeneralSettings.tsx` | Add frame settings |
| Frame Gallery | `frontend/components/events/FrameGalleryModal.tsx` | Build new component |
| Event Card | `frontend/components/events/EventCard.tsx` | Add clickable thumbnail |

### Architecture Diagram

```
Protect Event → Clip Download → Timing Offset → Frame Extraction
                                    ↓
                            Raw Frames (100+)
                                    ↓
                    ┌───────────────┼───────────────┐
                    ↓               ↓               ↓
                Uniform         Adaptive         Hybrid
              (fixed N)      (similarity)    (dense + filter)
                    ↓               ↓               ↓
                    └───────────────┼───────────────┘
                                    ↓
                          Motion Scoring
                                    ↓
                         Top N Frames Selected
                                    ↓
                    ┌───────────────┼───────────────┐
                    ↓               ↓               ↓
              Frame Storage    AI Analysis    Gallery Display
```

---

## Detailed Design

### Services and Modules

| Service/Module | Responsibility | Inputs | Outputs |
|---------------|----------------|--------|---------|
| FrameExtractionService | Extract frames from video clips | Video file, config | Raw frames array |
| AdaptiveSampler | Select diverse, high-activity frames | Raw frames, target count | Selected frames |
| FrameStorageService | Persist frames to filesystem | Frames, event_id | File paths |
| MotionScorer | Calculate motion magnitude per frame | Frame sequence | Motion scores |
| SimilarityFilter | Filter redundant frames | Frames, threshold | Unique frames |

### Data Models and Contracts

**Extended Event Model:**
```python
class Event(Base):
    # Existing fields...

    # Phase 9 additions
    frame_extraction_offset_ms: int = 0  # Timing offset applied
    motion_scores: JSON = []  # Per-frame motion scores
    sampling_strategy_used: str = "uniform"  # Strategy actually used
```

**New Settings Keys:**
```python
# System Settings additions
FRAME_SETTINGS = {
    "analysis_frame_count": 10,           # 5, 10, 15, 20
    "frame_sampling_strategy": "adaptive", # uniform, adaptive, hybrid
    "frame_extraction_offset_ms": 2000,    # Default 2 second offset
    "similarity_threshold": 0.95,          # SSIM threshold
    "motion_weight": 0.6,                  # Weight for motion vs uniqueness
}
```

**Frame Selection Result:**
```python
@dataclass
class FrameSelectionResult:
    frames: List[np.ndarray]
    indices: List[int]           # Original frame indices
    timestamps: List[int]        # Timestamp offsets in ms
    motion_scores: List[float]   # 0-100 motion score per frame
    similarity_scores: List[float]  # Similarity to previous selected
```

### APIs and Interfaces

**Settings Endpoints (modified):**

| Method | Path | Changes |
|--------|------|---------|
| GET | `/api/v1/system/settings` | Include new frame settings |
| PUT | `/api/v1/system/settings` | Accept new frame settings |

**Settings Response (frame section):**
```json
{
  "frame_settings": {
    "analysis_frame_count": 10,
    "frame_sampling_strategy": "adaptive",
    "frame_extraction_offset_ms": 2000,
    "similarity_threshold": 0.95
  }
}
```

**Frame Gallery Endpoint (existing from P8):**
```
GET /api/v1/events/{event_id}/frames
```

**Response with motion scores:**
```json
{
  "event_id": "uuid",
  "frame_count": 10,
  "sampling_strategy": "adaptive",
  "extraction_offset_ms": 2000,
  "frames": [
    {
      "frame_number": 1,
      "url": "/api/v1/events/{event_id}/frames/1",
      "timestamp_offset_ms": 2000,
      "motion_score": 85.5,
      "width": 1920,
      "height": 1080
    }
  ]
}
```

### Workflows and Sequencing

**Frame Extraction Pipeline (Updated):**

```
1. Event Triggered
   ├── Download video clip from Protect
   └── Store clip temporarily

2. Apply Timing Offset
   ├── Read frame_extraction_offset_ms from settings
   ├── Skip initial frames based on offset
   └── Log offset applied

3. Extract Raw Frames
   ├── Extract all frames from offset to end
   ├── Target: 50-200 raw frames depending on clip length
   └── Store frame timestamps

4. Apply Sampling Strategy
   ├── If "uniform": Select every Nth frame
   ├── If "adaptive":
   │   ├── Calculate similarity between consecutive frames
   │   ├── Filter frames with >95% similarity
   │   └── Calculate motion score for remaining
   └── If "hybrid":
       ├── Extract dense (every 3rd frame)
       └── Apply adaptive filtering

5. Select Final Frames
   ├── Score = (motion_weight * motion) + ((1 - motion_weight) * uniqueness)
   ├── Select top N frames by score
   └── Sort chronologically

6. Store and Analyze
   ├── Save frames to filesystem
   ├── Store metadata in database
   ├── Send to AI for analysis
   └── Update event with results
```

**Motion Scoring Algorithm:**

```python
def calculate_motion_score(prev_frame, curr_frame, next_frame):
    """Calculate motion magnitude using optical flow."""
    # Convert to grayscale
    prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    curr_gray = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)

    # Calculate optical flow
    flow = cv2.calcOpticalFlowFarneback(
        prev_gray, curr_gray, None,
        pyr_scale=0.5, levels=3, winsize=15,
        iterations=3, poly_n=5, poly_sigma=1.2, flags=0
    )

    # Calculate magnitude
    magnitude, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])

    # Normalize to 0-100
    score = min(100, np.mean(magnitude) * 10)
    return score
```

**Similarity Filtering Algorithm:**

```python
def is_similar(frame1, frame2, threshold=0.95):
    """Check if frames are too similar using SSIM."""
    gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)

    # Resize for faster comparison
    gray1 = cv2.resize(gray1, (256, 256))
    gray2 = cv2.resize(gray2, (256, 256))

    score = ssim(gray1, gray2)
    return score > threshold
```

---

## Non-Functional Requirements

### Performance

| Metric | Target | Measurement |
|--------|--------|-------------|
| Frame extraction | <2 seconds for 100 frames | Time from clip to raw frames |
| Similarity filtering | <500ms for 100 frames | Time to filter |
| Motion scoring | <1 second for 100 frames | Time to score |
| Total pipeline | <5 seconds | End-to-end frame selection |
| Frame gallery load | <500ms | Time to display gallery |

### Storage

| Item | Size | Retention |
|------|------|-----------|
| Single frame JPEG | ~50KB (quality 85) | Event retention policy |
| 10 frames per event | ~500KB | Event retention policy |
| 100 events/day | ~50MB/day | Configurable |

### Reliability

- Frame extraction must handle corrupt video gracefully
- Adaptive sampling must fall back to uniform if errors occur
- Gallery must handle missing frames gracefully
- Settings changes apply to new events only (don't reprocess)

### Observability

- Log frame extraction timing and offset applied
- Log sampling strategy decision points
- Log motion scores for debugging
- Track frames extracted vs frames selected ratio

---

## Dependencies and Integrations

### Backend Dependencies

```
# Existing - used for frame processing
opencv-python>=4.12.0
numpy>=1.24.0
scikit-image>=0.22.0  # For SSIM (already added in P8)
PyAV>=12.0.0          # For video decoding
```

### Frontend Dependencies

```json
{
  "dependencies": {
    "yet-another-react-lightbox": "^3.17.0"  // Already added in P8
  }
}
```

### Internal Dependencies

| Dependency | Version | Purpose |
|------------|---------|---------|
| FrameStorageService | P8 | Store extracted frames |
| ClipService | P3 | Download video clips |
| AIService | P3 | Analyze selected frames |
| EventModel | P1 | Store frame metadata |

---

## Acceptance Criteria (Authoritative)

### P9-2.1: Investigate and Fix Frame Capture Timing

**AC-2.1.1:** Given a motion event triggers, when frames are extracted, then at least 80% show the subject in frame
**AC-2.1.2:** Given timing offset is configurable, when I set offset to 3000ms, then extraction starts 3 seconds into clip
**AC-2.1.3:** Given default offset, when person event occurs, then person is visible in majority of frames
**AC-2.1.4:** Given default offset, when vehicle event occurs, then vehicle is visible in majority of frames
**AC-2.1.5:** Given extraction fails, when error occurs, then fallback to 0 offset with warning

### P9-2.2: Implement Similarity-Based Frame Filtering

**AC-2.2.1:** Given 100 raw frames extracted, when similarity filtering runs, then frames with >95% SSIM are removed
**AC-2.2.2:** Given consecutive identical frames, when filtering runs, then only first is kept
**AC-2.2.3:** Given visually distinct frames, when filtering runs, then all are retained
**AC-2.2.4:** Given filtering completes, when viewing logs, then filter ratio is logged (e.g., "Filtered 100→45 frames")

### P9-2.3: Add Motion Scoring to Frame Selection

**AC-2.3.1:** Given filtered frames, when motion scoring runs, then each frame gets score 0-100
**AC-2.3.2:** Given frame with moving person, when scored, then score >50
**AC-2.3.3:** Given static frame (no movement), when scored, then score <20
**AC-2.3.4:** Given final selection, when sorted, then highest combined scores selected
**AC-2.3.5:** Given selection complete, when stored, then motion_scores saved with event

### P9-2.4: Add Configurable Frame Count Setting

**AC-2.4.1:** Given Settings > General page, when viewing, then "Frames per Analysis" dropdown visible
**AC-2.4.2:** Given dropdown, when clicked, then options 5, 10, 15, 20 available
**AC-2.4.3:** Given I change from 10 to 15, when saving, then warning modal appears about cost
**AC-2.4.4:** Given I confirm warning, when saved, then setting persists
**AC-2.4.5:** Given new event, when processed, then configured frame count used

### P9-2.5: Store All Analysis Frames to Filesystem

**AC-2.5.1:** Given event analyzed with 10 frames, when complete, then 10 JPEGs in `data/frames/{event_id}/`
**AC-2.5.2:** Given frames saved, when checking files, then named `frame_001.jpg` through `frame_010.jpg`
**AC-2.5.3:** Given frames saved, when checking database, then frame_paths JSON contains paths
**AC-2.5.4:** Given event deleted, when cleanup runs, then frame files deleted
**AC-2.5.5:** Given frame save fails, when error occurs, then event still processes with warning

### P9-2.6: Build Frame Gallery Modal Component

**AC-2.6.1:** Given event card, when I click thumbnail, then gallery modal opens
**AC-2.6.2:** Given gallery open, when viewing, then all frames displayed as thumbnails
**AC-2.6.3:** Given gallery open, when I click frame, then enlarged view shows
**AC-2.6.4:** Given enlarged view, when I press arrow keys, then navigate between frames
**AC-2.6.5:** Given gallery open, when viewing frame, then "3 of 10" counter displays
**AC-2.6.6:** Given gallery open, when viewing frame, then motion score displays (if available)
**AC-2.6.7:** Given gallery open, when I press Escape, then modal closes
**AC-2.6.8:** Given gallery on mobile, when swiping, then navigate between frames

### P9-2.7: Add Frame Sampling Strategy Setting

**AC-2.7.1:** Given Settings > General, when viewing, then "Frame Sampling Strategy" dropdown visible
**AC-2.7.2:** Given dropdown, when clicked, then options: Uniform, Adaptive, Hybrid
**AC-2.7.3:** Given I hover option, when tooltip shows, then strategy explanation displayed
**AC-2.7.4:** Given I select Adaptive, when saved, then new events use adaptive sampling
**AC-2.7.5:** Given event processed, when viewing event, then strategy_used field shows which was used

---

## Traceability Mapping

| AC | Spec Section | Component(s) | Test Idea |
|----|--------------|--------------|-----------|
| AC-2.1.1-5 | Frame Extraction | frame_extraction_service.py | Test with sample clips |
| AC-2.2.1-4 | Similarity Filter | adaptive_sampler.py | Unit test with similar frames |
| AC-2.3.1-5 | Motion Scoring | adaptive_sampler.py | Unit test with motion clips |
| AC-2.4.1-5 | Settings UI | GeneralSettings.tsx, system.py | Component + integration test |
| AC-2.5.1-5 | Frame Storage | frame_storage_service.py | Integration test |
| AC-2.6.1-8 | Gallery Modal | FrameGalleryModal.tsx | Component + E2E test |
| AC-2.7.1-5 | Strategy Setting | GeneralSettings.tsx, settings | Component + integration test |

---

## Risks, Assumptions, Open Questions

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Optimal timing offset varies by camera | High | Medium | Make offset configurable per-camera in future |
| SSIM too slow for large frames | Medium | Medium | Resize frames before comparison |
| Motion scoring fails on static cameras | Low | Low | Fall back to uniform sampling |
| Different event types need different offsets | Medium | Medium | Consider per-event-type offsets |

### Assumptions

- Protect clips are at least 5 seconds long
- Motion events have detectable motion in frames
- 95% SSIM threshold is appropriate for most cameras
- Users prefer quality over speed for frame selection

### Open Questions

- **Q1:** Should timing offset be configurable per-camera or globally?
  - **A:** Start global, add per-camera in future phase if needed

- **Q2:** What's the right balance between motion score and uniqueness?
  - **A:** Default 60% motion, 40% uniqueness - make configurable later

- **Q3:** Should we show motion scores in the gallery?
  - **A:** Yes, helps users understand why frames were selected

- **Q4:** Handle clips shorter than offset?
  - **A:** If clip < offset, use offset of 0 with warning

---

## Test Strategy Summary

### Test Levels

| Level | Scope | Tools | Coverage |
|-------|-------|-------|----------|
| Unit | Sampling algorithms | pytest | Similarity, motion scoring |
| Integration | Frame pipeline | pytest | End-to-end extraction |
| Component | Gallery modal | vitest, RTL | UI interactions |
| E2E | Settings → Analysis | Manual | Full workflow |

### Test Cases by Story

**P9-2.1 (Timing):**
- Unit: Offset calculation
- Integration: Extract with various offsets
- Manual: Verify frame content quality

**P9-2.2 (Similarity):**
- Unit: SSIM calculation
- Unit: Filter with identical frames
- Unit: Filter with diverse frames
- Performance: 100 frames in <500ms

**P9-2.3 (Motion):**
- Unit: Optical flow calculation
- Unit: Score normalization
- Integration: Combined scoring

**P9-2.4 (Frame Count):**
- Component: Dropdown renders
- Component: Warning modal
- Integration: Setting persists
- E2E: New event uses setting

**P9-2.5 (Storage):**
- Integration: Files created
- Integration: DB records match files
- Integration: Cleanup on delete

**P9-2.6 (Gallery):**
- Component: Modal opens/closes
- Component: Navigation works
- Component: Keyboard navigation
- Component: Mobile swipe

**P9-2.7 (Strategy):**
- Component: Dropdown renders
- Component: Tooltips display
- Integration: Strategy applied

### Test Data

- Sample clips with clear motion (person walking)
- Sample clips with minimal motion (static scene)
- Sample clips with fast motion (vehicle)
- Sample clips with multiple subjects
- Edge cases: very short clips, corrupt frames

---

_Generated by BMAD Epic Tech Context Workflow_
_Date: 2025-12-22_
_For: Brent_
