# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Always use context7 when I need code generation, setup or configuration steps, or library/API documentation. This means you should automatically use the Context7 MCP tools to resolve library id and get library docs without me having to explicitly ask.

## Project Overview

ArgusAI is an AI-powered event detection system for home security. It analyzes video feeds from UniFi Protect cameras, RTSP IP cameras, and USB webcams, detects motion and smart events, and generates natural language descriptions using multi-provider AI (OpenAI, xAI Grok, Anthropic Claude, Google Gemini).

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

## Production Server Access

Claude Code has SSH access to the production server for troubleshooting and deployment:

```bash
ssh root@argusai.bengtson.local
```

### Server Details
- **Host**: `argusai.bengtson.local` (10.0.1.46)
- **Application Path**: `/ArgusAI`
- **Backend venv**: `/ArgusAI/backend/venv`
- **Frontend**: HTTPS on port 3000 (custom SSL server)
- **Backend**: HTTP on port 8000 (proxied by frontend)

### Common Server Commands
```bash
# Deploy latest changes
cd /ArgusAI && git pull && sudo systemctl restart argusai-backend

# Restart services
sudo systemctl restart argusai-backend
sudo systemctl restart argusai-frontend

# View logs
sudo journalctl -u argusai-backend -f
sudo journalctl -u argusai-frontend -f

# Run Python commands in backend context
cd /ArgusAI/backend && source venv/bin/activate && python3 -c "..."

# Test API endpoints
curl -s http://127.0.0.1:8000/api/v1/cameras
curl -s -H "X-API-Key: <key>" http://127.0.0.1:8000/api/v1/events?limit=5
```

### Service Configuration
- Backend service: `/etc/systemd/system/argusai-backend.service`
- Frontend service: `/etc/systemd/system/argusai-frontend.service`
- Frontend env: `/ArgusAI/frontend/.env.local`
- SSL certs: `/ArgusAI/backend/data/certs/`

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
POST   /api/v1/protect/controllers/{id}/cameras/{cam}/enable   # Enable for AI
POST   /api/v1/protect/controllers/{id}/cameras/{cam}/disable  # Disable for AI
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

# SSL Configuration (Story P9-5.1)
SSL_ENABLED=false  # Enable HTTPS
SSL_CERT_FILE=data/certs/cert.pem  # Path to certificate
SSL_KEY_FILE=data/certs/key.pem  # Path to private key
SSL_REDIRECT_HTTP=true  # Redirect HTTP to HTTPS
SSL_MIN_VERSION=TLSv1_2  # TLSv1_2 or TLSv1_3
SSL_PORT=443  # HTTPS port
```

### Frontend (.env.local)
```
NEXT_PUBLIC_API_URL=http://localhost:8000  # Use https:// when SSL is enabled
```

## SSL/HTTPS Configuration (Story P9-5.1)

ArgusAI supports SSL/HTTPS for secure connections. SSL is required for push notifications.

### Quick Setup
1. Place certificates in `data/certs/` directory
2. Set environment variables:
   ```
   SSL_ENABLED=true
   SSL_CERT_FILE=data/certs/cert.pem
   SSL_KEY_FILE=data/certs/key.pem
   ```
3. Restart the backend

### SSL Status Endpoint
- `GET /api/v1/system/ssl-status` - Returns SSL configuration and certificate info

### Generating Self-Signed Certificates (Development)
```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout data/certs/key.pem \
  -out data/certs/cert.pem \
  -subj "/CN=localhost"
