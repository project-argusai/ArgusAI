# Epic Technical Specification: Audio Analysis Foundation

Date: 2025-12-16
Author: Brent
Epic ID: P6-3
Status: Draft

---

## Overview

Epic P6-3 lays the groundwork for future audio-based event detection capabilities (backlog item FF-015). This is a foundational epic that establishes the audio capture infrastructure and creates integration points for audio classification models, without implementing full AI-powered audio analysis.

The goal is to enable ArgusAI to extract audio streams from RTSP cameras, detect basic audio events (glass break, gunshot, scream, doorbell), and provide UI configuration for audio features. This positions the system for more advanced audio AI integration in future phases.

## Objectives and Scope

### In Scope
- **Story P6-3.1**: Extract audio stream from RTSP cameras using PyAV/ffmpeg
- **Story P6-3.2**: Create audio event detection pipeline with model integration points
- **Story P6-3.3**: Build camera configuration UI for audio settings

### Out of Scope
- Training custom audio classification models
- Real-time audio streaming to frontend (audio is analyzed, not played)
- Audio recording/storage (analyze and discard)
- USB webcam audio (RTSP only for MVP)
- Integration with existing AI providers for audio (future work)
- Audio transcription for non-doorbell cameras (P3-5 handles doorbell audio)

## System Architecture Alignment

### Components Referenced
- **Backend**: `backend/app/services/camera_service.py` - Extend for audio extraction
- **Backend**: `backend/app/services/audio_service.py` - New service for audio processing
- **Backend**: `backend/app/services/audio_event_detector.py` - New event detection service
- **Backend**: `backend/app/models/camera.py` - Add audio configuration fields
- **Frontend**: `frontend/components/cameras/AudioSettings.tsx` - New component
- **Frontend**: `frontend/app/cameras/[id]/page.tsx` - Integrate audio settings

### Architecture Constraints
- Must not degrade video capture performance when audio is disabled
- Audio processing must be opt-in per camera (default: disabled)
- Must support common RTSP audio codecs (AAC, G.711, Opus)
- Audio buffer size limited to prevent memory issues (max 10 seconds)
- Must integrate with existing alert rule engine for audio events

## Detailed Design

### Services and Modules

| Module | Responsibility | Inputs | Outputs |
|--------|---------------|--------|---------|
| `camera_service.py` | Extract audio alongside video | RTSP URL | Audio frames + video frames |
| `audio_service.py` | Decode and buffer audio | Raw audio stream | PCM audio buffer |
| `audio_event_detector.py` | Classify audio events | PCM audio | Event type + confidence |
| `AudioSettings.tsx` | UI for audio configuration | Camera config | Updated settings |

### Data Models and Contracts

**Camera Model Updates:**
```python
class Camera(Base):
    # ... existing fields ...

    # Audio configuration (new fields)
    audio_enabled: bool = Column(Boolean, default=False)
    audio_event_types: List[str] = Column(JSON, default=list)  # ["glass_break", "gunshot", "scream", "doorbell"]
    audio_confidence_threshold: float = Column(Float, default=0.7)
```

**AudioEvent Schema:**
```python
class AudioEventType(str, Enum):
    GLASS_BREAK = "glass_break"
    GUNSHOT = "gunshot"
    SCREAM = "scream"
    DOORBELL = "doorbell"
    UNKNOWN = "unknown"

class AudioEvent(BaseModel):
    camera_id: str
    timestamp: datetime
    event_type: AudioEventType
    confidence: float
    duration_ms: int
    # Links to visual event if simultaneous
    correlated_event_id: Optional[str] = None
```

**Event Model Update:**
```python
class Event(Base):
    # ... existing fields ...

    # Audio event fields (new)
    audio_event_type: Optional[str] = Column(String, nullable=True)
    audio_confidence: Optional[float] = Column(Float, nullable=True)
```

### APIs and Interfaces

**Updated Camera Endpoints:**

| Endpoint | Change |
|----------|--------|
| `GET /api/v1/cameras/{id}` | Response includes audio_enabled, audio_event_types, audio_confidence_threshold |
| `PUT /api/v1/cameras/{id}` | Accepts audio configuration fields |
| `POST /api/v1/cameras` | Accepts audio configuration fields |

