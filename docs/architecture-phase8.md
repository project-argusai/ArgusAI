# ArgusAI Phase 8 Architecture

## Executive Summary

Phase 8 extends the established ArgusAI architecture with video analysis enhancements, AI improvements, and native Apple app foundations. This document captures incremental architectural decisions that build upon the existing FastAPI + Next.js stack, focusing on frame storage, adaptive sampling, video management, and mobile API design.

## Decision Summary

| Category | Decision | Version | Affects Epics | Rationale |
|----------|----------|---------|---------------|-----------|
| Frame Storage | Filesystem + DB metadata | N/A | P8-2 | Matches existing thumbnail pattern, performant |
| Adaptive Sampling | Hybrid (Histogram + SSIM) | OpenCV 4.12 | P8-2 | Balance of speed and quality |
| Video Storage | Original MP4 from Protect | N/A | P8-3 | No re-encoding overhead |
| Mobile Auth | Device pairing codes | N/A | P8-4 | Secure, user-friendly, no passwords |
| Cloud Relay | Cloudflare Tunnel + Tailscale | Latest | P8-4 | Free tier, easy setup, NAT traversal |
| Apple Apps | SwiftUI native | iOS 17+ | P8-4 | Best native experience, code sharing |

## Existing Architecture (Phases 1-7)

### Core Stack (Unchanged)
- **Backend:** FastAPI 0.115 + SQLAlchemy 2.0 + Alembic
- **Frontend:** Next.js 15 + React 19 + TanStack Query + Tailwind CSS 4 + shadcn/ui
- **AI Providers:** OpenAI → xAI Grok → Claude → Gemini (fallback chain)
- **Video Processing:** OpenCV 4.12 + PyAV 12
- **UniFi Integration:** uiprotect library
- **Database:** SQLite (default) / PostgreSQL

### Existing Patterns (Continue to Follow)
- Service layer pattern in `backend/app/services/`
- API routes prefixed with `/api/v1/`
- React hooks in `frontend/hooks/`
- shadcn/ui components in `frontend/components/ui/`
- Fernet encryption for sensitive data
- Structured JSON logging

---

## Phase 8 Project Structure Additions

```
backend/
├── app/
│   ├── api/v1/
│   │   ├── mobile/                    # NEW: Mobile API module
│   │   │   ├── __init__.py
│   │   │   ├── auth.py                # Device pairing endpoints
│   │   │   ├── events.py              # Mobile-optimized event queries
│   │   │   └── push.py                # APNS token registration
│   │   └── events.py                  # MODIFIED: Add /frames endpoint
│   ├── models/
│   │   ├── __init__.py                # MODIFIED: Export EventFrame
│   │   └── event_frame.py             # NEW: EventFrame model
│   ├── services/
│   │   ├── adaptive_sampler.py        # NEW: Adaptive frame sampling
│   │   ├── frame_storage_service.py   # NEW: Frame persistence
│   │   └── video_storage_service.py   # NEW: Video download/storage
│   └── schemas/
│       ├── event_frame.py             # NEW: Frame request/response schemas
│       └── mobile.py                  # NEW: Mobile API schemas
├── alembic/versions/
│   └── xxxx_add_event_frames.py       # NEW: EventFrame table migration

frontend/
├── components/
│   ├── events/
│   │   ├── EventCard.tsx              # MODIFIED: Clickable thumbnail
│   │   └── FrameGalleryModal.tsx      # NEW: Frame gallery lightbox
│   ├── settings/
│   │   ├── GeneralSettings.tsx        # MODIFIED: Frame count setting
│   │   ├── CostWarningModal.tsx       # NEW: Cost warning dialog
│   │   └── MQTTSettings.tsx           # MODIFIED: Conditional visibility
│   └── video/
│       └── VideoPlayerModal.tsx       # NEW: Video player with download
├── lib/
│   └── api-client.ts                  # MODIFIED: Add frame/video endpoints

data/
├── frames/                            # NEW: Analysis frame storage
│   └── {event_id}/
│       ├── frame_001.jpg
│       ├── frame_002.jpg
│       └── ...
├── videos/                            # NEW: Motion video storage
│   └── {event_id}.mp4
└── thumbnails/                        # EXISTING: Event thumbnails

docs/
├── research/
│   └── apple-apps-technology.md       # NEW: P8-4.1 research output
└── architecture/
    └── cloud-relay-design.md          # NEW: P8-4.2 design output
```

---

## Epic to Architecture Mapping

| Epic | Stories | Primary Components | New Services |
|------|---------|-------------------|--------------|
| P8-1 Bug Fixes | 1.1, 1.2, 1.3 | events.py, install.sh, push service | None |
| P8-2 Video Analysis | 2.1-2.5 | frame_extraction_service, events API | AdaptiveSampler, FrameStorageService |
| P8-3 AI & Settings | 3.1-3.3 | settings components, ai_service | VideoStorageService |
| P8-4 Apple Apps | 4.1-4.4 | mobile/ API module | MobileAuthService |

