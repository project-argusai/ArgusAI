# live-object-ai-classifier - Epic Breakdown

**Author:** Brent
**Date:** 2025-11-16
**Project Level:** MVP
**Target Scale:** Beta testing (10-20 users)

---

## Overview

This document provides the complete epic and story breakdown for live-object-ai-classifier, decomposing the requirements from the [PRD](./prd.md) into implementable stories.

**Living Document Notice:** This is the initial version. It will be updated after UX Design and Architecture workflows add interaction and technical details to stories.

### Epic Summary

**6 Epics organized by technical architecture layers and value delivery:**

1. **Foundation & Infrastructure Setup** - Technical foundation (Week 1)
2. **Camera Integration & Motion Detection** - Input layer (Weeks 2-3)
3. **AI Intelligence & Event Processing** - Intelligence layer (Weeks 2-3)
4. **Dashboard & Event Visualization** - Presentation layer (Weeks 3-4)
5. **Alert & Automation System** - Action layer (Week 5)
6. **Production Readiness & Security** - Operational layer (Weeks 6-10)

---

## Functional Requirements Inventory

**F1: Camera Feed Integration**
- F1.1: RTSP Camera Support - Connect to RTSP camera streams with authentication
- F1.2: Camera Configuration UI - Dashboard interface for camera setup
- F1.3: Webcam/USB Camera Support - Support local USB cameras for testing

**F2: Motion Detection**
- F2.1: Motion Detection Algorithm - Detect motion to trigger AI processing
- F2.2: Motion Detection Zones - User-defined active detection zones
- F2.3: Detection Schedule - Time-based scheduling for motion detection

**F3: AI-Powered Description Generation**
- F3.1: Natural Language Processing - Generate rich natural language descriptions
- F3.2: Image Capture & Processing - Capture optimal frame for AI analysis
- F3.3: AI Model Selection & Fallback - Support multiple AI model options
- F3.4: Description Enhancement Prompt - AI prompt optimized for security/accessibility

**F4: Event Storage & Management**
- F4.1: Event Data Structure - Store semantic event records (not video)
- F4.2: Event Retrieval API - Backend API for querying events
- F4.3: Data Retention Policy - User-configurable event storage duration
- F4.4: Event Search - Search events by description keywords

**F5: Alert Rule Engine**
- F5.1: Basic Alert Rules - User-defined conditions for alerts
- F5.2: Alert Rule Configuration UI - Dashboard interface for managing rules
- F5.3: Advanced Rule Logic - Complex rule conditions with AND/OR logic
- F5.4: Alert Cooldown - Prevent alert spam from repeated events

**F6: Dashboard & User Interface**
- F6.1: Event Timeline View - Display events in chronological order
- F6.2: Live Camera View - Preview camera feeds in dashboard
- F6.3: System Settings Page - Central configuration for all settings
- F6.4: Manual Analysis Trigger - User can manually analyze current frame
- F6.5: Dashboard Statistics - Overview of system activity and performance
- F6.6: Notification Center - In-dashboard notifications for new events

**F7: Authentication & Security**
- F7.1: User Authentication - Secure login to protect system access
- F7.2: API Key Management - Secure storage of AI model API keys
- F7.3: HTTPS/TLS Support - All communication encrypted in production
- F7.4: Rate Limiting - Protect API endpoints from abuse

**F8: System Administration**
- F8.1: Health Check Endpoint - Monitor system health programmatically
- F8.2: Logging & Debugging - Comprehensive logging for troubleshooting
- F8.3: Backup & Restore - Backup event data and configuration

**F9: Webhook Integration**
- F9.1: Webhook Configuration - Send event data to external URLs
- F9.2: Webhook Testing - Test webhooks before deploying
- F9.3: Webhook Logs - Track webhook delivery history

---

## FR Coverage Map

**Epic 1 (Foundation):** Covers infrastructure needs for ALL FRs
- No specific FRs, but enables: F1-F9

**Epic 2 (Camera Integration):** F1.1, F1.2, F1.3, F2.1, F2.2, F2.3
- F1.1: RTSP Camera Support (MUST HAVE)
- F1.2: Camera Configuration UI (MUST HAVE)
- F1.3: Webcam/USB Camera Support (SHOULD HAVE)
- F2.1: Motion Detection Algorithm (MUST HAVE)
- F2.2: Motion Detection Zones (SHOULD HAVE)
- F2.3: Detection Schedule (COULD HAVE)

**Epic 3 (AI Intelligence):** F3.1, F3.2, F3.3, F3.4, F4.1, F4.2, F4.3, F4.4
- F3.1: Natural Language Processing (MUST HAVE)
- F3.2: Image Capture & Processing (MUST HAVE)
- F3.3: AI Model Selection & Fallback (SHOULD HAVE)
- F3.4: Description Enhancement Prompt (MUST HAVE)
- F4.1: Event Data Structure (MUST HAVE)
- F4.2: Event Retrieval API (MUST HAVE)
- F4.3: Data Retention Policy (SHOULD HAVE)
- F4.4: Event Search (SHOULD HAVE)

**Epic 4 (Dashboard):** F6.1, F6.2, F6.3, F6.4, F6.5, F6.6
- F6.1: Event Timeline View (MUST HAVE)
- F6.2: Live Camera View (MUST HAVE)
- F6.3: System Settings Page (MUST HAVE)
- F6.4: Manual Analysis Trigger (SHOULD HAVE)
- F6.5: Dashboard Statistics (COULD HAVE)
- F6.6: Notification Center (SHOULD HAVE)

**Epic 5 (Alerts & Automation):** F5.1, F5.2, F5.3, F5.4, F9.1, F9.2, F9.3
- F5.1: Basic Alert Rules (MUST HAVE)
- F5.2: Alert Rule Configuration UI (MUST HAVE)
- F5.3: Advanced Rule Logic (COULD HAVE)
- F5.4: Alert Cooldown (SHOULD HAVE)
- F9.1: Webhook Configuration (SHOULD HAVE)
- F9.2: Webhook Testing (SHOULD HAVE)
- F9.3: Webhook Logs (COULD HAVE)

**Epic 6 (Production Readiness):** F7.1, F7.2, F7.3, F7.4, F8.1, F8.2, F8.3
- F7.1: User Authentication (MUST HAVE - Phase 1.5)
- F7.2: API Key Management (MUST HAVE)
- F7.3: HTTPS/TLS Support (SHOULD HAVE - Phase 1.5)
- F7.4: Rate Limiting (COULD HAVE)
- F8.1: Health Check Endpoint (SHOULD HAVE)
- F8.2: Logging & Debugging (SHOULD HAVE)
- F8.3: Backup & Restore (COULD HAVE)

---

## Epic 1: Foundation & Infrastructure Setup

**Goal:** Establish the technical foundation enabling all subsequent development. Set up repository structure, build systems, database schema, core dependencies, and deployment pipeline basics that all future stories will build upon.

---

### Story 1.1: Initialize Project Repository and Development Environment

**As a** developer,
**I want** a fully configured project repository with backend and frontend scaffolding,
**So that** I can begin feature development with proper tooling and structure in place.

**Acceptance Criteria:**

**Given** I am setting up a new greenfield project
**When** I clone the repository and run the setup script
**Then** I have a working development environment with all dependencies installed

**And** the project structure follows best practices:
- `/backend` - Python FastAPI project with proper package structure
- `/frontend` - Next.js 14+ project with TypeScript and App Router
- `/docs` - Documentation and architecture diagrams
- `/scripts` - Deployment and utility scripts
- Root-level: `.gitignore`, `README.md`, `docker-compose.yml`, `.env.example`

**And** Python backend includes:
- Virtual environment created (`.venv`)
- `requirements.txt` with pinned versions: FastAPI 0.104+, uvicorn 0.24+, SQLAlchemy 2.0+, opencv-python 4.8+, Pillow 10.0+, python-dotenv 1.0+, pydantic 2.5+, httpx 0.25+
- `pyproject.toml` for project metadata
- Black formatter configured (line length 100)
- Ruff linter configured
- pytest test framework setup with `tests/` directory
- Pre-commit hooks for code quality

**And** Next.js frontend includes:
- TypeScript 5+ with strict mode enabled
- Tailwind CSS 3.4+ configured with custom theme
- ESLint and Prettier configured
- `package.json` with dependencies: React 18+, TanStack Query 5.0+, axios 1.6+, Headless UI 1.7+, Heroicons 2.0+, date-fns 3.0+, zod 3.22+
- `/app` directory structure for App Router
- `/components` directory for reusable components
- Environment variable setup (`.env.local.example`)

**And** Docker configuration includes:
- Multi-stage Dockerfile for backend (Python 3.11+)
- Dockerfile for frontend (Node 20+)
- `docker-compose.yml` for local development with services: backend, frontend, database
- Volume mounts for hot-reloading during development
- Health checks configured for all services

**And** repository includes:
- `.gitignore` ignoring: `__pycache__`, `.venv`, `node_modules`, `.env`, `.DS_Store`, `*.pyc`, `.next`, `build/`
- `README.md` with: project description, setup instructions, tech stack, architecture overview
- GitHub Actions workflow placeholder for CI/CD
- License file (if applicable)

**Prerequisites:** None (first story)

**Technical Notes:**
- Use Python 3.11+ for pattern matching and performance improvements
- Node 20+ LTS for frontend stability
- Git repository initialized with `main` as default branch
- Consider using `uv` or `poetry` for Python dependency management (faster than pip)
- Set up `.nvmrc` for Node version consistency across team

---

### Story 1.2: Design and Implement Database Schema

**As a** backend developer,
**I want** a complete database schema with all tables, indexes, and relationships defined,
**So that** I can store cameras, events, alert rules, and system data reliably.

**Acceptance Criteria:**

**Given** I have the project foundation set up
**When** I run the database initialization script
**Then** SQLite database is created at `/backend/data/app.db` with all tables

**And** the `cameras` table is created with:
- `id` (TEXT PRIMARY KEY) - UUID format
- `name` (TEXT NOT NULL) - max 100 chars
- `rtsp_url` (TEXT) - nullable for USB cameras
- `camera_type` (TEXT NOT NULL) - 'rtsp' or 'usb', default 'rtsp'
- `username` (TEXT) - nullable
- `password` (TEXT) - nullable, will be encrypted
- `enabled` (BOOLEAN NOT NULL) - default TRUE
- `created_at` (TIMESTAMP NOT NULL) - ISO 8601 format
- `updated_at` (TIMESTAMP NOT NULL) - ISO 8601 format, auto-updated
- Index on `enabled` for fast filtering
- Unique constraint on `name`

**And** the `events` table is created with:
- `id` (TEXT PRIMARY KEY) - UUID format
- `camera_id` (TEXT NOT NULL) - foreign key to cameras.id with CASCADE delete
- `timestamp` (TIMESTAMP NOT NULL) - ISO 8601, indexed for range queries
- `description` (TEXT NOT NULL) - AI-generated description, no length limit
- `confidence` (INTEGER NOT NULL) - 0-100, check constraint
- `objects_detected` (TEXT NOT NULL) - JSON array: ["person", "vehicle", "animal", "package", "unknown"]
- `thumbnail_path` (TEXT) - relative path to image file
- `thumbnail_base64` (TEXT) - alternative to file storage (base64-encoded)
- `alert_triggered` (BOOLEAN NOT NULL) - default FALSE
- `user_feedback` (TEXT) - nullable, for learning system
- `created_at` (TIMESTAMP NOT NULL) - ISO 8601 format
- Index on `timestamp DESC` for timeline queries
- Index on `camera_id` for filtering
- Composite index on (`timestamp`, `camera_id`) for common queries
- Full-text search index on `description` (SQLite FTS5)