**Request Example (Update Camera):**
```json
{
  "audio_enabled": true,
  "audio_event_types": ["glass_break", "doorbell"],
  "audio_confidence_threshold": 0.8
}
```

**New Internal Interface (Not Exposed via API):**
```python
class AudioEventDetector:
    async def detect(self, audio_buffer: bytes, sample_rate: int) -> Optional[AudioEvent]:
        """Analyze audio buffer and return detected event if any."""
        pass

    def load_model(self, model_path: str) -> None:
        """Load audio classification model."""
        pass
```

### Workflows and Sequencing

**Audio Capture Flow:**
```
RTSP Stream → PyAV demuxer →
  Video packets → Existing video pipeline
  Audio packets → Audio decoder → PCM buffer (10s rolling) →
    Every 2 seconds: AudioEventDetector.detect() →
      If event detected with confidence > threshold:
        Create Event with audio_event_type →
        Trigger alert rules →
        WebSocket broadcast
```

**Audio Settings Update Flow:**
```
User opens camera settings → Loads current config →
  User toggles audio_enabled →
  User selects audio_event_types →
  User adjusts confidence threshold →
  User clicks Save →
    PUT /cameras/{id} →
    camera_service restarts with new config →
    Audio extraction enabled/disabled
```

## Non-Functional Requirements

### Performance

| Metric | Target | Measurement |
|--------|--------|-------------|
| Audio extraction overhead | < 5% CPU per camera | Profiling with/without audio |
| Audio buffer memory | < 2MB per camera | 10s @ 48kHz stereo 16-bit |
| Detection latency | < 500ms | Time from sound to event |
| Video performance impact | 0% when audio disabled | Frame rate comparison |

### Security

| Requirement | Implementation |
|-------------|----------------|
| Audio data privacy | Audio never stored, analyzed in memory only |
| No audio streaming | Audio not sent to frontend or external services |
| Model isolation | Classification model runs locally, no cloud calls |

### Reliability/Availability

| Scenario | Behavior |
|----------|----------|
| RTSP stream has no audio | audio_enabled silently ignored, video continues |
| Unsupported audio codec | Log warning, disable audio for that camera |
| Audio detection model fails | Log error, continue video processing |
| Audio buffer overflow | Drop oldest samples, continue |

### Observability

| Signal | Implementation |
|--------|----------------|
| Audio extraction status | INFO log: camera_id, codec, sample_rate |
| Audio events detected | INFO log: camera_id, event_type, confidence |
| Audio errors | WARNING log: camera_id, error message |

**Prometheus Metrics:**
- `audio_events_detected_total{camera_id, event_type}`
- `audio_extraction_errors_total{camera_id, reason}`
- `audio_buffer_size_bytes{camera_id}`

## Dependencies and Integrations

### Backend Dependencies (New)
| Package | Version | Purpose | Story |
|---------|---------|---------|-------|
| av (PyAV) | ^12.0.0 | Audio/video demuxing | P6-3.1 |
| librosa | ^0.10.0 | Audio feature extraction | P6-3.2 |
| soundfile | ^0.12.0 | Audio file I/O | P6-3.2 |

### Backend Dependencies (Existing)
| Package | Version | Purpose |
|---------|---------|---------|
| opencv-python | 4.8+ | Video capture (already has ffmpeg backend) |
| numpy | ^1.24 | Audio buffer manipulation |

### Frontend Dependencies
No new frontend dependencies required.

### Integration Points
| Integration | Type | Notes |
|-------------|------|-------|
| Alert Rules | Internal | Audio events trigger rules like visual events |
| Event Pipeline | Internal | Audio events stored in same Event table |
| WebSocket | Internal | Audio events broadcast via existing mechanism |
| PyAV/ffmpeg | External | Audio decoding library |

## Acceptance Criteria (Authoritative)

### Story P6-3.1: Audio Stream Extraction
| AC# | Criterion |
|-----|-----------|
| AC1 | Audio stream detected and extracted from RTSP using PyAV |
| AC2 | Supports AAC codec (most common) |
| AC3 | Supports G.711 codec (older cameras) |
| AC4 | Supports Opus codec (modern cameras) |
| AC5 | Audio buffer maintained separate from video (10s rolling buffer) |
| AC6 | Can be enabled/disabled per camera via audio_enabled field |
| AC7 | No impact on video capture frame rate when audio disabled |