---

## Technology Stack Details

### New Dependencies (Phase 8)

**Backend (requirements.txt additions):**
```
# Adaptive sampling (already have OpenCV)
scikit-image>=0.22.0        # For SSIM calculation

# Mobile push (iOS)
PyAPNs2>=0.8.0              # Apple Push Notification service
```

**Frontend (package.json additions):**
```json
{
  "dependencies": {
    "yet-another-react-lightbox": "^3.17.0"  // Frame gallery
  }
}
```

**iOS App (new project):**
```
- Xcode 15+
- iOS Deployment Target: 17.0
- SwiftUI
- Swift 5.9+
```

---

## Data Architecture

### New Model: EventFrame

```python
class EventFrame(Base):
    __tablename__ = "event_frames"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID, ForeignKey("events.id"), nullable=False, index=True)
    frame_number = Column(Integer, nullable=False)  # 1-indexed
    frame_path = Column(String, nullable=False)     # Relative path
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

### Modified Model: Event

```python
class Event(Base):
    # Existing fields...

    # NEW fields for Phase 8
    video_path = Column(String, nullable=True)      # Path to motion video
    frame_count = Column(Integer, nullable=True)    # Number of frames analyzed
    sampling_strategy = Column(String, nullable=True)  # uniform/adaptive/hybrid

    # Relationships
    frames = relationship("EventFrame", back_populates="event", cascade="all, delete-orphan")
```

### New Settings Keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `analysis_frame_count` | int | 10 | Number of frames to extract (5/10/15/20) |
| `frame_sampling_strategy` | str | "uniform" | uniform/adaptive/hybrid |
| `store_motion_videos` | bool | false | Download and store full videos |
| `video_retention_days` | int | 30 | Days to keep videos (separate from events) |

---

## API Contracts

### New Endpoints

#### GET /api/v1/events/{event_id}/frames
Get all frames for an event.

**Response:**
```json
{
  "event_id": "uuid",
  "frame_count": 10,
  "sampling_strategy": "adaptive",
  "frames": [
    {
      "frame_number": 1,
      "url": "/api/v1/events/{event_id}/frames/1",
      "timestamp_offset_ms": 0,
      "width": 1920,
      "height": 1080
    }
  ]
}
```

#### GET /api/v1/events/{event_id}/frames/{frame_number}
Get specific frame image (returns JPEG).

#### GET /api/v1/events/{event_id}/video
Get motion video (returns MP4 stream or download).

#### POST /api/v1/ai/refine-prompt
Refine AI prompt using feedback data.

**Request:**
```json
{
  "current_prompt": "string",
  "include_feedback": true,
  "max_feedback_samples": 50
}
```

**Response:**
```json
{
  "suggested_prompt": "string",
  "changes_summary": "string",
  "feedback_analyzed": 50
}
```

### Mobile API Endpoints

#### POST /api/v1/mobile/auth/pair
Generate device pairing code.

**Response:**
```json
{
  "pairing_code": "123456",
  "expires_at": "2025-12-20T12:05:00Z",
  "expires_in_seconds": 300
}
```

#### POST /api/v1/mobile/auth/verify
Verify pairing code and get tokens.

**Request:**
```json
{
  "pairing_code": "123456",
  "device_name": "iPhone 15 Pro",
  "device_id": "unique-device-identifier"
}
```

**Response:**
```json
{
  "access_token": "jwt...",
  "refresh_token": "jwt...",
  "expires_in": 3600
}
```

#### POST /api/v1/mobile/push/register
Register APNS token for push notifications.

**Request:**
```json
{
  "apns_token": "device-token-from-ios",
  "device_id": "unique-device-identifier"
}
```

---

## Implementation Patterns

### Frame Storage Pattern

```python
# Service: frame_storage_service.py