**And** the `alert_rules` table is created with:
- `id` (TEXT PRIMARY KEY) - UUID format
- `name` (TEXT NOT NULL) - max 100 chars, unique
- `enabled` (BOOLEAN NOT NULL) - default TRUE
- `conditions` (TEXT NOT NULL) - JSON object with rule logic
- `actions` (TEXT NOT NULL) - JSON array of actions to perform
- `cooldown_minutes` (INTEGER NOT NULL) - 0-1440, default 5
- `last_triggered` (TIMESTAMP) - nullable, tracks cooldown
- `created_at` (TIMESTAMP NOT NULL)
- `updated_at` (TIMESTAMP NOT NULL)
- Index on `enabled` for active rule queries

**And** the `webhook_logs` table is created with:
- `id` (TEXT PRIMARY KEY) - UUID format
- `event_id` (TEXT NOT NULL) - foreign key to events.id with CASCADE delete
- `url` (TEXT NOT NULL)
- `status_code` (INTEGER) - HTTP status code
- `response_time_ms` (INTEGER) - latency metric
- `retry_count` (INTEGER NOT NULL) - default 0, max 3
- `error_message` (TEXT) - nullable
- `created_at` (TIMESTAMP NOT NULL)
- Index on `event_id` for event lookups
- Index on `created_at` for log retention cleanup

**And** the `system_settings` table is created with:
- `key` (TEXT PRIMARY KEY) - setting name
- `value` (TEXT NOT NULL) - JSON-encoded value
- `updated_at` (TIMESTAMP NOT NULL)
- Pre-populated with defaults: data_retention_days=30, ai_model='gpt-4o-mini', motion_sensitivity='medium'

**And** database migrations are managed with:
- Alembic 1.12+ configured with `alembic.ini`
- Initial migration script in `alembic/versions/001_initial_schema.py`
- Migration command: `alembic upgrade head`
- Rollback capability: `alembic downgrade -1`

**And** database performance is optimized:
- SQLite configured with `PRAGMA journal_mode=WAL` for concurrent reads
- `PRAGMA foreign_keys=ON` for referential integrity
- `PRAGMA synchronous=NORMAL` for performance
- Connection pool with max 10 connections

**Prerequisites:** Story 1.1 (project structure)

**Technical Notes:**
- Use SQLAlchemy 2.0 ORM with async support
- Create `models.py` with declarative base models for all tables
- Add `created_at` and `updated_at` timestamps automatically using SQLAlchemy events
- Consider using UUIDs (uuid4) for all primary keys for distributed scalability
- Thumbnail storage decision: Start with `thumbnail_path` for files, add `thumbnail_base64` option later
- Maximum event storage estimation: ~10KB per event (description + metadata), 10MB per 1000 events
- FTS5 full-text search provides <100ms search performance for 10K+ events

---

### Story 1.3: Set Up Core Backend API Structure and Health Endpoint

**As a** system administrator,
**I want** a running FastAPI backend with proper structure and health monitoring,
**So that** I can verify the system is operational and ready for feature development.

**Acceptance Criteria:**

**Given** I have the database schema implemented
**When** I start the backend server with `uvicorn main:app --reload`
**Then** the server starts on `http://localhost:8000` within 2 seconds

**And** the API follows this structure:
- `/backend/app/main.py` - FastAPI application initialization
- `/backend/app/api/` - API route modules
- `/backend/app/core/` - Core utilities (config, database, security)
- `/backend/app/models/` - SQLAlchemy models
- `/backend/app/schemas/` - Pydantic request/response schemas
- `/backend/app/services/` - Business logic layer
- `/backend/app/utils/` - Utility functions

**And** FastAPI application includes:
- CORS middleware configured for development (allow `http://localhost:3000`)
- Request ID middleware for tracing
- Logging middleware with structured JSON logs
- Global exception handler returning consistent error format
- API versioning prefix: `/api/v1`
- OpenAPI documentation available at `/docs` (Swagger UI)
- ReDoc documentation at `/redoc`

**And** `GET /api/v1/health` endpoint returns:
```json
{
  "status": "healthy",
  "timestamp": "2025-11-16T10:30:00Z",
  "version": "0.1.0",
  "services": {
    "database": "connected",
    "storage": "available"
  },
  "uptime_seconds": 3600
}
```

**And** health check validates:
- Database connectivity (SELECT 1 query completes)
- Storage directory writable (test file create/delete)
- Response time < 500ms
- Returns 503 status if any service degraded

**And** environment configuration includes:
- `.env` file with variables: `DATABASE_URL`, `LOG_LEVEL`, `CORS_ORIGINS`, `API_VERSION`
- Config loader in `/backend/app/core/config.py` using Pydantic BaseSettings
- Validation of required environment variables on startup
- Defaults for development: `LOG_LEVEL=INFO`, `DATABASE_URL=sqlite:///./data/app.db`

**And** logging is configured:
- Python `logging` module with JSON formatter
- Log levels: DEBUG (development), INFO (production)
- Log format includes: timestamp, level, message, request_id, module
- Logs written to: stdout (for Docker) and `/backend/logs/app.log` (rotated daily)
- Separate error log: `/backend/logs/error.log`

**And** error handling provides:
- HTTP 500 errors return: `{"detail": "Internal server error", "request_id": "..."}`
- Validation errors (422) return Pydantic error details
- Custom exception classes: `DatabaseError`, `ExternalServiceError`, `ConfigurationError`
- Sentry integration placeholder for error tracking (optional)

**And** the server includes:
- Graceful shutdown handling (cleanup database connections)
- Startup event logs application version and configuration
- Signal handlers for SIGTERM and SIGINT

**Prerequisites:** Story 1.2 (database schema)

**Technical Notes:**
- Use `uvicorn` with `--reload` for development, `--workers 4` for production
- Configure `lifespan` context manager for startup/shutdown events
- Add `app.state` for shared resources (database engine, etc.)
- Response time monitoring with middleware tracking p50, p95, p99 latency
- Consider using `gunicorn` with uvicorn workers for production deployment
- Health endpoint should not require authentication
- Add `/api/v1/version` endpoint returning build info and commit hash

---

## Epic 2: Camera Integration & Motion Detection

**Goal:** Enable system to connect to cameras and detect when interesting events occur. Provide the "input layer" that captures visual data and intelligently triggers AI processing only when needed.

---

### Story 2.1: Implement RTSP Camera Connection and Frame Capture

**As a** backend developer,
**I want** to connect to RTSP camera streams and continuously capture frames,
**So that** I can process video feeds for motion detection and event analysis.

**Acceptance Criteria:**

**Given** I have a camera with RTSP stream available
**When** I configure the camera connection with RTSP URL and credentials
**Then** the system successfully connects and begins capturing frames

**And** RTSP connection supports:
- Protocol: RTSP over TCP (primary) and UDP (fallback)
- Authentication: Basic auth and Digest auth
- URL format: `rtsp://username:password@ip:port/stream` or `rtsp://ip:port/stream?user=X&password=Y`
- Common ports: 554 (default), 8554, 88
- Stream resolution: Auto-detect (support 480p to 4K)

**And** frame capture implementation:
- Uses OpenCV `cv2.VideoCapture()` with RTSP URL
- Configurable frame rate: 1-30 FPS (default 5 FPS for motion detection)
- Frame buffer: Keep last 3 frames for comparison
- Frame format: BGR color space, converted to RGB when needed
- Frame preprocessing: Resize to max 1920x1080 to reduce processing load

**And** connection resilience includes:
- Auto-reconnect on stream drop with exponential backoff (1s, 2s, 4s, 8s, max 30s)
- Maximum reconnect attempts: 10, then mark camera as "disconnected"
- Connection timeout: 10 seconds for initial connection
- Read timeout: 5 seconds per frame
- Graceful handling of network interruptions

**And** camera state management:
- Connection states: "connecting", "connected", "disconnected", "error"
- State stored in database (cameras.status column - add in migration)
- State change events logged with timestamp
- WebSocket notification sent to frontend on state change

**And** performance monitoring tracks:
- Frame capture rate (actual FPS)
- Frame drop rate (missed frames / total frames)
- Connection uptime percentage
- Latency between frame timestamp and capture time

**And** resource management:
- Thread-safe frame capture using asyncio
- Proper cleanup of VideoCapture resources on disconnect
- Memory limit: Max 50MB per camera stream in buffer
- CPU usage: <10% per camera on 2-core system

**Prerequisites:** Story 1.3 (backend API structure)

**Technical Notes:**
- Use `opencv-python` (cv2) for RTSP handling
- Consider `ffmpeg` backend for better codec support: `cv2.CAP_FFMPEG`
- Test with common camera brands: Hikvision, Dahua, Amcrest, Reolink
- RTSP URL discovery: Support ONVIF protocol for auto-discovery (Phase 2)
- Frame capture runs in background task (asyncio Task)
- Store camera connection config in database `cameras` table
- Add service class: `/backend/app/services/camera_service.py`

---

### Story 2.2: Implement USB/Webcam Support for Local Cameras

**As a** developer or tester,
**I want** to use a USB webcam or built-in laptop camera for testing,
**So that** I can develop and test without requiring RTSP hardware.

**Acceptance Criteria:**

**Given** I have a USB camera connected to my computer
**When** I configure the camera with type "usb" and device index
**Then** the system captures frames from the local camera

**And** USB camera detection provides:
- Auto-enumerate available USB cameras (indices 0, 1, 2...)
- API endpoint `GET /api/v1/cameras/usb/list` returns: `[{"index": 0, "name": "Built-in Camera"}, {"index": 1, "name": "USB Camera"}]`
- Camera name detection via platform-specific methods (DirectShow on Windows, V4L2 on Linux, AVFoundation on macOS)
- Default to index 0 if only one camera available

**And** USB camera configuration:
- Database field `camera_type = 'usb'`
- Device index stored in `rtsp_url` field as `usb://0` format
- No username/password required (fields nullable)
- Resolution configuration: Auto-detect supported resolutions, allow user override
- Frame rate: Configurable 1-30 FPS (default 10 FPS)

**And** frame capture works identically to RTSP:
- Uses `cv2.VideoCapture(device_index)` for local cameras
- Same frame buffer and preprocessing as RTSP
- Same state management (connected/disconnected/error)
- Automatic reconnect if camera disconnected and reconnected

**And** USB camera limitations are documented:
- Typically lower quality than dedicated IP cameras
- May not support night vision or advanced features
- Suitable for testing and development only
- Production deployments should use RTSP cameras

**And** platform compatibility:
- Windows 10+: DirectShow backend
- macOS 11+: AVFoundation backend
- Linux (Ubuntu 20.04+): V4L2 backend
- Test on all three platforms during development

**Prerequisites:** Story 2.1 (RTSP camera connection)

