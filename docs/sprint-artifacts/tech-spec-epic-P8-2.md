# Epic Technical Specification: Video Analysis Enhancements

Date: 2025-12-20
Author: Brent
Epic ID: P8-2
Status: Draft

---

## Overview

Epic P8-2 enhances ArgusAI's video analysis capabilities by implementing frame storage, user-configurable frame counts, and adaptive content-aware frame sampling. Currently, frames extracted for AI analysis are discarded after processing. This epic enables users to review exactly what the AI saw, configure analysis depth, and benefit from smarter frame selection that prioritizes motion and content changes over uniform sampling.

These enhancements address backlog items IMP-006, IMP-007, FF-020, and FF-021, providing better AI descriptions through smarter frame selection while giving users control over the quality-vs-cost tradeoff.

## Objectives and Scope

### In Scope

- **P8-2.1**: Store all frames used for AI analysis to filesystem with database metadata
- **P8-2.2**: Create clickable thumbnail → frame gallery modal on event cards
- **P8-2.3**: Add configurable frame count setting (5/10/15/20) with cost warning modal
- **P8-2.4**: Implement adaptive frame sampling using hybrid histogram + SSIM algorithm
- **P8-2.5**: Add frame sampling strategy selection in settings (uniform/adaptive/hybrid)

### Out of Scope

- Query-adaptive frame selection (FR10 - deferred to future phase)
- Per-camera frame count overrides (future enhancement)
- Video storage (covered in P8-3)
- Frame editing or annotation features

## System Architecture Alignment

### Architecture Decisions (from architecture-phase8.md)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Frame Storage | Filesystem + DB metadata | Matches thumbnail pattern, performant |
| Adaptive Sampling | Hybrid (Histogram + SSIM) | Balance of speed and quality |
| Frame File Format | JPEG, quality 85 | ~50KB per frame, good quality |
| Frame Naming | `frame_{NNN}.jpg` | Zero-padded, sortable |

### Components Referenced

| Component | Location | Stories Affected |
|-----------|----------|------------------|
| Frame Extraction Service | `backend/app/services/frame_extraction_service.py` | All |
| Event Processor | `backend/app/services/event_processor.py` | P8-2.1 |
| Events API | `backend/app/api/v1/events.py` | P8-2.2 |
| EventCard Component | `frontend/components/events/EventCard.tsx` | P8-2.2 |
| General Settings | `frontend/components/settings/GeneralSettings.tsx` | P8-2.3, P8-2.5 |
| System Settings API | `backend/app/api/v1/system.py` | P8-2.3, P8-2.5 |

### New Components

| Component | Location | Purpose |
|-----------|----------|---------|
| EventFrame Model | `backend/app/models/event_frame.py` | Database model for frame metadata |
| FrameStorageService | `backend/app/services/frame_storage_service.py` | Save/delete frames |
| AdaptiveSampler | `backend/app/services/adaptive_sampler.py` | Content-aware frame selection |
| FrameGalleryModal | `frontend/components/events/FrameGalleryModal.tsx` | Frame viewing lightbox |
| CostWarningModal | `frontend/components/settings/CostWarningModal.tsx` | Frame count warning |

---

## Detailed Design

### Services and Modules

| Service/Module | Responsibility | Inputs | Outputs |
|----------------|----------------|--------|---------|
| `FrameStorageService` | Persist frames to filesystem, create DB records | event_id, frames[], timestamps[] | List[EventFrame] |
| `AdaptiveSampler` | Select diverse frames using histogram + SSIM | frames[], target_count | List[(index, frame)] |
| `frame_extraction_service.py` | Extract frames from video, apply sampling strategy | video_path, settings | frames[], timestamps[] |
| `event_processor.py` | Orchestrate frame extraction and storage | event | updated event |

### Data Models and Contracts

#### New Model: EventFrame

```python
# backend/app/models/event_frame.py

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime

from app.db.base_class import Base

class EventFrame(Base):
    __tablename__ = "event_frames"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    frame_number = Column(Integer, nullable=False)  # 1-indexed
    frame_path = Column(String, nullable=False)     # Relative path: frames/{event_id}/frame_001.jpg
    timestamp_offset_ms = Column(Integer, nullable=False)  # Offset from event start
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    event = relationship("Event", back_populates="frames")

    __table_args__ = (
        UniqueConstraint('event_id', 'frame_number', name='uq_event_frame_number'),
    )
```

#### Modified Model: Event