class FrameStorageService:
    def __init__(self, base_path: str = "data/frames"):
        self.base_path = Path(base_path)

    def save_frames(self, event_id: UUID, frames: List[np.ndarray],
                    timestamps: List[int]) -> List[EventFrame]:
        """Save frames to filesystem and create DB records."""
        event_dir = self.base_path / str(event_id)
        event_dir.mkdir(parents=True, exist_ok=True)

        saved_frames = []
        for i, (frame, ts) in enumerate(zip(frames, timestamps), 1):
            filename = f"frame_{i:03d}.jpg"
            filepath = event_dir / filename
            cv2.imwrite(str(filepath), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

            saved_frames.append(EventFrame(
                event_id=event_id,
                frame_number=i,
                frame_path=str(filepath.relative_to(self.base_path.parent)),
                timestamp_offset_ms=ts
            ))

        return saved_frames

    def delete_frames(self, event_id: UUID) -> None:
        """Delete all frames for an event."""
        event_dir = self.base_path / str(event_id)
        if event_dir.exists():
            shutil.rmtree(event_dir)
```

### Adaptive Sampling Pattern

```python
# Service: adaptive_sampler.py

class AdaptiveSampler:
    def __init__(self, similarity_threshold: float = 0.95):
        self.similarity_threshold = similarity_threshold

    def select_frames(self, frames: List[np.ndarray],
                      target_count: int) -> List[Tuple[int, np.ndarray]]:
        """Select diverse frames using hybrid approach."""
        if len(frames) <= target_count:
            return list(enumerate(frames))

        selected = [(0, frames[0])]  # Always include first frame

        for i, frame in enumerate(frames[1:], 1):
            # Fast histogram check
            if not self._histogram_similar(selected[-1][1], frame):
                # Detailed SSIM check
                if not self._ssim_similar(selected[-1][1], frame):
                    selected.append((i, frame))

                    if len(selected) >= target_count:
                        break

        # If we didn't get enough, fill with uniform sampling
        if len(selected) < target_count:
            selected = self._fill_uniform(frames, selected, target_count)

        return selected

    def _histogram_similar(self, frame1, frame2) -> bool:
        """Fast histogram comparison."""
        hist1 = cv2.calcHist([frame1], [0], None, [256], [0, 256])
        hist2 = cv2.calcHist([frame2], [0], None, [256], [0, 256])
        return cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL) > 0.98

    def _ssim_similar(self, frame1, frame2) -> bool:
        """Detailed SSIM comparison."""
        gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
        score = ssim(gray1, gray2)
        return score > self.similarity_threshold
```

### Mobile Auth Pattern

```python
# Service: mobile_auth_service.py

class MobileAuthService:
    PAIRING_CODE_LENGTH = 6
    PAIRING_CODE_EXPIRY = 300  # 5 minutes

    def __init__(self, redis_client=None):
        self.pending_codes = {}  # In production, use Redis

    def generate_pairing_code(self) -> Tuple[str, datetime]:
        """Generate a 6-digit pairing code."""
        code = ''.join(random.choices('0123456789', k=self.PAIRING_CODE_LENGTH))
        expires_at = datetime.utcnow() + timedelta(seconds=self.PAIRING_CODE_EXPIRY)

        self.pending_codes[code] = {
            'created_at': datetime.utcnow(),
            'expires_at': expires_at
        }

        return code, expires_at

    def verify_pairing_code(self, code: str, device_name: str,
                            device_id: str) -> Optional[Dict]:
        """Verify code and return tokens if valid."""
        if code not in self.pending_codes:
            return None

        code_data = self.pending_codes[code]
        if datetime.utcnow() > code_data['expires_at']:
            del self.pending_codes[code]
            return None

        # Generate tokens
        access_token = self._create_access_token(device_id)
        refresh_token = self._create_refresh_token(device_id)

        # Clean up used code
        del self.pending_codes[code]

        return {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_in': 3600
        }
```

---

## Consistency Rules

### Naming Conventions (Phase 8 Additions)

| Item | Convention | Example |
|------|------------|---------|
| Frame files | `frame_{NNN}.jpg` | `frame_001.jpg` |
| Video files | `{event_id}.mp4` | `abc123.mp4` |
| Frame directories | `{event_id}/` | `abc123-def456/` |
| Mobile endpoints | `/api/v1/mobile/{resource}` | `/api/v1/mobile/auth/pair` |
| Settings keys | `snake_case` | `analysis_frame_count` |
| iOS files | `PascalCase.swift` | `EventListView.swift` |

### Error Handling (Phase 8)

| Error Type | HTTP Status | Response Format |
|------------|-------------|-----------------|
| Frame not found | 404 | `{"detail": "Frame 5 not found for event {id}"}` |
| Video not stored | 404 | `{"detail": "Video not available for this event"}` |
| Pairing code expired | 400 | `{"detail": "Pairing code expired"}` |
| Pairing code invalid | 400 | `{"detail": "Invalid pairing code"}` |
| Sampling failed | 500 | `{"detail": "Frame extraction failed: {reason}"}` |

### File Size Limits

| Content | Max Size | Notes |
|---------|----------|-------|
| Frame JPEG | 500KB | Quality 85, resize if needed |
| Video MP4 | 100MB | Protect clips typically 5-30MB |
| Thumbnail | 200KB | Existing limit |

---

## Security Architecture

### Mobile Authentication Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Web UI    │     │   Backend   │     │   iOS App   │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       │ Generate Code     │                   │
       │──────────────────>│                   │
       │    "123456"       │                   │
       │<──────────────────│                   │
       │                   │                   │
       │     Display       │                   │
       │    to User        │    Enter Code     │
       │                   │<──────────────────│
       │                   │  Verify + Tokens  │
       │                   │──────────────────>│
       │                   │                   │
       │                   │  Subsequent calls │
       │                   │  with JWT Bearer  │
       │                   │<──────────────────│
```