### Story P6-3.2: Audio Event Detection Pipeline
| AC# | Criterion |
|-----|-----------|
| AC8 | Audio classification model integration point created |
| AC9 | Supports glass_break event type |
| AC10 | Supports gunshot event type |
| AC11 | Supports scream event type |
| AC12 | Supports doorbell event type |
| AC13 | Confidence threshold configurable per camera |
| AC14 | Events created with audio_event_type field |
| AC15 | Audio events can trigger alert rules |

### Story P6-3.3: Audio Settings UI
| AC# | Criterion |
|-----|-----------|
| AC16 | Toggle to enable/disable audio capture per camera |
| AC17 | Multi-select for audio event types to detect |
| AC18 | Slider for confidence threshold (0.5 - 1.0) |
| AC19 | Audio indicator shown in camera status when enabled |
| AC20 | Settings persist after save and page refresh |

## Traceability Mapping

| AC | Spec Section | Component/API | Test Approach |
|----|--------------|---------------|---------------|
| AC1-AC5 | Workflows | `camera_service.py`, `audio_service.py` | Integration test with RTSP mock |
| AC2-AC4 | NFR | PyAV decoder | Unit test with sample audio files |
| AC6-AC7 | Data Models | `Camera` model | Unit test: enable/disable, measure FPS |
| AC8-AC15 | APIs | `audio_event_detector.py` | Unit test with audio samples |
| AC16-AC20 | Workflows | `AudioSettings.tsx` | E2E test: Playwright |

## Risks, Assumptions, Open Questions

### Risks
| Risk | Impact | Mitigation |
|------|--------|------------|
| **R1**: Audio classification accuracy may be low | High | Start with high confidence threshold (0.8+) |
| **R2**: PyAV may have codec compatibility issues | Medium | Test with multiple camera brands; fallback to ffmpeg CLI |
| **R3**: Audio processing may impact video on low-end hardware | Medium | Make audio opt-in; profile on Raspberry Pi |

### Assumptions
| Assumption | Validation |
|------------|------------|
| **A1**: Most RTSP cameras include audio stream | Verify with target camera models |
| **A2**: Pre-trained audio event models exist (YAMNet, VGGish) | Research open-source models |
| **A3**: 10-second buffer is sufficient for event detection | Based on typical audio event duration |

### Open Questions
| Question | Owner | Status |
|----------|-------|--------|
| **Q1**: Which pre-trained model to use? (YAMNet, VGGish, custom) | Dev Team | Open - recommend YAMNet for size |
| **Q2**: Should audio events create separate Event records or augment visual events? | PM | Recommend: Separate records with correlation |
| **Q3**: Should we support audio-only events (no camera video)? | PM | Deferred - require visual event first |

## Test Strategy Summary

### Test Levels

| Level | Framework | Coverage |
|-------|-----------|----------|
| Unit | pytest | Audio decoder, event detector, model interface |
| Integration | pytest + mock RTSP | End-to-end audio extraction pipeline |
| E2E | Playwright | Audio settings UI |

### Test Cases by Story

**P6-3.1 (Audio Extraction)**
- Extract audio from AAC RTSP stream
- Extract audio from G.711 RTSP stream
- Extract audio from Opus RTSP stream
- Handle RTSP stream with no audio gracefully
- Verify video FPS unchanged when audio disabled
- Verify buffer size stays within limits

**P6-3.2 (Event Detection)**
- Detect glass break sound with > 0.8 confidence
- Detect gunshot sound with > 0.8 confidence
- Detect scream sound with > 0.8 confidence
- Detect doorbell sound with > 0.8 confidence
- No false positive on silence
- No false positive on background noise
- Respect confidence threshold setting
- Create Event record with audio_event_type

**P6-3.3 (Audio Settings UI)**
- Enable audio capture toggle
- Select multiple event types
- Adjust confidence threshold slider
- Settings persist after save
- Audio indicator shows in camera status

### Coverage Targets
- Backend: > 80% line coverage for new audio services
- Frontend: > 70% coverage for AudioSettings component
- E2E: Happy path for all 3 stories
