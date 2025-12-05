# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Live Object AI Classifier is an AI-powered event detection system for home security. It analyzes video feeds from UniFi Protect cameras, RTSP IP cameras, and USB webcams, detects motion and smart events, and generates natural language descriptions using multi-provider AI (OpenAI, xAI Grok, Anthropic Claude, Google Gemini).

## Tech Stack

- **Backend**: FastAPI 0.115 + SQLAlchemy 2.0 + Alembic (Python 3.11+)
- **Frontend**: Next.js 15 (App Router) + React 19 + TanStack Query + Tailwind CSS 4 + shadcn/ui
- **AI Providers**: OpenAI GPT-4o mini → xAI Grok 2 Vision → Anthropic Claude 3 Haiku → Google Gemini Flash (fallback order)
- **Video**: OpenCV 4.12 + PyAV 12 (for secure RTSP)
- **UniFi Integration**: uiprotect library for native Protect WebSocket events
- **Database**: SQLite (default) or PostgreSQL

## Build & Test Commands

### Backend
```bash
cd backend
source venv/bin/activate         # Activate virtualenv
uvicorn main:app --reload        # Run dev server (localhost:8000)
pytest tests/ -v                 # Run all tests
pytest tests/test_services/test_camera_service.py -v  # Single test file
pytest tests/ --cov=app --cov-report=html  # Coverage report
alembic upgrade head             # Apply migrations
alembic downgrade -1             # Rollback one migration
```

### Frontend
```bash
cd frontend
npm run dev      # Dev server (localhost:3000)
npm run build    # Production build
npm run lint     # ESLint
```

## Architecture

### Event Processing Pipeline
```
Camera Capture → Motion Detection → Event Queue → AI Description → Database → Alert Rules → Webhooks/Notifications → WebSocket
(background)     (per frame)       (asyncio)     (multi-provider)             (eval + retry)                        (broadcast)
```

### Key Services (backend/app/services/)
- `camera_service.py` - RTSP/USB capture with background threading, auto-reconnect
- `protect_service.py` - UniFi Protect controller connection, WebSocket management, camera discovery
- `protect_event_handler.py` - Protect event parsing, smart detection filtering, snapshot retrieval
- `motion_detection_service.py` - MOG2/KNN/frame-diff algorithms, detection zones
- `event_processor.py` - Async queue pipeline, <5s p95 latency target, event correlation
- `ai_service.py` - Multi-provider fallback (OpenAI, xAI Grok, Claude, Gemini), image preprocessing
- `alert_engine.py` - Rule evaluation, webhook dispatch with retry
- `snapshot_service.py` - Snapshot retrieval from Protect cameras

### API Routes
All routes prefixed with `/api/v1`. Main routers in `backend/app/api/v1/`:
- `cameras.py` - Camera CRUD, test/start/stop, live preview
- `protect.py` - Protect controller CRUD, connection test, camera discovery, enable/disable
- `events.py` - Event list/detail, search, export, stats, correlated events
- `ai.py` - AI providers, describe endpoint
- `alert_rules.py` - Alert rule management
- `system.py` - Settings, storage, health, retention

### Phase 2 API Endpoints (Protect Integration)
```
POST   /api/v1/protect/controllers          # Create controller
GET    /api/v1/protect/controllers          # List controllers
GET    /api/v1/protect/controllers/{id}     # Get controller
PUT    /api/v1/protect/controllers/{id}     # Update controller
DELETE /api/v1/protect/controllers/{id}     # Delete controller
POST   /api/v1/protect/controllers/test     # Test connection (no persistence)
GET    /api/v1/protect/controllers/{id}/cameras           # Discover cameras
PUT    /api/v1/protect/controllers/{id}/cameras/{cam}/enable   # Enable for AI
PUT    /api/v1/protect/controllers/{id}/cameras/{cam}/disable  # Disable for AI
PUT    /api/v1/protect/controllers/{id}/cameras/{cam}/filters  # Set event filters
```

### Frontend Structure
- Pages: `frontend/app/` (App Router)
- Components: `frontend/components/` (cameras/, events/, dashboard/, rules/, settings/, ui/)
- State: React Context (Auth, Notifications, Settings) + TanStack Query (server state)
- API Client: `frontend/lib/api-client.ts` (typed, ~19KB)

## Database Models (backend/app/models/)
- `Camera` - RTSP/USB/Protect config with encrypted passwords, source_type field
- `ProtectController` - UniFi Protect controller credentials and connection state
- `Event` - Detected events with AI descriptions, thumbnails, and correlation
  - `source_type` - 'rtsp', 'usb', or 'protect'
  - `protect_event_id` - Native Protect event ID
  - `smart_detection_type` - person, vehicle, package, animal, ring
  - `is_doorbell_ring` - Flag for doorbell ring events
  - `correlation_group_id` - Links events from same time window
  - `description_retry_needed` - Flag for AI retry on failure
- `MotionEvent` - Low-level motion detections
- `AlertRule` - Rule definitions with object matching
- `Notification` - User notifications
- `AIUsage` - Provider usage tracking

## Environment Variables

### Backend (.env)
```
DATABASE_URL=sqlite:///./data/app.db
ENCRYPTION_KEY=<fernet-key>  # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
DEBUG=True
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:3000,http://localhost:8000
MAX_CAMERAS=1  # MVP limitation
```

### Frontend (.env.local)
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## BMAD Workflows

This project uses the BMAD Method. Slash commands available:
- `/bmad:bmm:workflows:dev-story` - Execute story implementation
- `/bmad:bmm:workflows:create-story` - Create next story from epics
- `/bmad:bmm:workflows:story-context` - Assemble story context
- `/bmad:bmm:agents:dev` - Activate dev agent

## Key Patterns

- **Backend**: Service layer in `/app/services/`, FastAPI dependency injection, async/await for I/O
- **Frontend**: Hooks in `hooks/`, Zod validation with React Hook Form, shadcn/ui components
- **Security**: Fernet encryption for API keys/passwords (never logged), CORS configured
- **Logging**: Structured JSON via python-json-logger, Prometheus metrics at `/metrics`

## Current Limitations
- Minimal frontend auth (stub)
- No SSL/HTTPS configuration
- Descriptions only, not video archival

## Phase 2 Architecture (UniFi Protect)

### Protect Event Flow
```
Protect Controller → WebSocket → ProtectService → ProtectEventHandler → SnapshotService → AIService → Event DB
                                  (uiprotect)      (filter/dedupe)       (get image)       (describe)
```

### Camera Sources Coexistence
All three camera types can coexist:
- **Protect**: Real-time events via WebSocket, smart detection types
- **RTSP**: Polling-based frame capture, motion detection
- **USB**: Direct capture, motion detection

Events from all sources appear in unified timeline with `source_type` filtering.