```python
# Add to backend/app/models/event.py

# New fields
frame_count = Column(Integer, nullable=True)           # Number of frames analyzed
sampling_strategy = Column(String, nullable=True)     # uniform/adaptive/hybrid

# New relationship
frames = relationship("EventFrame", back_populates="event", cascade="all, delete-orphan")
```

#### New Settings Keys

```python
# System settings schema additions
{
    "analysis_frame_count": 10,           # 5, 10, 15, or 20
    "frame_sampling_strategy": "uniform"  # uniform, adaptive, hybrid
}
```

### APIs and Interfaces

#### GET /api/v1/events/{event_id}/frames

Get all frames for an event.

```
GET /api/v1/events/{event_id}/frames

Response (200):
{
  "event_id": "uuid-string",
  "frame_count": 10,
  "sampling_strategy": "adaptive",
  "frames": [
    {
      "frame_number": 1,
      "url": "/api/v1/events/{event_id}/frames/1",
      "timestamp_offset_ms": 0,
      "width": 1920,
      "height": 1080,
      "file_size_bytes": 48532
    },
    {
      "frame_number": 2,
      "url": "/api/v1/events/{event_id}/frames/2",
      "timestamp_offset_ms": 1200,
      "width": 1920,
      "height": 1080,
      "file_size_bytes": 51024
    }
    // ... more frames
  ]
}

Response (404):
{
  "detail": "Event not found"
}

Response (404 - no frames):
{
  "detail": "No frames stored for this event"
}
```

#### GET /api/v1/events/{event_id}/frames/{frame_number}

Get specific frame image.

```
GET /api/v1/events/{event_id}/frames/{frame_number}

Response (200):
Content-Type: image/jpeg
[Binary JPEG data]

Response (404):
{
  "detail": "Frame 5 not found for event {event_id}"
}
```

#### Updated Settings Endpoints

```
GET /api/v1/system/settings
Response includes:
{
  "analysis_frame_count": 10,
  "frame_sampling_strategy": "uniform",
  // ... other settings
}

PUT /api/v1/system/settings
Request body can include:
{
  "analysis_frame_count": 15,
  "frame_sampling_strategy": "adaptive"
}
```

### Workflows and Sequencing

#### P8-2.1: Frame Storage During Event Processing

```
Event Created
  → event_processor.py receives event
  → Check if video clip available
  → Call frame_extraction_service.extract_frames()
    → Load video with PyAV/OpenCV
    → Apply sampling strategy (uniform/adaptive/hybrid)
    → Return frames[] and timestamps[]
  → Call frame_storage_service.save_frames(event_id, frames, timestamps)
    → Create directory: data/frames/{event_id}/
    → For each frame:
      → Save as frame_{NNN}.jpg (quality 85)
      → Create EventFrame record
    → Return List[EventFrame]
  → Update event.frame_count = len(frames)
  → Update event.sampling_strategy = strategy
  → Continue to AI analysis with frames
```

#### P8-2.2: Frame Gallery Modal Flow

```
User views Event Card
  → Thumbnail displayed (existing)
  → User clicks thumbnail
  → FrameGalleryModal opens
  → Fetch GET /api/v1/events/{id}/frames
  → Display first frame
  → User navigates with arrows/keyboard
  → Frames load lazily as needed
  → User closes modal (X, Escape, click outside)
```

#### P8-2.4: Adaptive Sampling Algorithm

```
Input: raw_frames[], target_count
Output: selected_frames[]

1. Always select first frame (index 0)
2. For each subsequent frame:
   a. Fast histogram comparison vs last selected
   b. If histogram similarity < 0.98:
      - Run SSIM comparison
      - If SSIM < 0.95:
        - Add to selected
   c. Check temporal spacing (min 500ms)
3. If len(selected) < target_count:
   - Fill gaps with uniform sampling
4. Return selected frames with original indices
```

---

## Non-Functional Requirements

### Performance

| Requirement | Target | Measurement |
|-------------|--------|-------------|
| Frame extraction | <2 seconds for 100 candidate frames | Profiling |
| Histogram comparison | <1ms per frame | Benchmark |
| SSIM comparison | <10ms per frame | Benchmark |
| Total adaptive sampling | <500ms for 10 frames from 100 | End-to-end timing |
| Frame gallery load | <500ms first frame, lazy load rest | Frontend timing |
| Frame file size | <100KB per frame (target 50KB) | File size check |

### Security

- Frame files stored with event ownership (no cross-event access)
- Frame API requires same authentication as events API
- No sensitive data in frame filenames
- Frame deletion follows event deletion (cascade)