**Technical Notes:**
- OpenCV automatically handles platform-specific backends
- On Linux, ensure user has permission to access `/dev/video*` devices
- Add `camera_type` enum field to database schema
- Frontend camera configuration UI should show USB camera list dropdown
- Test with: Built-in laptop camera, Logitech C920, generic USB webcam
- Useful for CI/CD testing with simulated camera input

---

### Story 2.3: Build Camera Management API Endpoints

**As a** frontend developer,
**I want** RESTful API endpoints for camera CRUD operations,
**So that** users can configure and manage their cameras.

**Acceptance Criteria:**

**Given** I have the backend API running
**When** I make requests to camera endpoints
**Then** I can create, read, update, and delete cameras

**And** `POST /api/v1/cameras` creates a camera:
- Request body: `{"name": "Front Door", "camera_type": "rtsp", "rtsp_url": "rtsp://...", "username": "admin", "password": "pass123", "enabled": true}`
- Validation: name required (1-100 chars), camera_type enum ('rtsp'|'usb'), rtsp_url required if type=rtsp
- Response: 201 Created with camera object including generated UUID
- Password encrypted before storage using Fernet symmetric encryption
- Test connection before saving (optional, controlled by `test_connection=true` query param)

**And** `GET /api/v1/cameras` lists all cameras:
- Response: Array of camera objects (passwords masked as `****`)
- Query params: `enabled=true/false` to filter
- Includes connection status for each camera
- Sorted by created_at DESC

**And** `GET /api/v1/cameras/:id` retrieves single camera:
- Response: Full camera object (password masked)
- Returns 404 if camera not found
- Includes statistics: uptime, frame rate, last frame timestamp

**And** `PUT /api/v1/cameras/:id` updates camera:
- Request body: Partial update (only fields to change)
- Can update: name, rtsp_url, username, password, enabled
- Cannot update: id, created_at, camera_type (immutable after creation)
- Returns 404 if camera not found
- Re-establishes connection if connection params changed

**And** `DELETE /api/v1/cameras/:id` removes camera:
- Soft delete: Sets `enabled=false` and `deleted_at=now()` (add column)
- Cascade: Marks associated events as orphaned (add `camera_deleted` flag to events)
- Returns 204 No Content on success
- Returns 404 if camera not found

**And** `POST /api/v1/cameras/:id/test` tests connection:
- Attempts to connect to camera and capture one frame
- Response: `{"success": true, "message": "Connected successfully", "frame_captured": true}` or error details
- Timeout: 10 seconds
- Does not save connection state (test only)

**And** `GET /api/v1/cameras/:id/preview` returns preview frame:
- Response: JPEG image (Content-Type: image/jpeg)
- Captures latest frame from active stream
- Resized to 640x360 for fast loading
- Returns 503 if camera disconnected
- Cache-Control: no-cache (always fresh)

**And** API includes proper error handling:
- 400 Bad Request: Invalid input (with field-specific errors)
- 404 Not Found: Camera ID doesn't exist
- 409 Conflict: Duplicate camera name
- 500 Internal Server Error: Database or network issues
- Consistent error format: `{"error": "message", "details": {...}}`

**Prerequisites:** Story 2.2 (USB camera support)

**Technical Notes:**
- Create Pydantic schemas in `/backend/app/schemas/camera.py`
- Password encryption using `cryptography.fernet` with key from environment variable
- Add routes in `/backend/app/api/routes/cameras.py`
- Use SQLAlchemy async session for all database operations
- Add unit tests for each endpoint in `/backend/tests/api/test_cameras.py`
- Preview endpoint should use streaming response for large images
- Consider rate limiting on test endpoint (max 5 tests/minute per IP)

---

### Story 2.4: Implement Motion Detection Algorithm

**As a** backend developer,
**I want** efficient motion detection that triggers AI processing,
**So that** the system only analyzes frames when something is happening.

**Acceptance Criteria:**

**Given** I have a camera stream with continuous frame capture
**When** motion is detected above the configured threshold
**Then** an event trigger is created for AI processing

**And** motion detection algorithm uses:
- Method: Background subtraction with MOG2 (Mixture of Gaussians) from OpenCV
- Alternative: Frame differencing for simpler/faster detection
- Configurable via system settings: `motion_detection_method` ('mog2' or 'frame_diff')
- Background learning: First 30 frames used to establish baseline
- Update rate: Background model updated every 10 frames

**And** motion detection sensitivity:
- Three levels: 'low' (50% threshold), 'medium' (30% threshold), 'high' (10% threshold)
- Threshold represents % of frame that must change to trigger
- Stored in system_settings: `motion_sensitivity`
- Adjustable per camera in future (Phase 2)

**And** motion filtering reduces false positives:
- Minimum motion area: 1% of frame (filters out noise, small movements)
- Maximum motion area: 90% of frame (filters out camera adjustments, lighting changes)
- Minimum duration: Motion must persist for 3 consecutive frames (300-600ms at 5-10 FPS)
- Ignore regions: Support for masking areas (e.g., trees, flags) - stored as polygons

**And** cooldown period prevents spam:
- Configurable cooldown: 30-60 seconds (default 30s)
- During cooldown, motion detected but no AI trigger created
- Cooldown resets after motion stops for 10 seconds
- Per-camera cooldown tracking in memory (dict)

**And** motion detection outputs:
- Boolean: Motion detected (yes/no)
- Confidence: 0-100 based on amount of motion detected
- Bounding box: Coordinates of motion region (x, y, width, height)
- Motion mask: Binary image showing motion pixels (for debugging)
- Timestamp: When motion was detected

**And** performance optimizations:
- Frame resizing: Detect on 640x360 resolution (faster than full res)
- Frame skipping: Process every 2nd frame if CPU constrained
- GPU acceleration: Use CUDA if available (cv2.cuda module)
- Processing time: <50ms per frame on 2-core CPU

**And** debugging and visualization:
- Debug mode: Save motion mask images to `/backend/debug/motion/`
- Logging: Log motion events with confidence and bounding box
- Metrics: Track detection rate, false positive estimates
- Dashboard: Show live motion detection status per camera

**Prerequisites:** Story 2.1 (RTSP camera connection)

**Technical Notes:**
- Create service: `/backend/app/services/motion_detector.py`
- OpenCV methods: `cv2.createBackgroundSubtractorMOG2()` or `cv2.absdiff()` for frame differencing
- Morphological operations (erosion, dilation) to reduce noise in motion mask
- Connected component analysis to identify distinct motion regions
- Consider integration with PIR (Passive Infrared) sensors for hardware-assisted detection (Phase 2)
- Motion events logged to separate table for analytics (optional)
- Test with: Person walking, car driving, tree swaying, lighting changes, camera shake

---

### Story 2.5: Create Camera Configuration UI in Dashboard

**As a** user,
**I want** an intuitive interface to add and manage my cameras,
**So that** I can configure the system without technical expertise.

**Acceptance Criteria:**

**Given** I am on the dashboard cameras page
**When** I click "Add Camera" button
**Then** I see a modal with camera configuration form

**And** the camera form includes:
- Camera Name: Text input, required, max 100 chars, placeholder "Front Door Camera"
- Camera Type: Radio buttons for "RTSP Camera" or "USB Webcam", default RTSP
- RTSP URL: Text input (shown if type=RTSP), required, placeholder "rtsp://192.168.1.100:554/stream"
- Username: Text input (shown if type=RTSP), optional
- Password: Password input (shown if type=RTSP), optional, masked characters
- USB Device: Dropdown select (shown if type=USB), options populated from API
- Enable Camera: Toggle switch, default ON

**And** the form includes validation:
- Name: Required, 1-100 characters, no special chars except spaces and hyphens
- RTSP URL: Valid URL format starting with `rtsp://`, show error if invalid
- USB Device: Must select from dropdown if type=USB
- Real-time validation with inline error messages (red text below field)
- Submit button disabled until all required fields valid

**And** "Test Connection" button:
- Located below form fields, prominent blue button
- Calls `POST /api/v1/cameras/:id/test` endpoint
- Shows loading spinner while testing (max 10 seconds)
- Success: Green checkmark icon + "Connected successfully! Preview:" with thumbnail
- Failure: Red X icon + error message (e.g., "Connection refused", "Invalid credentials", "Timeout")
- Thumbnail preview: 320x180 JPEG from `/api/v1/cameras/:id/preview`

**And** form submission:
- "Save Camera" button (primary, bottom right), "Cancel" button (secondary, bottom left)
- On save: POST to `/api/v1/cameras` with form data
- Success: Close modal, show toast notification "Camera added successfully", refresh camera list
- Error: Show error message at top of modal, keep modal open for corrections
- Loading state: Disable form and show spinner during save

**And** cameras page displays camera list:
- Card-based layout, 2 columns on desktop, 1 column on mobile
- Each card shows: Camera name (h3), connection status indicator (green dot=connected, red=disconnected, yellow=connecting), preview thumbnail (320x180), Edit/Delete buttons
- Preview auto-refreshes every 5 seconds via API polling
- Sort by: Name (alphabetical), Status (connected first), Created (newest first) - toggle button

**And** edit camera functionality:
- Click Edit button opens same modal pre-filled with camera data
- Password field shows `••••••••` placeholder (not actual password)
- Can update all fields except camera ID
- "Update Camera" button (instead of "Save Camera")
- PUT request to `/api/v1/cameras/:id`

**And** delete camera functionality:
- Click Delete button shows confirmation dialog: "Delete [Camera Name]? This will remove all associated events."
- Confirm button (red, "Delete"), Cancel button (gray)
- On confirm: DELETE to `/api/v1/cameras/:id`
- Success: Remove card from list, show toast "Camera deleted"
- Error: Show error toast with message

**And** responsive design:
- Mobile (<640px): Single column, stacked form fields, full-width buttons
- Tablet (640-1024px): Two-column camera grid
- Desktop (>1024px): Three-column camera grid, side-by-side form fields where appropriate
- Touch targets: Minimum 44x44px for buttons and toggles
- Keyboard navigation: Tab through form fields, Enter to submit, Escape to close modal

**Prerequisites:** Story 2.3 (camera API endpoints)

**Technical Notes:**
- Create components: `/frontend/components/CameraForm.tsx`, `/frontend/components/CameraCard.tsx`, `/frontend/components/CameraList.tsx`
- Use Headless UI for modal (`Dialog`) and toggle (`Switch`)
- Form validation with Zod schema
- State management with React Query (TanStack Query) for API calls
- Optimistic updates: Add camera to UI immediately, rollback on error
- Image loading: Use Next.js `<Image>` with placeholder blur
- Toast notifications: Use `react-hot-toast` or similar library
- Error messages should be user-friendly (not raw API errors)

---

## Epic 3: AI Intelligence & Event Processing

**Goal:** Transform visual motion triggers into rich semantic event descriptions. Implement the core value proposition - AI-powered natural language generation that creates searchable, meaningful event records.

---

### Story 3.1: Integrate AI Vision API for Description Generation

**As a** backend developer,
**I want** to send frames to AI vision models and receive natural language descriptions,
**So that** motion events are transformed into meaningful semantic records.

**Acceptance Criteria:**

**Given** motion has been detected and a frame captured
**When** the frame is sent to the AI vision API
**Then** a rich natural language description is returned within 5 seconds