```

### Push Notifications and HTTPS
Push notifications require HTTPS to work. Check requirements:
- `GET /api/v1/push/requirements` - Returns HTTPS status and warnings

## BMAD Workflows

This project uses the BMAD Method. Slash commands available:
- `/bmad:bmm:workflows:dev-story` - Execute story implementation
- `/bmad:bmm:workflows:create-story` - Create next story from epics
- `/bmad:bmm:workflows:story-context` - Assemble story context
- `/bmad:bmm:workflows:yolo` - Creates story, context and executes implementation
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

## Phase 3 Architecture (Video Analysis)

### Analysis Modes
- **single_frame**: Legacy snapshot-based analysis (fastest, lowest cost)
- **multi_frame**: Extract 3-5 key frames from video clips (balanced)
- **video_native**: Send full video to AI providers that support it (highest quality)

### Video Processing Pipeline
```
Protect Event → Clip Download → Frame Extraction → AI Analysis → Description
                (uiprotect)     (PyAV/OpenCV)      (multi-image)
```

### Key Phase 3 Services
- `video_clip_service.py` - Download motion clips from Protect
- `frame_extraction_service.py` - Extract key frames from video
- `cost_tracking_service.py` - Track AI usage and costs per provider

## Phase 4 Roadmap (Planned)

Phase 4 adds intelligent context awareness and smart home integration:

### Planned Features
- **Push Notifications**: Web Push with thumbnails, PWA support
- **Home Assistant**: MQTT integration with auto-discovery
- **Temporal Context**: Recognize recurring visitors, pattern detection
- **Activity Summaries**: Daily digests and natural language reports
- **User Feedback**: Thumbs up/down to improve AI accuracy

### Phase 4 Documentation
- PRD: `docs/PRD-phase4.md`
- Epics: `docs/epics-phase4.md`
- Architecture: `docs/architecture.md` (Phase 4 Additions section)

### Phase 4 Key APIs (Planned)
```
GET  /api/v1/context/similar/{event_id}   # Find similar past events
GET  /api/v1/entities                      # List recognized people/vehicles
POST /api/v1/push/subscribe                # Register for push notifications
GET  /api/v1/summaries/daily               # Get daily activity digest
POST /api/v1/events/{id}/feedback          # Submit feedback on description
GET  /api/v1/integrations/mqtt/status      # MQTT connection status
```

## AI Agent UI Testing (Playwright MCP)

Claude Code has browser automation capabilities via the Playwright MCP server for full E2E UI testing.

### Access URL
- **Cloudflare Tunnel**: `https://agent.argusai.cc` (valid SSL certificate)
- Local access requires SSL cert bypass which Docker containers don't support

### Available Tools

| Tool | Purpose |
|------|---------|
| `browser_navigate` | Navigate to a URL |
| `browser_snapshot` | Get accessibility tree (best for AI interaction) |
| `browser_take_screenshot` | Capture visual screenshot |
| `browser_click` | Click elements by ref |
| `browser_type` | Type into input fields |
| `browser_fill_form` | Fill multiple form fields at once |
| `browser_wait_for` | Wait for text/element/time |
| `browser_evaluate` | Execute JavaScript on page |
| `browser_press_key` | Press keyboard keys |
| `browser_select_option` | Select dropdown options |

### Usage Examples

```
# Navigate to the app
browser_navigate: {"url": "https://agent.argusai.cc"}

# Get page state for AI interaction
browser_snapshot: {}

# Take a screenshot
browser_take_screenshot: {"filename": "test-result.png"}

# Fill login form (refs come from snapshot)
browser_fill_form: {"fields": [
  {"name": "Username", "type": "textbox", "ref": "e19", "value": "admin"},
  {"name": "Password", "type": "textbox", "ref": "e23", "value": "password"}
]}

# Click a button
browser_click: {"element": "Sign in button", "ref": "e28"}
```

### Testing Workflow

1. Navigate to page with `browser_navigate`
2. Get accessibility tree with `browser_snapshot` (returns element refs)
3. Interact using refs from snapshot (`browser_click`, `browser_type`, `browser_fill_form`)
4. Verify results with `browser_snapshot` or `browser_take_screenshot`
5. Repeat for multi-step flows

### Capabilities

- Full E2E test scenarios
- Form filling and submission
- Navigation through multi-step workflows
- Visual regression testing via screenshots
- Console log and network request inspection
- JavaScript execution for complex interactions