### Token Security
- Access tokens: JWT, 1 hour expiry
- Refresh tokens: JWT, 30 day expiry, rotated on use
- Stored in iOS Keychain (encrypted)
- Device ID bound to tokens

### Cloud Relay Security
- Cloudflare Tunnel: Zero-trust, no open ports
- All traffic encrypted (TLS 1.3)
- Rate limiting at tunnel level
- Optional Tailscale: WireGuard encryption

---

## Performance Considerations

### Frame Storage
- JPEG quality 85 = ~50KB per frame
- 10 frames per event = ~500KB
- 100 events/day = ~50MB/day frame storage
- Cleanup via retention policy

### Adaptive Sampling
- Histogram comparison: <1ms per frame
- SSIM comparison: ~10ms per frame
- Target: <500ms total for 10-frame selection from 100 candidates

### Video Storage
- Protect clips: typically 5-30MB
- 10 videos/day = 50-300MB/day
- Stream on demand, don't preload

### Mobile API
- Compressed thumbnails for lists (max 50KB)
- Pagination: 20 events per page
- WebSocket for real-time updates (optional)

---

## Deployment Architecture

### Phase 8 Changes
No changes to deployment architecture. New features deploy with existing:
- Backend: uvicorn + systemd
- Frontend: Next.js + systemd
- Data: Local filesystem (frames/, videos/)

### Storage Considerations
- Monitor disk usage for frames/videos
- Add warning when >80% disk used
- Implement aggressive cleanup for videos (separate retention)

---

## Development Environment

### Prerequisites (Phase 8 Additions)

**For iOS Development:**
- macOS 14+ (Sonoma)
- Xcode 15+
- Apple Developer Account (for device testing)
- iOS 17+ device or simulator

**Backend:**
```bash
# Additional dependency
pip install scikit-image PyAPNs2
```

### Setup Commands

```bash
# Backend (existing + new migration)
cd backend
source venv/bin/activate
alembic upgrade head  # Applies event_frames migration

# Frontend (no changes)
cd frontend
npm install

# iOS App (new)
cd ios-app
open ArgusAI.xcodeproj
# Build and run in Xcode
```

---

## Architecture Decision Records (ADRs)

### ADR-P8-001: Frame Storage in Filesystem

**Context:** Need to store frames used for AI analysis for user review.

**Decision:** Store frames as JPEG files in `data/frames/{event_id}/` with metadata in database.

**Rationale:**
- Matches existing thumbnail storage pattern
- Filesystem efficient for binary data
- Easy cleanup with directory deletion
- No database bloat

**Consequences:**
- Two sources of truth (files + DB)
- Need to handle orphaned files in cleanup

---

### ADR-P8-002: Hybrid Adaptive Sampling

**Context:** Need content-aware frame selection to reduce redundant frames.

**Decision:** Use histogram comparison as fast pre-filter, SSIM for accuracy.

**Rationale:**
- Histogram: <1ms, catches obvious duplicates
- SSIM: ~10ms, accurate similarity measure
- Combined: Good balance of speed and quality

**Consequences:**
- More complex than uniform sampling
- Need to tune thresholds for different camera types

---

### ADR-P8-003: Device Pairing for Mobile Auth

**Context:** Need secure authentication for mobile apps without complex setup.

**Decision:** Use 6-digit pairing codes with 5-minute expiry.

**Rationale:**
- User-friendly (similar to Apple TV pairing)
- Secure (short window, single use)
- No password entry on mobile device
- Device binding via unique ID

**Consequences:**
- Requires web UI access to generate code
- Code must be entered quickly

---

### ADR-P8-004: SwiftUI for Apple Apps

**Context:** Need native apps for iPhone, iPad, Watch, TV, macOS.

**Decision:** Use SwiftUI as the UI framework.

**Rationale:**
- Best native experience
- Code sharing across Apple platforms
- Modern, declarative approach
- No Android requirement

**Consequences:**
- Requires macOS for development
- iOS 17+ minimum (SwiftUI features)
- Cannot share code with web/Android

---

### ADR-P8-005: Cloudflare Tunnel for Remote Access

**Context:** Need mobile apps to connect to local ArgusAI without port forwarding.

**Decision:** Use Cloudflare Tunnel as primary, Tailscale as advanced option.

**Rationale:**
- Cloudflare: Free tier, easy setup, no ports
- Tailscale: For power users wanting VPN
- Both: Zero-trust, encrypted

**Consequences:**
- Dependency on external services
- Need fallback for local network access

---

_Generated by BMAD Decision Architecture Workflow v1.0_
_Date: 2025-12-20_
_For: Brent_