**And** AI model integration supports:
- Primary model: OpenAI GPT-4o mini (vision capable)
- Secondary models: Anthropic Claude 3 Haiku, Google Gemini Flash
- Model selection configurable in system_settings
- API key stored encrypted in database
- HTTP timeout: 10 seconds with retry logic

**And** image preprocessing before API call:
- Resize to max 2048x2048 (AI models have size limits)
- Convert to JPEG format with 85% quality
- Base64 encode for API transmission
- Maximum payload size: 5MB after encoding

**And** AI prompt is optimized for security/accessibility:
- System prompt: "You are describing video surveillance events for home security and accessibility. Provide detailed, accurate descriptions."
- User prompt template: "Describe what you see in this image. Include: WHO (people, their appearance, clothing), WHAT (objects, vehicles, packages), WHERE (location in frame), and ACTIONS (what is happening). Be specific and detailed."
- Prompt includes context: camera name, timestamp, detected objects from motion detection

**And** API response parsing:
- Extract description text from model response
- Generate confidence score based on model certainty (0-100)
- Identify detected objects from description (person, vehicle, animal, package, unknown)
- Handle API errors gracefully with fallback responses
- Log all API calls for debugging and cost tracking

**And** error handling and fallback:
- If primary model fails → try secondary model
- If all models fail → store event with description "Failed to generate description" + error reason
- Rate limit handling: Exponential backoff on 429 errors
- Invalid API key: Alert administrator immediately
- Network errors: Retry up to 3 times with 2s, 4s, 8s delays

**And** cost and usage tracking:
- Log API calls with: model used, tokens consumed, response time, cost estimate
- Track daily/monthly API usage
- Warning when approaching rate limits or budget thresholds
- API endpoint: `GET /api/v1/ai/usage` returns usage statistics

**Prerequisites:** Story 2.4 (motion detection)

**Technical Notes:**
- Create service: `/backend/app/services/ai_service.py`
- Use `httpx` async client for API calls
- OpenAI client library: `openai` Python package
- Claude client: `anthropic` Python package
- Gemini client: `google-generativeai` package
- Store API keys in environment variables with encryption at rest
- Test with diverse scenarios: daytime/nighttime, different weather, various subjects
- Consider local AI models (Llama Vision) for privacy-focused deployments (Phase 2)

---

### Story 3.2: Implement Event Storage and Retrieval System

**As a** backend developer,
**I want** to store AI-generated events in the database with full metadata,
**So that** events can be queried, filtered, and displayed to users.

**Acceptance Criteria:**

**Given** an AI description has been generated for a motion event
**When** the event is stored in the database
**Then** all event data is persisted reliably with proper indexing

**And** event creation includes:
- Generate UUID for event ID
- Store camera_id (foreign key to cameras table)
- Store timestamp (ISO 8601 format, indexed)
- Store description (AI-generated text, full-text searchable)
- Store confidence score (0-100)
- Store objects_detected (JSON array parsed from description)
- Store thumbnail (either file path or base64, configurable)
- Set alert_triggered=false initially (updated by alert engine)
- Record created_at timestamp

**And** thumbnail storage supports two modes:
- File system: Save JPEG to `/backend/data/thumbnails/{event_id}.jpg`, store path in DB
- Database: Store base64-encoded image in `thumbnail_base64` column
- Mode configurable via `THUMBNAIL_STORAGE_MODE` environment variable
- File system mode: Create directory if doesn't exist, handle write errors
- Image size limit: 200KB per thumbnail (resize if needed)

**And** event retrieval API endpoint `POST /api/v1/events`:
- Accepts event data from AI service
- Validates all required fields (Pydantic schema)
- Returns 201 Created with full event object
- Triggers alert rule evaluation (async task)
- Broadcasts event to WebSocket connections
- Response time: <100ms for database write

**And** event query endpoint `GET /api/v1/events`:
- Query parameters: `camera_id`, `start_date`, `end_date`, `object_type`, `limit`, `offset`, `search`
- Default: Last 50 events, sorted by timestamp DESC
- Pagination: limit (max 100), offset for cursor-based paging
- Filter by camera: `?camera_id=uuid`
- Filter by date range: `?start_date=2025-11-01&end_date=2025-11-16`
- Filter by objects: `?object_type=person` (supports multiple: `object_type=person,vehicle`)
- Full-text search: `?search=delivery package` (searches description field)
- Response includes: events array, total_count, pagination metadata

**And** single event endpoint `GET /api/v1/events/:id`:
- Returns full event object including thumbnail
- Thumbnail as base64 data URL or file path (frontend handles retrieval)
- Returns 404 if event not found
- Includes related camera information

**And** event statistics endpoint `GET /api/v1/events/stats`:
- Returns aggregated statistics:
  - Total events (all time, today, this week)
  - Events by camera (count per camera)
  - Events by object type (count per type)
  - Events by hour of day (for pattern analysis)
  - Average confidence score
- Time range filters supported
- Cached for 1 minute to reduce database load

**And** performance optimization:
- Database indexes on: timestamp, camera_id, objects_detected
- Full-text search index (FTS5) on description field
- Query response time: <100ms for typical queries (50 events)
- Efficient pagination using offset/limit
- Connection pooling for concurrent requests

**Prerequisites:** Story 3.1 (AI integration)

**Technical Notes:**
- Create Pydantic schemas in `/backend/app/schemas/event.py`
- Add routes in `/backend/app/api/routes/events.py`
- SQLAlchemy async queries for all database operations
- Use `LIKE` with FTS5 for full-text search on SQLite
- Thumbnail retrieval endpoint: `GET /api/v1/events/:id/thumbnail` (returns image file)
- Add database migration for FTS5 virtual table
- Test with 1000+ events to ensure query performance
- Consider PostgreSQL migration path for production scale

---

### Story 3.3: Build Event-Driven Processing Pipeline

**As a** backend developer,
**I want** an asynchronous event processing pipeline from motion detection to storage,
**So that** the system handles events efficiently without blocking.

**Acceptance Criteria:**

**Given** the system is running with cameras connected
**When** motion is detected
**Then** the event flows through the pipeline: detect → capture → AI → store → alert

**And** pipeline architecture uses:
- Asyncio for concurrent processing
- Queue-based architecture (asyncio.Queue)
- Separate async tasks for each camera
- Background workers for AI processing
- Non-blocking database operations

**And** motion detection task:
- Runs continuously for each enabled camera
- Checks for motion every frame (5-10 FPS)
- When motion detected → capture best frame → add to processing queue
- Cooldown enforced (no new events during cooldown period)
- Gracefully handles camera disconnections

**And** AI processing worker pool:
- Configurable number of workers (default: 2, max: 5)
- Workers pull events from queue (FIFO)
- Each worker processes one event at a time
- Parallel processing: Multiple events processed simultaneously
- Queue max size: 50 events (reject new events if queue full)

**And** processing flow:
1. Motion detected → Frame captured → Event queued
2. Worker picks event from queue
3. Frame sent to AI API
4. Description received → Event stored in database
5. Alert rules evaluated → Notifications sent if triggered
6. WebSocket broadcast to connected clients
7. Processing complete → Worker ready for next event

**And** error handling and resilience:
- AI API failures → Retry with fallback model
- Database failures → Log error, retry up to 3 times
- Queue overflow → Drop oldest events, log warning
- Worker crashes → Automatically restart worker
- Camera disconnects → Pause processing, resume on reconnect

**And** monitoring and metrics:
- Track queue depth (current events waiting)
- Track processing time per event (p50, p95, p99)
- Track success/failure rates
- Expose metrics via `/api/v1/metrics` endpoint
- Prometheus-compatible metrics (optional)

**And** performance targets:
- End-to-end latency: <5 seconds (motion → stored event)
- Throughput: Process 10+ events per minute
- Queue depth: Typically <5 events
- CPU usage: <50% on 2-core system
- Memory usage: <1GB for event processing

**And** graceful shutdown:
- SIGTERM handler drains queue before exit
- Save queue state to disk (optional)
- Complete in-flight events before shutdown
- Timeout: 30 seconds max for shutdown

**Prerequisites:** Story 3.2 (event storage)

**Technical Notes:**
- Create orchestrator: `/backend/app/services/event_processor.py`
- Use `asyncio.create_task()` for concurrent tasks
- Queue implementation: `asyncio.Queue` with maxsize
- Worker pattern: Async while loop consuming from queue
- Structured logging for all pipeline stages
- Add startup task in FastAPI lifespan to initialize pipeline
- Consider Redis queue for distributed deployment (Phase 2)
- Test with simulated high load (50+ events/minute)

---

### Story 3.4: Implement Data Retention and Cleanup

**As a** system administrator,
**I want** automatic cleanup of old events based on retention policy,
**So that** storage doesn't grow unbounded and complies with user preferences.

**Acceptance Criteria:**

**Given** a data retention policy is configured
**When** the cleanup job runs
**Then** events older than the retention period are deleted

**And** retention policy configuration:
- Stored in system_settings table
- Options: 7 days, 30 days, 90 days, 1 year, forever
- Default: 30 days
- Configurable via UI settings page
- Applied to: events table and thumbnail files

**And** cleanup job runs:
- Scheduled task: Daily at 2:00 AM server time
- Uses APScheduler or similar cron-like scheduler
- Identifies events where `created_at < now() - retention_days`
- Batch deletion: Delete max 1000 events per run (prevent long locks)
- Transaction-based: All or nothing for each batch

**And** cleanup includes:
- Delete event records from database
- Delete associated thumbnail files (if file storage mode)
- Delete associated webhook logs
- Cascade delete handled by foreign key constraints
- Log deletion statistics (count of deleted events)

**And** user notification before deletion:
- Email notification 24 hours before cleanup (if email configured)
- Dashboard banner: "X events will be deleted in 24 hours"
- Option to export events before deletion
- Notification can be disabled in settings

**And** export functionality:
- Export endpoint: `GET /api/v1/events/export?format=json|csv`
- JSON format: Full event objects including descriptions
- CSV format: Flattened data (id, timestamp, camera, description, confidence, objects)
- Date range filters supported
- Streaming response for large exports
- Download as file attachment

**And** manual cleanup option:
- Admin endpoint: `DELETE /api/v1/events/cleanup?before_date=2025-01-01`
- Requires confirmation parameter
- Runs cleanup immediately (synchronous)
- Returns count of deleted events
- Audit log entry created

**And** storage space monitoring:
- Track database size: Query `PRAGMA page_count * page_size` (SQLite)
- Track thumbnail directory size (if file storage)
- Display in dashboard: "Using XMB of storage (Y events)"
- Warning when approaching disk space limits (>80% full)

**Prerequisites:** Story 3.2 (event storage)

**Technical Notes:**
- Use `APScheduler` for scheduled tasks: `pip install apscheduler`
- Scheduler initialized in FastAPI lifespan startup
- Create service: `/backend/app/services/cleanup_service.py`
- Deletion query: `DELETE FROM events WHERE created_at < ?` with index on created_at
- Thumbnail cleanup: `os.remove(thumbnail_path)` with error handling
- Export uses streaming: `StreamingResponse` with generator
- CSV export: `csv.DictWriter` for formatting
- Add configuration UI in frontend settings page
- Test with large datasets (10K+ events)

---

## Epic 4: Dashboard & Event Visualization