### Reliability/Availability

- Frame storage failure should not block event processing (log and continue)
- Missing frames should show placeholder in gallery
- Adaptive sampling falls back to uniform if algorithm fails
- Frame cleanup follows retention policy

### Observability

| Metric | Type | Description |
|--------|------|-------------|
| `frames_stored_total` | Counter | Total frames saved |
| `frames_storage_bytes` | Gauge | Total frame storage size |
| `adaptive_sampling_duration_ms` | Histogram | Sampling algorithm time |
| `frame_gallery_opens` | Counter | Gallery modal views |
| `sampling_strategy_used` | Counter (labeled) | Track uniform vs adaptive usage |

---

## Dependencies and Integrations

### Backend Dependencies

```
# requirements.txt - existing (no changes)
opencv-python>=4.12.0      # Frame extraction, histogram, SSIM
numpy>=1.24.0              # Array operations
pyav>=12.0.0               # Video decoding

# Optional addition for better SSIM
scikit-image>=0.22.0       # skimage.metrics.structural_similarity
```

### Frontend Dependencies

```json
// package.json - new dependency
{
  "dependencies": {
    "yet-another-react-lightbox": "^3.17.0"  // Frame gallery
  }
}
```

### File System

```
data/
├── frames/                    # NEW directory
│   └── {event_id}/
│       ├── frame_001.jpg
│       ├── frame_002.jpg
│       └── ...
├── thumbnails/                # Existing
└── videos/                    # Future (P8-3)
```

---

## Acceptance Criteria (Authoritative)

### P8-2.1: Store All Analysis Frames During Event Processing

| AC# | Acceptance Criteria |
|-----|---------------------|
| AC1.1 | Given multi-frame analysis, when frames are extracted, then all frames saved to `data/frames/{event_id}/` |
| AC1.2 | Given frame storage, when frames saved, then EventFrame records created in database |
| AC1.3 | Given frame metadata, when stored, then includes frame_number, path, timestamp_offset_ms |
| AC1.4 | Given event deletion, when cascade occurs, then frame files and records deleted |
| AC1.5 | Given retention policy, when cleanup runs, then old frames deleted with events |

### P8-2.2: Display Analysis Frames Gallery on Event Cards

| AC# | Acceptance Criteria |
|-----|---------------------|
| AC2.1 | Given event with frames, when user clicks thumbnail, then gallery modal opens |
| AC2.2 | Given gallery open, when viewing, then all frames shown in sequence |
| AC2.3 | Given gallery, when navigating, then prev/next arrows work |
| AC2.4 | Given gallery, when viewing, then frame number indicator shows (e.g., "3 of 10") |
| AC2.5 | Given gallery, when viewing, then timestamp offset displayed per frame |
| AC2.6 | Given gallery, when pressing arrow keys, then navigation works |
| AC2.7 | Given gallery, when pressing Escape, then modal closes |
| AC2.8 | Given event without frames, when clicked, then placeholder message shown |

### P8-2.3: Add Configurable Frame Count Setting

| AC# | Acceptance Criteria |
|-----|---------------------|
| AC3.1 | Given Settings > General, when viewing, then "Analysis Frame Count" dropdown visible |
| AC3.2 | Given dropdown, when expanded, then options 5, 10, 15, 20 available |
| AC3.3 | Given value change, when selecting new value, then cost warning modal appears |
| AC3.4 | Given warning modal, when user clicks Cancel, then value reverts |
| AC3.5 | Given warning modal, when user clicks Confirm, then setting saved |
| AC3.6 | Given new setting, when event processed, then configured frame count used |
| AC3.7 | Given setting, when default, then value is 10 |

### P8-2.4: Implement Adaptive Frame Sampling

| AC# | Acceptance Criteria |
|-----|---------------------|
| AC4.1 | Given adaptive mode, when sampling, then histogram comparison used as pre-filter |
| AC4.2 | Given similar frames (histogram >0.98), then SSIM comparison applied |
| AC4.3 | Given frames >95% similar (SSIM), then redundant frame skipped |
| AC4.4 | Given sampling, when complete, then configured frame count respected |
| AC4.5 | Given temporal coverage, when sampling, then minimum 500ms spacing enforced |
| AC4.6 | Given static video, when insufficient diverse frames, then uniform fallback used |
| AC4.7 | Given sampling, when complete, then frame selection logged for debugging |

### P8-2.5: Add Frame Sampling Strategy Selection in Settings