**Goal:** Enable users to view, search, and interact with detected events through an intuitive Next.js dashboard. Provide real-time monitoring with live camera previews and event notifications.

---

### Story 4.1: Build Next.js Dashboard Foundation and Layout

**As a** frontend developer,
**I want** a responsive dashboard layout with navigation and routing,
**So that** users can access all features through a clean interface.

**Acceptance Criteria:**

**Given** the frontend application is initialized
**When** a user navigates to the dashboard
**Then** they see a professional, responsive layout with navigation

**And** application structure includes:
- App Router architecture: `/frontend/app` directory
- Layout component: `/frontend/app/layout.tsx` with persistent header/sidebar
- Pages: `/` (home/dashboard), `/events`, `/cameras`, `/rules`, `/settings`
- Components: `/frontend/components` for reusable UI elements
- TypeScript strict mode enabled throughout

**And** header component contains:
- Logo/branding (top left)
- Navigation links: Dashboard, Events, Cameras, Rules, Settings
- Notification bell icon with unread count badge
- System status indicator (green=healthy, red=degraded)
- User menu dropdown (logout, profile - Phase 1.5)

**And** sidebar navigation (desktop >1024px):
- Fixed left sidebar, 240px width
- Icons + labels for each section
- Active state highlighting (blue background)
- Collapse/expand button (hamburger icon)
- Collapsed state shows icons only (64px width)

**And** mobile navigation (<1024px):
- Bottom tab bar with icons
- Hamburger menu for header
- Swipe gestures for sidebar (optional)
- Full-screen pages (no persistent sidebar)

**And** responsive breakpoints:
- Mobile: <640px (single column, bottom tabs)
- Tablet: 640-1024px (two columns, top nav)
- Desktop: >1024px (sidebar + multi-column content)

**And** theme and styling:
- Tailwind CSS utility classes
- Custom theme in `tailwind.config.ts`:
  - Primary color: Blue (#3B82F6)
  - Success: Green (#10B981)
  - Warning: Yellow (#F59E0B)
  - Error: Red (#EF4444)
  - Neutral: Gray scale
- Dark mode support (optional, Phase 2)
- Font: Inter from Google Fonts

**And** routing configuration:
- Client-side navigation with Next.js Link components
- Loading states for page transitions
- Error boundaries for graceful error handling
- 404 page for invalid routes
- Metadata and SEO tags in layout

**And** global state management:
- React Context for: auth state, notifications, system settings
- TanStack Query for: API data fetching, caching, mutations
- Local state: useState/useReducer for component-specific state

**Prerequisites:** Story 1.1 (project initialization)

**Technical Notes:**
- Create layout: `/frontend/app/layout.tsx`
- Create components: `Header.tsx`, `Sidebar.tsx`, `MobileNav.tsx`
- Use Headless UI for dropdowns and menus
- Heroicons for all icon needs
- Add loading.tsx and error.tsx for Next.js conventions
- Implement not-found.tsx for 404 handling
- Configure middleware for redirects (if needed)

---

### Story 4.2: Create Event Timeline View with Filtering

**As a** user,
**I want** to see all detected events in a chronological timeline,
**So that** I can review what happened when I was away.

**Acceptance Criteria:**

**Given** I am on the Events page
**When** events are loaded from the API
**Then** I see a scrollable timeline of event cards with descriptions and thumbnails

**And** event card displays:
- Thumbnail image (320x180px, left side)
- Timestamp: "2 hours ago" (relative time with tooltip showing exact time)
- Camera name with icon
- AI description (full text, max 3 lines with "Read more" expansion)
- Confidence score: Visual indicator (90-100%=green, 70-89%=yellow, <70%=red)
- Detected objects: Pills/badges (Person, Vehicle, etc.)
- Click to expand: Shows full details modal

**And** timeline layout:
- Card-based design, one column
- Infinite scroll: Load 20 events at a time
- Lazy loading: Images load as they enter viewport
- Smooth scrolling with scroll-to-top button (appears after scrolling)
- Empty state: "No events found" with helpful message

**And** filter sidebar contains:
- Date range picker: Quick selections (Today, Last 7 days, Last 30 days, Custom range)
- Camera multi-select: Checkboxes for each camera
- Object type filter: Checkboxes for Person, Vehicle, Animal, Package, Unknown
- Confidence filter: Slider (0-100%)
- Apply/Reset buttons

**And** search functionality:
- Search bar at top: "Search events..."
- Full-text search on description field
- Search executes on Enter key or after 500ms debounce
- Results update timeline in real-time
- Highlight search terms in results (optional)

**And** filtering behavior:
- Filters combine with AND logic (camera AND object AND date range)
- Real-time updates: Timeline refreshes as filters change
- URL query params: Filters persist in URL (`?camera=uuid&object=person&date=7d`)
- Shareable URLs: Copy link with filters applied
- Filter count badge: Show number of active filters

**And** event detail modal (click on card):
- Full-size thumbnail image (640x480 or larger)
- Complete description (no truncation)
- All metadata: Timestamp, camera, confidence, objects
- Actions: Download image, Delete event, Provide feedback (Phase 2)
- Close button and backdrop click to close
- Keyboard: Escape to close, Arrow keys for prev/next event

**And** performance optimization:
- Virtual scrolling for large event lists (react-window)
- Image lazy loading with blur placeholder
- Debounced search input (500ms delay)
- Cached API responses (TanStack Query)
- Optimistic UI updates for smooth experience

**Prerequisites:** Story 3.2 (event API endpoints)

**Technical Notes:**
- Create page: `/frontend/app/events/page.tsx`
- Create components: `EventCard.tsx`, `EventDetailModal.tsx`, `EventFilters.tsx`
- Use TanStack Query: `useInfiniteQuery` for pagination
- Date picker: `react-datepicker` or Headless UI custom component
- Relative time: `date-fns/formatDistanceToNow`
- Virtual scrolling: `react-window` or `@tanstack/react-virtual`
- Image optimization: Next.js `<Image>` component with blur placeholders
- URL state: `next/navigation` useSearchParams, useRouter
- Modal: Headless UI `Dialog` component

---

### Story 4.3: Implement Live Camera Preview Grid

**As a** user,
**I want** to see live previews of all my cameras on the dashboard,
**So that** I can monitor my property in real-time.

**Acceptance Criteria:**

**Given** I have cameras configured and connected
**When** I view the dashboard home page
**Then** I see a grid of live camera previews with current status

**And** camera preview grid:
- Responsive grid: 1 column (mobile), 2 columns (tablet), 3 columns (desktop)
- Each preview shows: Camera name (header), live thumbnail (auto-refreshing), connection status, last update time
- Grid auto-adjusts based on number of cameras (1-4 cameras supported in MVP)
- Consistent card sizing with aspect ratio 16:9

**And** live preview functionality:
- Auto-refresh: Fetch new frame every 2 seconds from `/api/v1/cameras/:id/preview`
- Polling: Use setInterval or React Query with refetchInterval
- Loading state: Skeleton/spinner while fetching first frame
- Error state: Red border + "Camera offline" message if preview fails
- Smooth transitions: Fade-in effect for new frames

**And** connection status indicator:
- Green dot + "Connected": Camera streaming normally
- Yellow dot + "Connecting": Camera initializing
- Red dot + "Disconnected": Camera offline or error
- Gray dot + "Disabled": Camera manually disabled
- Status updates in real-time (WebSocket or polling)

**And** preview card interactions:
- Click camera preview → Navigate to `/cameras/:id` detail page (Phase 2)
- Hover → Show "Analyze Now" button for manual trigger
- Right-click → Context menu: View events, Configure, Disable (optional)

**And** manual analysis trigger:
- "Analyze Now" button overlay (appears on hover)
- Click → API call to `POST /api/v1/events/analyze` with camera_id
- Loading spinner during analysis (up to 10 seconds)
- Success: Show toast "Analysis complete" + navigate to new event
- Error: Show toast with error message

**And** performance considerations:
- Stagger preview refreshes: Don't fetch all simultaneously (100ms offset per camera)
- Pause refreshing when page not visible (Page Visibility API)
- Reduce refresh rate on mobile/battery saver (detect with Network Information API)
- Image caching: Use browser cache headers
- Graceful degradation: Show static image if browser can't handle auto-refresh

**And** empty state:
- No cameras configured: "Add your first camera to get started" + "Add Camera" button
- All cameras disconnected: "All cameras offline. Check your network connection."
- Cameras disabled: "Enable cameras to see live previews."

**Prerequisites:** Story 2.3 (camera API) and Story 2.5 (camera UI)

**Technical Notes:**
- Create component: `/frontend/components/CameraPreviewGrid.tsx`, `/frontend/components/CameraPreview.tsx`
- Use TanStack Query: `useQuery` with refetchInterval for auto-refresh
- Image loading: Next.js Image with unoptimized prop for dynamic images
- Grid layout: CSS Grid or Tailwind grid classes
- Status indicator: Separate component `ConnectionStatus.tsx`
- Page Visibility: `document.visibilityState` to pause updates when hidden
- Manual analysis: Mutation with `useMutation` from TanStack Query
- Toast notifications: `react-hot-toast`

---

### Story 4.4: Build System Settings Page

**As a** user,
**I want** a centralized settings page to configure all system options,
**So that** I can customize the system without editing configuration files.

**Acceptance Criteria:**

**Given** I navigate to the Settings page
**When** I view the settings interface
**Then** I see organized tabs with all configurable system options

**And** settings page layout:
- Tabbed interface: General, AI Models, Motion Detection, Data & Privacy
- Left sidebar: Tab navigation (desktop)
- Top pills: Tab navigation (mobile)
- Form-based settings with clear labels and help text
- Save button (bottom right), Cancel button (bottom left)
- Auto-save indicator: "Saved" message with timestamp

**And** General tab includes:
- System Name: Text input (default: "Live Object AI Classifier")
- Timezone: Dropdown selector (auto-detect user timezone)
- Language: Dropdown (English only in MVP, placeholder for future)
- Date format: Dropdown (MM/DD/YYYY, DD/MM/YYYY, YYYY-MM-DD)
- Time format: Radio buttons (12-hour, 24-hour)

**And** AI Models tab includes:
- Primary Model: Dropdown (GPT-4o mini, Claude 3 Haiku, Gemini Flash)
- API Key: Password input (masked, shows "••••••••" if set)
- Test API Key: Button (validates key with test request)
- Fallback Model: Dropdown (same options, can be "None")
- Description Prompt: Textarea (advanced users can customize prompt)
- Reset to Default Prompt: Button

**And** Motion Detection tab includes:
- Sensitivity: Slider with labels (Low, Medium, High)
- Detection Method: Radio buttons (Background Subtraction, Frame Difference)
- Cooldown Period: Number input with unit selector (30-300 seconds)
- Minimum Motion Area: Slider (1-10% of frame)
- Save Debug Images: Toggle (on/off, for troubleshooting)

**And** Data & Privacy tab includes:
- Data Retention: Dropdown (7 days, 30 days, 90 days, 1 year, Forever)
- Thumbnail Storage: Radio buttons (File System, Database)
- Auto Cleanup: Toggle (enable/disable automatic cleanup)
- Export Data: Button (download all events as JSON/CSV)
- Delete All Data: Button (requires confirmation, red button)

**And** form validation and saving:
- Real-time validation: Show errors below fields
- Disable Save button if validation fails
- Save button: POST to `/api/v1/settings` with changed values only
- Success: Show toast "Settings saved successfully"
- Error: Show inline errors and toast "Failed to save settings"
- Optimistic updates: UI updates immediately, rollback on error

**And** API key testing:
- Test button calls `/api/v1/ai/test-key` with model and key
- Shows loading spinner during test (max 10 seconds)
- Success: Green checkmark + "API key valid"
- Error: Red X + specific error message ("Invalid key", "Rate limit exceeded", etc.)

**And** dangerous actions have confirmations:
- Delete All Data: Modal confirmation "Are you sure? This cannot be undone."
- Change Retention (shortening): Warning "This will delete X events immediately"
- Reset Prompt: Confirmation "Restore default prompt?"

**Prerequisites:** Story 1.3 (backend settings), Story 3.1 (AI service)

**Technical Notes:**
- Create page: `/frontend/app/settings/page.tsx`
- Create components: `SettingsTabs.tsx`, `GeneralSettings.tsx`, `AISettings.tsx`, etc.
- Form handling: `react-hook-form` with Zod validation
- Tabs: Headless UI `Tab` component
- Settings API: `GET /api/v1/settings`, `PUT /api/v1/settings`
- Timezone detection: `Intl.DateTimeFormat().resolvedOptions().timeZone`
- Export: Trigger download via anchor element with blob URL
- Confirmation modals: Headless UI Dialog

---

## Epic 5: Alert & Automation System

**Goal:** Enable automated responses and notifications based on detected events. Build the alert rule engine that evaluates conditions and triggers webhooks for smart home integration.

---

### Story 5.1: Implement Alert Rule Engine

**As a** backend developer,
**I want** a rule evaluation engine that triggers alerts based on event conditions,
**So that** users receive notifications when specific events occur.

**Acceptance Criteria:**

**Given** alert rules are configured
**When** a new event is stored
**Then** all active rules are evaluated and matching rules trigger alerts

**And** rule data structure (JSON in database):
```json
{
  "conditions": {
    "object_types": ["person", "vehicle"],
    "cameras": ["camera-uuid-1"],
    "time_of_day": {"start": "20:00", "end": "06:00"},
    "days_of_week": [1,2,3,4,5],
    "min_confidence": 70
  },
  "actions": {
    "dashboard_notification": true,
    "webhook": {"url": "https://...", "headers": {}}
  }
}
```

**And** rule evaluation logic:
- Triggered on event creation (async task after event stored)
- Evaluates all enabled rules (`enabled=true`)
- Conditions use AND logic (all conditions must match)
- Object type: Event must contain at least one matching object
- Camera: Event must be from specified camera(s), or "any camera"
- Time of day: Event timestamp within time range (optional)
- Days of week: Event on specified days (1=Monday, 7=Sunday) (optional)
- Confidence: Event confidence >= minimum (optional)

**And** cooldown enforcement:
- Check `last_triggered` timestamp for each rule
- If `now() - last_triggered < cooldown_minutes` → Skip rule (no alert)
- If cooldown expired → Evaluate rule normally
- Update `last_triggered` timestamp when rule fires
- Cooldown per rule (independent tracking)

**And** rule execution flow:
1. Event stored → Trigger rule evaluation task
2. Load all enabled rules from database
3. For each rule:
   - Check cooldown (skip if in cooldown)
   - Evaluate conditions (AND logic)
   - If match → Execute actions
   - Update last_triggered timestamp
4. Log evaluation results (matched rules, actions executed)

**And** action execution:
- Dashboard notification: Create notification record, broadcast via WebSocket
- Webhook: Queue webhook HTTP POST (async task)
- Email/SMS: Placeholder for Phase 2
- Multiple actions can execute for single rule

**And** performance and reliability:
- Rule evaluation completes in <500ms
- Asynchronous: Doesn't block event storage
- Error handling: Failed actions logged but don't block other rules
- Retry logic: Webhook failures retry up to 3 times
- Audit trail: Log all rule executions in webhook_logs or audit table

**And** rule management API (already created in Epic 5 planning):
- CRUD endpoints: `GET/POST/PUT/DELETE /api/v1/rules`
- Test endpoint: `POST /api/v1/rules/:id/test` (evaluate against recent events)
- Enable/disable: `PATCH /api/v1/rules/:id/enable`

**Prerequisites:** Story 3.2 (event storage)

**Technical Notes:**
- Create service: `/backend/app/services/alert_engine.py`
- Rule evaluation function: `evaluate_rule(rule, event) -> bool`
- Time of day comparison: Convert to datetime.time objects
- Days of week: `event.timestamp.weekday() + 1` (ISO weekday)
- Webhook execution: Create separate task with httpx async POST
- Add rule evaluation to event creation pipeline
- Database transaction: Update last_triggered atomically
- Consider rule caching in memory for performance (invalidate on changes)

---

### Story 5.2: Build Alert Rule Configuration UI

**As a** user,
**I want** an intuitive interface to create and manage alert rules,
**So that** I can define when I want to be notified without writing code.

**Acceptance Criteria:**

**Given** I am on the Alert Rules page
**When** I click "Create Rule"
**Then** I see a visual rule builder form

**And** rules list page displays:
- Table view: Rule name, Status (enabled/disabled toggle), Conditions summary, Last triggered, Actions
- Empty state: "Create your first alert rule to get notified"
- "Create Rule" button (top right, prominent blue button)
- Edit/Delete icons per row
- Enable/disable toggle (updates immediately)

**And** create rule form contains:
- Rule Name: Text input, required, max 100 chars, placeholder "Package delivery alert"
- Enabled: Toggle switch, default ON
- Conditions section (card):
  - Object Types: Multi-select checkboxes (Person, Vehicle, Animal, Package, Unknown)
  - Cameras: Multi-select dropdown (all cameras, or specific cameras)
  - Time of Day: Time range picker (optional, "Only between X and Y")
  - Days of Week: Checkboxes (Mon-Sun, default all selected)
  - Minimum Confidence: Slider (0-100%, default 70%)
- Actions section (card):
  - Dashboard Notification: Checkbox (default ON)
  - Webhook: Checkbox, conditional URL input field
  - Webhook URL: Text input (validated URL format)
  - Webhook Headers: Key-value inputs (optional, for auth)
- Cooldown section:
  - Cooldown Period: Slider or number input (0-60 minutes, default 5 minutes)
  - Help text: "Prevent repeated alerts for same rule"

**And** form validation:
- Rule name: Required, 1-100 characters
- At least one condition must be set (can't create "always trigger" rule)
- At least one action must be enabled
- Webhook URL: Valid HTTPS URL if webhook action enabled
- Real-time validation with inline error messages

**And** rule testing feature:
- "Test Rule" button (bottom of form)
- Evaluates rule against last 50 events
- Shows list of matching events: "This rule would match X events"
- Displays matched event cards (mini preview)
- Helps user verify rule logic before saving

**And** save behavior:
- "Save Rule" button: POST to `/api/v1/rules`
- Success: Close modal/form, show toast "Rule created", add to table
- Error: Show inline errors, keep form open
- "Cancel" button: Discard changes, confirm if form dirty

**And** edit functionality:
- Click Edit icon → Open same form pre-filled with rule data
- All fields editable
- "Update Rule" button (PUT to `/api/v1/rules/:id`)
- Can test rule with updated conditions before saving

**And** delete functionality:
- Click Delete icon → Confirmation modal "Delete [Rule Name]?"
- Explain consequences: "Alerts will no longer trigger"
- Confirm button (red, "Delete"), Cancel button
- DELETE to `/api/v1/rules/:id`
- Success: Remove from table, show toast

**And** responsive design:
- Mobile: Vertical stacked form, full-width inputs
- Desktop: Two-column layout for conditions/actions
- Accessible: Labels, ARIA attributes, keyboard navigation
- Touch-friendly: 44px+ touch targets

**Prerequisites:** Story 5.1 (alert engine)

**Technical Notes:**
- Create page: `/frontend/app/rules/page.tsx`
- Create components: `RuleForm.tsx`, `RulesList.tsx`, `RuleTestResults.tsx`
- Form handling: `react-hook-form` + Zod validation
- Multi-select: Headless UI `Listbox` or custom checkbox group
- Time picker: Custom component or `react-datepicker`
- Toggle: Headless UI `Switch`
- Table: Custom or `@tanstack/react-table`
- API calls: TanStack Query mutations and queries

---

### Story 5.3: Implement Webhook Integration

**As a** smart home enthusiast,
**I want** to trigger webhooks when events occur,
**So that** I can integrate with Home Assistant and other automation platforms.

**Acceptance Criteria:**

**Given** a rule with webhook action is triggered
**When** the rule matches an event
**Then** an HTTP POST request is sent to the configured webhook URL

**And** webhook payload format (JSON):
```json
{
  "event_id": "uuid",
  "timestamp": "2025-11-16T15:30:00Z",
  "camera": {"id": "uuid", "name": "Front Door"},
  "description": "Person approaching front door...",
  "confidence": 92,
  "objects_detected": ["person"],
  "thumbnail_url": "https://.../api/v1/events/uuid/thumbnail",
  "rule": {"id": "uuid", "name": "Front door visitor"}
}
```

**And** webhook HTTP request:
- Method: POST
- Content-Type: application/json
- Headers: User-defined headers from rule config (for authentication)
- Timeout: 5 seconds
- User-Agent: "LiveObjectAIClassifier/1.0"

**And** retry logic for failures:
- Failed requests (non-2xx status, timeout, network error) → Retry
- Retry attempts: 3 total (initial + 2 retries)
- Backoff: Exponential (1s, 2s, 4s delays)
- After 3 failures → Give up, log error
- Success: Any 2xx status code

**And** webhook logging:
- Log every webhook attempt in webhook_logs table
- Logged data: event_id, url, status_code, response_time_ms, retry_count, error_message, created_at
- Keep logs for 30 days (cleanup with event retention)
- View logs in UI: `/api/v1/webhooks/logs` endpoint

**And** security and validation:
- HTTPS required (reject http:// URLs in production)
- URL validation: Must be valid HTTP(S) URL
- No localhost/127.0.0.1 in production (prevent SSRF)
- Request signing: Optional HMAC signature in header (Phase 2)
- Rate limiting: Max 100 webhooks per minute per rule

**And** webhook testing:
- Test button in rule form sends sample payload
- Sample payload uses recent real event or mock data
- Displays: Status code, response body (first 200 chars), response time
- Success: Green checkmark, "Webhook test successful"
- Error: Red X, specific error message

**And** webhook logs UI (Settings or Rules page):
- Table: Timestamp, Rule, URL, Status, Response Time, Retries
- Filter: By rule, by success/failure, by date range
- Details modal: Click row to see full request/response
- Export: Download logs as CSV

**Prerequisites:** Story 5.1 (alert engine)

**Technical Notes:**
- Create service: `/backend/app/services/webhook_service.py`
- Use `httpx.AsyncClient` for HTTP requests
- Retry logic: Manual implementation or use `tenacity` library
- Logging: Store in webhook_logs table (created in Story 1.2)
- URL validation: Use Pydantic HttpUrl type
- SSRF prevention: Check URL against blocklist (localhost, private IPs)
- Async task: Webhook execution doesn't block rule engine
- Test endpoint: `POST /api/v1/webhooks/test` with url and payload

---

### Story 5.4: Build In-Dashboard Notification Center

**As a** user,
**I want** to see real-time notifications in the dashboard when rules trigger,
**So that** I'm immediately aware of important events.

**Acceptance Criteria:**

**Given** I have the dashboard open
**When** an alert rule triggers
**Then** I see a notification appear in real-time

**And** notification bell icon (header):
- Bell icon in top-right header
- Badge: Red circle with count (unread notifications)
- Count updates in real-time (WebSocket)
- Click → Open notifications dropdown

**And** notifications dropdown:
- Dropdown panel below bell icon
- Width: 400px (desktop), full-width (mobile)
- Max height: 500px, scrollable
- Header: "Notifications" + "Mark all as read" link
- List of notifications (most recent first, max 20 shown)
- Footer: "View all" link → Navigate to `/notifications` page (optional)

**And** notification item displays:
- Thumbnail: Small image (64x64px)
- Title: Rule name or auto-generated ("Person detected at Front Door")
- Description: Truncated event description (max 100 chars)
- Timestamp: Relative time ("5 minutes ago")
- Read/unread indicator: Blue dot for unread
- Click → Navigate to event detail, mark as read

**And** notification states:
- Unread: Blue dot + bold text
- Read: No dot + normal weight text
- Mark as read: Auto-mark when clicked, or explicit "Mark read" button
- Mark all as read: Button in dropdown header

**And** real-time delivery:
- WebSocket connection to backend (`ws://host/ws`)
- Backend broadcasts notification on rule trigger
- Frontend receives WebSocket message → Update notification list
- Sound notification (optional, user preference in settings)
- Desktop notification (browser API) if permission granted

**And** notification storage:
- Backend table: `notifications` (id, user_id, event_id, rule_id, read, created_at)
- Created when alert rule triggers with dashboard_notification action
- API endpoints:
  - `GET /api/v1/notifications` (list, filter by read/unread)
  - `PATCH /api/v1/notifications/:id/read` (mark as read)
  - `PATCH /api/v1/notifications/mark-all-read`
  - `DELETE /api/v1/notifications/:id`

**And** notification persistence:
- Stored in database (survive page refreshes)
- Retained for 30 days, then auto-deleted
- Accessible on multiple devices (multi-user Phase 2)

**And** WebSocket connection management:
- Auto-connect on dashboard load
- Reconnect on disconnect (exponential backoff)
- Heartbeat/ping to keep connection alive
- Close on logout or page unload

**Prerequisites:** Story 5.1 (alert engine), Story 3.3 (event pipeline)

**Technical Notes:**
- Create component: `/frontend/components/NotificationBell.tsx`, `/frontend/components/NotificationDropdown.tsx`
- WebSocket backend: FastAPI WebSocket endpoint `/ws`
- WebSocket frontend: Native WebSocket API or `socket.io-client`
- Notification storage: New database table (add in migration)
- Real-time state: React Context for notification state
- Sound: Use `Audio()` API with user permission
- Desktop notification: `Notification.requestPermission()` + `new Notification()`
- Badge count: Derived from unread count
- Dropdown: Headless UI `Popover` component

---

## Epic 6: Production Readiness & Security

**Goal:** Secure and operationalize the system for production deployment. Implement authentication, encryption, monitoring, and administrative tools to ensure the system is reliable and secure.

---

### Story 6.1: Implement API Key Encryption and Management

**As a** developer,
**I want** sensitive data (API keys, passwords) encrypted at rest,
**So that** the system is secure even if the database is compromised.

**Acceptance Criteria:**

**Given** users configure AI API keys or camera passwords
**When** the data is stored in the database
**Then** it is encrypted using strong encryption

**And** encryption implementation:
- Algorithm: Fernet (symmetric encryption from `cryptography` library)
- Key: 32-byte key derived from environment variable `ENCRYPTION_KEY`
- Key generation: `Fernet.generate_key()` on first setup
- Stored encrypted: API keys, camera passwords, webhook auth headers
- Decrypted: Only when needed for API calls, never logged

**And** key management:
- Encryption key stored in environment variable (never in code/database)
- Docker: Pass as environment variable or Docker secret
- Production: Use secrets management (AWS Secrets Manager, HashiCorp Vault - Phase 2)
- Key rotation: Planned for Phase 2 (re-encrypt all data with new key)

**And** encryption functions:
- `encrypt(plaintext: str) -> str`: Returns base64-encoded ciphertext
- `decrypt(ciphertext: str) -> str`: Returns original plaintext
- Utility module: `/backend/app/core/encryption.py`
- Used by: Camera service, AI service, Webhook service

**And** database storage:
- Camera passwords: Encrypted before INSERT/UPDATE
- AI API keys: Encrypted in system_settings
- Webhook headers: Encrypted in alert_rules conditions JSON
- Retrieved as encrypted, decrypted in memory when used

**And** API key validation endpoint:
- `POST /api/v1/ai/test-key` accepts key and model
- Encrypts key temporarily (not stored)
- Sends test request to AI API
- Returns validation result (success/failure)
- No key persistence unless user saves settings

**And** security best practices:
- Never log decrypted values (mask in logs: "key=****")
- Clear decrypted values from memory after use (del variable)
- No decrypted values in error messages or stack traces
- Encryption failures → Graceful error handling with user-friendly message

**And** setup and initialization:
- First run: Generate encryption key if not present
- Save to `.env` file or display to user for manual configuration
- Validation: Check encryption key is valid Fernet key on startup
- Error: Exit with clear message if key missing or invalid

**Prerequisites:** Story 1.2 (database schema)

**Technical Notes:**
- Library: `cryptography` package (`pip install cryptography`)
- Import: `from cryptography.fernet import Fernet`
- Key format: 44-byte base64-encoded string (32 bytes decoded)
- Environment: `ENCRYPTION_KEY=your-fernet-key-here` in `.env`
- Add to config: Load encryption key in `/backend/app/core/config.py`
- Migration: Add encryption to existing data (one-time script)
- Testing: Use test key in test environment, rotate for production

---

### Story 6.2: Add Comprehensive Logging and Monitoring

**As a** system administrator,
**I want** detailed logs and system metrics,
**So that** I can troubleshoot issues and monitor system health.

**Acceptance Criteria:**

**Given** the system is running
**When** operations occur
**Then** relevant events are logged with appropriate detail levels

**And** logging configuration:
- Structured logging: JSON format for machine parsing
- Log levels: DEBUG (development), INFO (production), WARNING, ERROR, CRITICAL
- Configurable via environment: `LOG_LEVEL=INFO`
- Log to: stdout (Docker/cloud) and file (`/backend/logs/app.log`)
- Rotation: Daily rotation, keep last 7 days, max 100MB per file

**And** log format (JSON):
```json
{
  "timestamp": "2025-11-16T15:30:00Z",
  "level": "INFO",
  "message": "Event created",
  "module": "event_service",
  "request_id": "uuid",
  "event_id": "uuid",
  "camera_id": "uuid",
  "processing_time_ms": 4500
}
```

**And** logged operations:
- Application startup/shutdown: Log version, config summary
- API requests: Request ID, method, path, status, response time
- Camera events: Connection/disconnection, frame capture rate
- Motion detection: Detection events, confidence, bounding box
- AI API calls: Model used, tokens, response time, cost
- Event creation: Event ID, camera, description length, confidence
- Alert rules: Rule evaluation, matched rules, actions executed
- Webhooks: URL, status code, retry count, response time
- Errors: Full stack traces, context data (request, user, etc.)

**And** sensitive data handling:
- Never log: Passwords, API keys, user emails (Phase 2)
- Mask sensitive fields: "password=****", "api_key=****"
- Sanitize user input in logs (prevent log injection)

**And** log retrieval API:
- `GET /api/v1/logs?level=ERROR&limit=100` (admin only)
- Query parameters: level, module, start_date, end_date, search
- Returns: Array of log entries (JSON)
- Download: `GET /api/v1/logs/download?date=2025-11-16` (returns log file)

**And** metrics and monitoring:
- Prometheus-compatible metrics endpoint: `GET /metrics`
- Metrics exposed:
  - Request count: Total HTTP requests (by endpoint, status)
  - Request latency: p50, p95, p99 (by endpoint)
  - Event processing: Events processed, processing time, queue depth
  - AI API: Calls made, errors, latency, cost estimate
  - Camera status: Connected/disconnected count
  - Database: Query count, query time, connection pool usage
  - System: CPU usage, memory usage, disk usage
- Update interval: Real-time counters, 1-minute gauges

**And** health monitoring dashboard (basic):
- Display in UI: System uptime, events processed today, error rate
- Health endpoint: `GET /api/v1/health` (already in Story 1.3)
- Status page: `/status` route showing all services (database, AI, cameras)

**And** error alerting (basic):
- Critical errors → Log to separate error.log file
- Email alerts on critical errors (configurable, Phase 2)
- Slack/Discord webhooks for errors (Phase 2)

**Prerequisites:** Story 1.3 (backend API structure)

**Technical Notes:**
- Logging library: Python `logging` with `json` formatter
- Structured logging: `python-json-logger` package
- Log rotation: `logging.handlers.RotatingFileHandler` or `RotatingFileHandler`
- Metrics: `prometheus_client` library for Prometheus metrics
- Middleware: Add request logging middleware to FastAPI
- Request ID: Generate UUID per request, add to all logs in context
- Performance: Logging shouldn't impact request latency (async writes)
- Log storage: Consider centralized logging (ELK stack, CloudWatch) for production

---

### Story 6.3: Implement Basic User Authentication (Phase 1.5)

**As a** user,
**I want** to log in with a username and password,
**So that** my camera system is protected from unauthorized access.

**Acceptance Criteria:**

**Given** the authentication system is enabled
**When** a user accesses the dashboard
**Then** they are redirected to login if not authenticated

**And** authentication implementation:
- Method: Username + password (email support Phase 2)
- Password hashing: bcrypt with cost factor 12
- Session management: JWT tokens
- Token storage: HTTP-only cookies (secure, SameSite)
- Token expiration: 24 hours (refresh token Phase 2)

**And** database schema (add migration):
- New table: `users` (id, username, password_hash, created_at, last_login)
- Username: Unique, 3-50 characters, alphanumeric + underscore
- Password hash: bcrypt hash string (60 chars)
- Default user: Created on first setup (username: admin, password: randomly generated)

**And** login endpoint:
- `POST /api/v1/auth/login`
- Request body: `{"username": "admin", "password": "password"}`
- Validation: Username exists, password matches hash
- Success: Return JWT token, set HTTP-only cookie, 200 OK
- Failure: Return 401 Unauthorized, "Invalid credentials"
- Rate limiting: Max 5 attempts per 15 minutes (prevent brute force)

**And** JWT token:
- Payload: `{"user_id": "uuid", "username": "admin", "exp": timestamp}`
- Signing: HS256 with secret key from environment (`JWT_SECRET_KEY`)
- Expiration: 24 hours from issuance
- Validate: Signature, expiration, user exists

**And** authentication middleware:
- Intercept all API requests (except /health, /login)
- Check for JWT in cookie or Authorization header
- Validate token: Signature, expiration, user active
- Add user context to request (request.state.user)
- Reject if invalid: 401 Unauthorized

**And** logout endpoint:
- `POST /api/v1/auth/logout`
- Clear JWT cookie (set max-age=0)
- Return 200 OK

**And** frontend login page:
- Route: `/login`
- Form: Username input, password input, "Login" button
- Validation: Required fields, username min length
- Submit: POST to `/api/v1/auth/login`
- Success: Store token (if using localStorage), redirect to `/`
- Error: Show error message "Invalid username or password"
- Remember me: Optional checkbox (Phase 2, extends token expiration)

**And** protected routes:
- All dashboard routes require authentication
- Redirect to `/login` if not authenticated
- After login: Redirect back to originally requested page
- Logout button in user menu (header dropdown)

**And** password management:
- Change password: `POST /api/v1/auth/change-password` (requires current password)
- Password requirements: 8+ characters, 1 uppercase, 1 number, 1 special char
- First login: Prompt to change default password (Phase 2)
- Reset password: Email-based reset (Phase 2)

**Prerequisites:** Story 1.3 (backend API), Story 4.1 (dashboard layout)

**Technical Notes:**
- Bcrypt: `bcrypt` Python library (`pip install bcrypt`)
- JWT: `python-jose` library (`pip install python-jose[cryptography]`)
- Middleware: FastAPI dependency injection for auth
- Frontend: Context for auth state, ProtectedRoute component
- Cookie: Set with `httponly=True`, `secure=True` (production), `samesite='lax'`
- Rate limiting: `slowapi` library or Redis-based limiter
- Default user setup: Script to create admin user on first run

---

### Story 6.4: Add System Backup and Restore Functionality

**As a** system administrator,
**I want** to backup and restore all system data,
**So that** I can recover from failures or migrate to a new server.

**Acceptance Criteria:**

**Given** I want to backup my system
**When** I trigger a backup
**Then** all data is exported to a downloadable archive

**And** backup includes:
- Database: Full SQLite database file (app.db)
- Thumbnails: All event thumbnail images (if file storage mode)
- Configuration: Environment variables and system settings
- Metadata: Backup timestamp, version, system info

**And** backup creation:
- Manual trigger: Button in Settings page → "Backup Now"
- API endpoint: `POST /api/v1/system/backup`
- Process:
  1. Create temp directory: `/backend/data/backups/backup-{timestamp}/`
  2. Copy database file: `app.db` → `backup-{timestamp}/database.db`
  3. Copy thumbnails: Recursive copy of `/backend/data/thumbnails/` → `backup-{timestamp}/thumbnails/`
  4. Export settings: JSON file with system_settings table → `backup-{timestamp}/settings.json`
  5. Create metadata: `backup-{timestamp}/metadata.json` (timestamp, version, file counts)
  6. Archive: Create ZIP file `backup-{timestamp}.zip`
  7. Cleanup: Delete temp directory
  8. Return download link: `/api/v1/system/backup/{timestamp}/download`

**And** backup download:
- `GET /api/v1/system/backup/{timestamp}/download`
- Streaming response: ZIP file
- Filename: `liveobject-backup-YYYY-MM-DD-HH-MM-SS.zip`
- Content-Disposition: attachment (triggers download)
- Cleanup: Delete backup ZIP after 1 hour

**And** restore functionality:
- Manual upload: Settings page → "Restore from Backup" → File upload
- API endpoint: `POST /api/v1/system/restore` (multipart/form-data)
- Process:
  1. Validate ZIP structure (check for required files)
  2. Stop all background tasks (camera capture, event processing)
  3. Backup current database (before overwrite)
  4. Extract ZIP to temp directory
  5. Replace database: `database.db` → `app.db`
  6. Replace thumbnails: Clear existing, copy from backup
  7. Import settings: Update system_settings from `settings.json`
  8. Restart background tasks
  9. Return success message

**And** restore validation:
- Check ZIP file integrity (not corrupted)
- Verify metadata (version compatibility)
- Confirm database schema matches current version
- Warn if restore will overwrite existing data
- Require confirmation: "Restore will replace all data. Continue?"

**And** automatic backups (optional):
- Scheduled: Daily at 3:00 AM
- Keep last N backups (default: 7)
- Auto-cleanup: Delete backups older than retention period
- Stored locally: `/backend/data/backups/` directory
- Configurable in settings: Enable/disable, time, retention

**And** UI components:
- Settings page: Backup & Restore section
- "Backup Now" button: Triggers immediate backup + download
- "Restore from Backup": File upload input + restore button
- Backup history: List of available backups (if automatic enabled)
- Download backup: Click to download previous backup
- Confirmation modals: "Restore will replace all data. Continue?"

**And** error handling:
- Insufficient disk space → Error message "Not enough disk space"
- Corrupted ZIP → Error "Backup file is corrupted"
- Version mismatch → Warning "Backup from older version, may have issues"
- Database locked → Error "Cannot backup while database is in use"

**Prerequisites:** Story 1.2 (database schema), Story 3.2 (event storage)

**Technical Notes:**
- ZIP creation: Python `zipfile` module
- File operations: `shutil` for copy/move operations
- Streaming: FastAPI `StreamingResponse` for large files
- Backup service: `/backend/app/services/backup_service.py`
- Scheduler: APScheduler for automatic backups (if enabled)
- Validation: Check ZIP CRC, verify file list matches expected structure
- Database copy: Use `VACUUM INTO` for SQLite or simple file copy (ensure not in use)
- Frontend: File upload with progress bar (optional)

---

## FR Coverage Matrix

This matrix validates that ALL functional requirements from the PRD are covered by epics and stories:

| FR ID | Requirement | Epic | Stories |
|-------|-------------|------|---------|
| F1.1 | RTSP Camera Support | Epic 2 | 2.1, 2.3 |
| F1.2 | Camera Configuration UI | Epic 2 | 2.3, 2.5 |
| F1.3 | Webcam/USB Camera Support | Epic 2 | 2.2, 2.3 |
| F2.1 | Motion Detection Algorithm | Epic 2 | 2.4 |
| F2.2 | Motion Detection Zones | Epic 2 | 2.4 (basic implementation) |
| F2.3 | Detection Schedule | Epic 2 | 2.4 (configurable cooldown) |
| F3.1 | Natural Language Processing | Epic 3 | 3.1 |
| F3.2 | Image Capture & Processing | Epic 3 | 3.1, 3.3 |
| F3.3 | AI Model Selection & Fallback | Epic 3 | 3.1, Epic 4: 4.4 |
| F3.4 | Description Enhancement Prompt | Epic 3 | 3.1, Epic 4: 4.4 |
| F4.1 | Event Data Structure | Epic 1 | 1.2, Epic 3: 3.2 |
| F4.2 | Event Retrieval API | Epic 3 | 3.2 |
| F4.3 | Data Retention Policy | Epic 3 | 3.4, Epic 4: 4.4 |
| F4.4 | Event Search | Epic 3 | 3.2, Epic 4: 4.2 |
| F5.1 | Basic Alert Rules | Epic 5 | 5.1, 5.2 |
| F5.2 | Alert Rule Configuration UI | Epic 5 | 5.2 |
| F5.3 | Advanced Rule Logic | Epic 5 | 5.1 (AND logic) |
| F5.4 | Alert Cooldown | Epic 5 | 5.1 |
| F6.1 | Event Timeline View | Epic 4 | 4.2 |
| F6.2 | Live Camera View | Epic 4 | 4.3 |
| F6.3 | System Settings Page | Epic 4 | 4.4 |
| F6.4 | Manual Analysis Trigger | Epic 4 | 4.3 |
| F6.5 | Dashboard Statistics | Epic 3 | 3.2 (stats endpoint) |
| F6.6 | Notification Center | Epic 5 | 5.4 |
| F7.1 | User Authentication | Epic 6 | 6.3 (Phase 1.5) |
| F7.2 | API Key Management | Epic 6 | 6.1, Epic 4: 4.4 |
| F7.3 | HTTPS/TLS Support | Epic 6 | 6.3 (infrastructure) |
| F7.4 | Rate Limiting | Epic 6 | 6.3 (login rate limiting) |
| F8.1 | Health Check Endpoint | Epic 1 | 1.3 |
| F8.2 | Logging & Debugging | Epic 6 | 6.2 |
| F8.3 | Backup & Restore | Epic 6 | 6.4 |
| F9.1 | Webhook Configuration | Epic 5 | 5.1, 5.3 |
| F9.2 | Webhook Testing | Epic 5 | 5.3 |
| F9.3 | Webhook Logs | Epic 5 | 5.3 |

**Coverage Summary:**
- ✅ ALL 34 functional requirements covered
- ✅ Epic 1 (Foundation): 3 stories - Enables all subsequent work
- ✅ Epic 2 (Camera Integration): 5 stories - Covers F1.x and F2.x
- ✅ Epic 3 (AI Intelligence): 4 stories - Covers F3.x and F4.x
- ✅ Epic 4 (Dashboard): 4 stories - Covers F6.x
- ✅ Epic 5 (Alerts & Automation): 4 stories - Covers F5.x and F9.x
- ✅ Epic 6 (Production Readiness): 4 stories - Covers F7.x and F8.x

---

## Summary

### Epic Breakdown Complete (Initial Version)

**Created:** epics.md with 6 epics and 24 detailed stories

**Total Story Count:**
- Epic 1: 3 stories (Foundation)
- Epic 2: 5 stories (Cameras & Motion)
- Epic 3: 4 stories (AI & Events)
- Epic 4: 4 stories (Dashboard)
- Epic 5: 4 stories (Alerts)
- Epic 6: 4 stories (Security)
- **Total: 24 stories**

**FR Coverage:** All 34 functional requirements from PRD mapped to stories (see coverage matrix above)

**Story Quality:**
- ✅ All stories follow BDD format (Given/When/Then)
- ✅ Detailed acceptance criteria with specific measurements
- ✅ Implementation details added (UI specifics, performance targets, technical notes)
- ✅ Vertically sliced (complete functionality per story)
- ✅ Sequential ordering (no forward dependencies)
- ✅ Sized for single-session completion

**Next Steps in BMad Method:**

1. **UX Design** (if UI exists) - Run: `/bmad:bmm:workflows:create-ux-design`
   → Will add interaction details to stories in epics.md
   → Update acceptance criteria with UX mockup references, flow details
   → Add responsive breakpoints and visual design decisions

2. **Architecture** - Run: `/bmad:bmm:workflows:architecture`
   → Will add technical details to stories in epics.md
   → Update technical notes with architecture decisions
   → Add references to data models, API contracts, deployment patterns

3. **Phase 4 Implementation** - Stories ready for context assembly
   → Each story pulls context from: PRD (why) + epics.md (what/how) + UX (interactions) + Architecture (technical)
   → Use `/bmad:bmm:workflows:create-story` to generate implementation plans
   → Use `/bmad:bmm:workflows:dev-story` to execute stories

**Important:** This is a living document that will be updated as you progress through the workflow chain. The epics.md file will evolve with UX and Architecture inputs before implementation begins.

---

_For implementation: Use the `create-story` workflow to generate individual story implementation plans from this epic breakdown._

_This document will be updated after UX Design and Architecture workflows to incorporate interaction details and technical decisions._