| AC# | Acceptance Criteria |
|-----|---------------------|
| AC5.1 | Given Settings > General, when viewing, then "Frame Sampling Strategy" option visible |
| AC5.2 | Given strategy selector, when expanded, then Uniform, Adaptive, Hybrid options shown |
| AC5.3 | Given each option, when viewed, then description of strategy shown |
| AC5.4 | Given strategy change, when saved, then setting persisted |
| AC5.5 | Given new strategy, when event processed, then selected strategy used |
| AC5.6 | Given default, when not configured, then Uniform used |

---

## Traceability Mapping

| AC | Spec Section | Component(s) | Test Idea |
|----|--------------|--------------|-----------|
| AC1.1-1.3 | Data Models, Workflows | FrameStorageService, EventFrame | Integration test frame save |
| AC1.4-1.5 | Reliability | Event model cascade | Test event deletion cleans frames |
| AC2.1-2.7 | APIs, Workflows | FrameGalleryModal, events.py | Component tests for gallery |
| AC2.8 | APIs | FrameGalleryModal | Test empty state |
| AC3.1-3.2 | APIs | GeneralSettings.tsx | Component test dropdown |
| AC3.3-3.5 | Workflows | CostWarningModal | Component test modal flow |
| AC3.6-3.7 | Services | frame_extraction_service | Integration test setting used |
| AC4.1-4.3 | Workflows | AdaptiveSampler | Unit tests for algorithm |
| AC4.4-4.6 | Workflows | AdaptiveSampler | Edge case tests |
| AC4.7 | Observability | AdaptiveSampler | Verify logging |
| AC5.1-5.6 | APIs | GeneralSettings.tsx, system.py | Component + API tests |

---

## Risks, Assumptions, Open Questions

### Risks

| ID | Risk | Impact | Mitigation |
|----|------|--------|------------|
| R1 | Frame storage increases disk usage significantly | High | Add storage monitoring, aggressive retention |
| R2 | SSIM calculation too slow for real-time | Medium | Use histogram pre-filter, tune thresholds |
| R3 | scikit-image dependency conflicts | Low | Use OpenCV built-in SSIM alternative |
| R4 | Gallery modal performance with many frames | Medium | Lazy loading, limit to 20 max |

### Assumptions

| ID | Assumption |
|----|------------|
| A1 | Frame extraction service already extracts multiple frames |
| A2 | OpenCV 4.12 has adequate histogram and SSIM functions |
| A3 | 50KB average per frame is acceptable quality |
| A4 | Users want to see all frames, not just key frames |

### Open Questions

| ID | Question | Owner | Status |
|----|----------|-------|--------|
| Q1 | Should frames be compressed more aggressively for storage? | Dev | Decide during implementation |
| Q2 | Is 500ms minimum temporal spacing appropriate? | PM | Validate with test footage |
| Q3 | Should adaptive sampling parameters be configurable? | PM | Future enhancement if needed |

---

## Test Strategy Summary

### Test Levels

| Level | Framework | Coverage |
|-------|-----------|----------|
| Unit | pytest | AdaptiveSampler, FrameStorageService |
| Integration | pytest + TestClient | Frame API endpoints |
| Component | React Testing Library | FrameGalleryModal, CostWarningModal |
| E2E | Manual | Full frame storage → gallery flow |

### Key Test Cases

**P8-2.1 (Frame Storage):**
- `test_save_frames_creates_files`
- `test_save_frames_creates_db_records`
- `test_delete_event_deletes_frames`
- `test_retention_cleanup_removes_frames`

**P8-2.2 (Gallery):**
- `test_gallery_opens_on_thumbnail_click`
- `test_gallery_navigation_arrows`
- `test_gallery_keyboard_navigation`
- `test_gallery_empty_state`

**P8-2.3 (Frame Count Setting):**
- `test_frame_count_dropdown_options`
- `test_cost_warning_modal_shows`
- `test_setting_persists_after_save`

**P8-2.4 (Adaptive Sampling):**
- `test_histogram_similar_frames_filtered`
- `test_ssim_similar_frames_filtered`
- `test_temporal_spacing_enforced`
- `test_fallback_to_uniform`
- `test_respects_target_count`

**P8-2.5 (Strategy Selection):**
- `test_strategy_options_displayed`
- `test_strategy_change_persists`
- `test_uniform_strategy_used_by_default`

### Edge Cases

- Zero frames available (single-frame mode)
- All frames identical (static camera)
- Video shorter than expected
- Frame extraction failure mid-process
- Disk full during frame storage
- Concurrent frame gallery access
