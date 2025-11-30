# Architecture Document
## Live Object AI Classifier - MVP + Phase 2

**Version:** 1.1
**Date:** 2025-11-30
**Author:** BMad Architect Agent
**For:** Brent

> **Phase 2 Update:** This document now includes architectural additions for UniFi Protect native integration and xAI Grok AI provider. See [Phase 2 Additions](#phase-2-additions) section.

---

## Executive Summary

The Live Object AI Classifier uses an **event-driven architecture** that processes camera feeds through motion detection, generates natural language descriptions via AI models, and delivers real-time notifications to a web dashboard. The system prioritizes simplicity and privacy by storing semantic descriptions rather than video footage, making it suitable for security, accessibility, and home automation use cases.

**Key Architectural Principles:**
1. **Description-First:** Store event descriptions, not video (privacy + storage efficiency)
2. **Event-Driven:** Asynchronous processing triggered by motion detection
3. **Multi-Provider AI:** Support multiple AI models with automatic fallback
4. **Real-Time Updates:** WebSocket notifications for live event feed
5. **Zero-Config Database:** SQLite for plug-and-play deployment
6. **Single Camera MVP:** Designed to scale to multi-camera in Phase 2

---

## Project Initialization

**First implementation story should execute:**

### Frontend Setup
```bash
npx create-next-app@latest frontend \
  --typescript \
  --tailwind \
  --eslint \
  --app \
  --no-src-dir \
  --import-alias "@/*"

cd frontend
npm install lucide-react date-fns
npx shadcn-ui@latest init
```

### Backend Setup
```bash
mkdir backend && cd backend
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

pip install "fastapi[standard]" \
  opencv-python \
  sqlalchemy \
  alembic \
  python-jose[cryptography] \
  passlib[bcrypt] \
  python-multipart \
  openai \
  google-generativeai \
  anthropic \
  cryptography \
  httpx

# Initialize Alembic for migrations
alembic init alembic
```

**This establishes the base architecture with:**
- TypeScript, Tailwind CSS, ESLint (frontend)
- FastAPI, SQLAlchemy, OpenCV (backend)
- Async I/O support throughout
- Type safety on both sides

---

## Decision Summary

| Category | Decision | Version/Details | Affects | Rationale |
|----------|----------|----------------|---------|-----------|
| **Frontend Framework** | Next.js | 15.x with App Router | All UI features | React Server Components, built-in optimization, excellent DX |
| **Frontend Language** | TypeScript | 5.x | All frontend code | Type safety, better tooling, catches errors early |
| **Frontend Styling** | Tailwind CSS + shadcn/ui | 3.x / latest | All UI components | Rapid development, mobile-responsive, professional components |
| **Backend Framework** | FastAPI | 0.115+ | All API endpoints | Async support, automatic docs, WebSocket support, excellent performance |
| **Backend Language** | Python | 3.11+ | All backend code | Ecosystem for CV/AI, async/await support, team familiarity |
| **Database** | SQLite | 3.x | Event storage, settings | Zero-config, sufficient for MVP scale, easy backup |
| **ORM** | SQLAlchemy | 2.0+ with async | Database access | Type-safe queries, migrations support, async operations |
| **Camera Library** | OpenCV | 4.8+ | Camera capture, motion | Industry standard, RTSP support, cross-platform |
| **Motion Detection** | OpenCV MOG2 | Built-in | F2 (Motion Detection) | Background subtraction, adaptive, proven algorithm |
| **AI Primary** | OpenAI GPT-4o-mini | Latest API | F3 (AI Descriptions) | Best cost/performance, reliable API, good descriptions |
| **AI Fallback** | Google Gemini Flash | Latest API | F3 (AI Descriptions) | Free tier available, good quality, automatic fallback |
| **AI Tertiary** | Anthropic Claude Haiku | Latest API | F3 (AI Descriptions) | Additional fallback option, excellent quality |
| **Authentication** | JWT + HTTP-only cookies | python-jose | F7 (Auth) | Stateless, secure, XSS protection |
| **Password Hashing** | bcrypt | via passlib | F7 (Auth) | Industry standard, secure, slow by design |
| **API Key Encryption** | Fernet (symmetric) | cryptography lib | F7.2 | Secure storage of AI API keys |
| **WebSocket** | FastAPI/Starlette | Built-in | F6.6 (Real-time) | Native support, no additional services needed |
| **Background Tasks** | FastAPI BackgroundTasks | Built-in | F3 (AI processing) | Simple async tasks, no external queue needed for MVP |
| **State Management** | React Context | Built-in | Frontend global state | Sufficient for MVP, no Redux complexity |
| **Icons** | lucide-react | Latest | All UI icons | Consistent, lightweight, good selection |
| **Date Formatting** | date-fns | Latest | All date displays | Lightweight, immutable, locale support |

---

## Technology Stack Details

### Core Technologies

**Frontend Stack:**
- **Framework:** Next.js 15.x (App Router, React Server Components)
- **Language:** TypeScript 5.x (strict mode enabled)
- **Styling:** Tailwind CSS 3.x + shadcn/ui components
- **HTTP Client:** Built-in `fetch` with Next.js extensions
- **WebSocket:** Native browser WebSocket API
- **Form Handling:** React Hook Form + Zod validation
- **State:** React Context for global state, Server Components for data fetching
- **Icons:** lucide-react
- **Date/Time:** date-fns
- **Build Tool:** Turbopack (default in Next.js 15)

**Backend Stack:**
- **Framework:** FastAPI 0.115+ (ASGI)
- **Language:** Python 3.11+
- **Server:** Uvicorn (included with fastapi[standard])
- **Database:** SQLite 3.x (file-based: `backend/data/app.db`)
- **ORM:** SQLAlchemy 2.0+ (async engine)
- **Migrations:** Alembic
- **Camera/CV:** opencv-python 4.8+
- **AI SDKs:** openai, google-generativeai, anthropic
- **Auth:** python-jose (JWT), passlib (bcrypt)
- **Encryption:** cryptography (Fernet)
- **HTTP Client:** httpx (async)
- **WebSocket:** Built into FastAPI/Starlette

**Development Tools:**
- **Linting:** ESLint (frontend), Ruff (backend)
- **Formatting:** Prettier (frontend), Black (backend)
- **Testing:** Jest + React Testing Library (frontend), pytest (backend)
- **API Docs:** Auto-generated by FastAPI (Swagger UI + ReDoc)

### Integration Points

**Frontend ↔ Backend:**
- **REST API:** HTTP calls to `http://localhost:8000/api/v1/*`
- **WebSocket:** Persistent connection to `ws://localhost:8000/ws`
- **CORS:** Backend configured to allow frontend origin
- **Proxy:** Next.js API routes can proxy to backend (optional, for production)

**Backend ↔ Camera:**
- **Protocol:** RTSP for IP cameras, DirectShow/V4L2 for USB
- **Library:** OpenCV VideoCapture
- **Threading:** Separate thread per camera for frame capture
- **Frame Rate:** Configurable (default 5 FPS) to balance performance

**Backend ↔ AI Services:**
- **Protocol:** HTTPS REST APIs
- **Models:** OpenAI, Google Gemini, Anthropic Claude
- **Fallback:** Automatic retry with next provider if primary fails
- **Rate Limiting:** Respect free-tier limits, queue if necessary

**Backend ↔ Database:**
- **Connection:** SQLAlchemy async engine
- **Pooling:** Default SQLite connection pool
- **Transactions:** Automatic per-request transaction handling
- **Migrations:** Alembic for schema versioning

**Backend ↔ Webhook Targets:**
- **Protocol:** HTTPS POST (HTTP allowed but warned)
- **Retry:** 3 attempts with exponential backoff (1s, 2s, 4s)
- **Timeout:** 5 seconds per attempt
- **Headers:** Custom headers supported for auth

---

## Complete Project Structure

```
live-object-ai-classifier/
├── backend/
│   ├── main.py                          # FastAPI app entry point, server startup
│   ├── requirements.txt                 # Python dependencies with pinned versions
│   ├── .env.example                     # Environment variables template
│   ├── .env                             # Actual env vars (gitignored)
│   ├── alembic.ini                      # Alembic configuration
│   ├── alembic/                         # Database migrations
│   │   ├── versions/                    # Migration version scripts
│   │   │   └── 001_initial_schema.py
│   │   └── env.py                       # Alembic environment config
│   ├── app/
│   │   ├── __init__.py
│   │   ├── api/                         # API route handlers
│   │   │   ├── __init__.py
│   │   │   └── v1/                      # API version 1
│   │   │       ├── __init__.py
│   │   │       ├── cameras.py          # GET/POST/PUT/DELETE /api/v1/cameras
│   │   │       ├── events.py           # GET /api/v1/events, GET /api/v1/events/{id}
│   │   │       ├── alert_rules.py      # CRUD for /api/v1/alert-rules
│   │   │       ├── settings.py         # GET/PUT /api/v1/settings
│   │   │       ├── health.py           # GET /api/health (no auth)
│   │   │       ├── auth.py             # POST /api/v1/login, /logout (Phase 1.5)
│   │   │       └── websocket.py        # WebSocket endpoint /ws
│   │   ├── core/                        # Core system modules
│   │   │   ├── __init__.py
│   │   │   ├── config.py               # Pydantic Settings for env vars
│   │   │   ├── security.py             # JWT auth, password hashing, API key encryption
│   │   │   ├── database.py             # SQLAlchemy engine, session management
│   │   │   └── logging.py              # Structured logging configuration
│   │   ├── models/                      # SQLAlchemy ORM models
│   │   │   ├── __init__.py
│   │   │   ├── camera.py               # Camera model (id, name, rtsp_url, etc.)
│   │   │   ├── event.py                # Event model (id, timestamp, description, etc.)
│   │   │   ├── alert_rule.py           # AlertRule model (conditions, actions)
│   │   │   ├── user.py                 # User model (Phase 1.5)
│   │   │   └── system_setting.py       # SystemSetting model (key-value config)
│   │   ├── schemas/                     # Pydantic request/response schemas
│   │   │   ├── __init__.py
│   │   │   ├── camera.py               # CameraCreate, CameraUpdate, CameraResponse
│   │   │   ├── event.py                # EventResponse, EventList, EventFilters
│   │   │   ├── alert_rule.py           # AlertRuleCreate, AlertRuleUpdate
│   │   │   └── user.py                 # UserLogin, UserResponse (Phase 1.5)
│   │   ├── services/                    # Business logic layer
│   │   │   ├── __init__.py
│   │   │   ├── camera_service.py       # Camera capture thread, RTSP handling, reconnect logic
│   │   │   ├── motion_detection.py     # OpenCV background subtraction, zone filtering
│   │   │   ├── ai_service.py           # Multi-provider AI calls (OpenAI, Gemini, Claude)
│   │   │   ├── event_processor.py      # Event pipeline: capture→AI→store→alert
│   │   │   ├── alert_service.py        # Evaluate rules, trigger actions, cooldown tracking
│   │   │   ├── webhook_service.py      # HTTP POST with retry, timeout handling
│   │   │   └── websocket_manager.py    # WebSocket connection pool, broadcast messages
│   │   └── utils/                       # Utility modules
│   │       ├── __init__.py
│   │       ├── image_processing.py     # Resize, compress, thumbnail generation
│   │       ├── encryption.py           # Fernet encrypt/decrypt for API keys
│   │       └── validators.py           # Custom Pydantic validators
│   ├── tests/                           # Pytest test suite
│   │   ├── __init__.py
│   │   ├── conftest.py                 # Pytest fixtures
│   │   ├── test_api/                   # API endpoint tests
│   │   │   ├── test_cameras.py
│   │   │   ├── test_events.py
│   │   │   └── test_alert_rules.py
│   │   └── test_services/              # Service layer tests
│   │       ├── test_motion_detection.py
│   │       ├── test_ai_service.py
│   │       └── test_event_processor.py
│   └── data/                            # Runtime data directory (gitignored)
│       ├── app.db                       # SQLite database file
│       ├── thumbnails/                  # Event thumbnail images
│       │   └── {event_id}.jpg
│       └── logs/                        # Application log files
│           ├── app.log
│           └── error.log
├── frontend/
│   ├── package.json                     # npm dependencies
│   ├── next.config.js                   # Next.js configuration
│   ├── tailwind.config.js               # Tailwind CSS configuration
│   ├── tsconfig.json                    # TypeScript configuration
│   ├── .env.local.example               # Frontend env vars template
│   ├── .env.local                       # Actual env vars (gitignored)
│   ├── components.json                  # shadcn/ui configuration
│   ├── public/                          # Static assets
│   │   ├── favicon.ico
│   │   ├── icons/                       # App icons
│   │   └── images/                      # Static images
│   ├── app/                             # Next.js App Router pages
│   │   ├── layout.tsx                  # Root layout (nav, auth provider)
│   │   ├── page.tsx                    # Dashboard home (redirect to /events)
│   │   ├── globals.css                 # Global styles, Tailwind directives
│   │   ├── events/                     # Event management
│   │   │   ├── page.tsx                # Event timeline (main dashboard)
│   │   │   └── [id]/
│   │   │       └── page.tsx            # Event detail modal/page
│   │   ├── cameras/                    # Camera management
│   │   │   ├── page.tsx                # Camera grid view
│   │   │   ├── new/
│   │   │   │   └── page.tsx            # Add camera form
│   │   │   └── [id]/
│   │   │       ├── page.tsx            # Camera detail/edit
│   │   │       └── live/
│   │   │           └── page.tsx        # Full-screen camera view
│   │   ├── alert-rules/                # Alert rule management
│   │   │   ├── page.tsx                # Rules list
│   │   │   ├── new/
│   │   │   │   └── page.tsx            # Create rule form
│   │   │   └── [id]/
│   │   │       └── page.tsx            # Edit rule form
│   │   ├── settings/                   # System settings
│   │   │   └── page.tsx                # Settings tabs (general, AI, detection)
│   │   ├── login/                      # Authentication (Phase 1.5)
│   │   │   └── page.tsx                # Login form
│   │   └── api/                        # Next.js API routes (optional proxy)
│   │       └── [...path]/
│   │           └── route.ts            # Catch-all proxy to backend
│   ├── components/                      # React components
│   │   ├── ui/                         # shadcn/ui base components
│   │   │   ├── button.tsx
│   │   │   ├── card.tsx
│   │   │   ├── dialog.tsx
│   │   │   ├── form.tsx
│   │   │   ├── input.tsx
│   │   │   ├── label.tsx
│   │   │   ├── select.tsx
│   │   │   ├── table.tsx
│   │   │   ├── tabs.tsx
│   │   │   ├── toast.tsx
│   │   │   └── ...                     # Other shadcn components as needed
│   │   ├── layout/
│   │   │   ├── Header.tsx              # Top navigation bar
│   │   │   ├── Sidebar.tsx             # Side navigation (optional)
│   │   │   └── Footer.tsx              # Footer (optional)
│   │   ├── events/
│   │   │   ├── EventCard.tsx           # Single event card in timeline
│   │   │   ├── EventTimeline.tsx       # Scrollable event list
│   │   │   ├── EventDetail.tsx         # Expanded event view
│   │   │   ├── EventFilters.tsx        # Filter controls (date, camera, type)
│   │   │   └── EventSearch.tsx         # Search bar component
│   │   ├── cameras/
│   │   │   ├── CameraGrid.tsx          # Grid of camera previews
│   │   │   ├── CameraPreview.tsx       # Single camera preview tile
│   │   │   ├── CameraForm.tsx          # Add/edit camera form
│   │   │   ├── CameraStatus.tsx        # Connection status indicator
│   │   │   └── AnalyzeNowButton.tsx    # Manual analysis trigger
│   │   ├── alerts/
│   │   │   ├── AlertRuleCard.tsx       # Single rule display
│   │   │   ├── AlertRuleForm.tsx       # Rule creation/edit form
│   │   │   ├── AlertRuleTest.tsx       # Test rule against past events
│   │   │   └── ConditionBuilder.tsx    # Visual condition builder
│   │   └── common/
│   │       ├── Loading.tsx             # Loading spinner
│   │       ├── ErrorBoundary.tsx       # Error handling wrapper
│   │       ├── NotificationBell.tsx    # WebSocket notification indicator
│   │       ├── ConfirmDialog.tsx       # Confirmation modal
│   │       └── EmptyState.tsx          # No data placeholder
│   ├── lib/                             # Frontend utilities
│   │   ├── api-client.ts               # Typed API client wrapper
│   │   ├── websocket.ts                # WebSocket client class
│   │   ├── utils.ts                    # Helper functions (cn, formatDate, etc.)
│   │   └── constants.ts                # Frontend constants (API URL, etc.)
│   ├── hooks/                           # Custom React hooks
│   │   ├── useEvents.ts                # Fetch/filter events
│   │   ├── useCameras.ts               # Camera CRUD operations
│   │   ├── useAlertRules.ts            # Alert rule CRUD
│   │   ├── useWebSocket.ts             # WebSocket connection hook
│   │   ├── useAuth.ts                  # Auth state (Phase 1.5)
│   │   └── useToast.ts                 # Toast notifications
│   ├── types/                           # TypeScript type definitions
│   │   ├── event.ts                    # Event, EventFilters types
│   │   ├── camera.ts                   # Camera, CameraConfig types
│   │   ├── alert-rule.ts               # AlertRule, RuleCondition types
│   │   └── user.ts                     # User, AuthState types
│   └── context/                         # React Context providers
│       ├── AuthContext.tsx             # Authentication state
│       └── WebSocketContext.tsx        # WebSocket connection state
├── docker-compose.yml                   # Docker orchestration (optional)
├── Dockerfile.backend                   # Backend container
├── Dockerfile.frontend                  # Frontend container
├── .gitignore                           # Git ignore patterns
├── README.md                            # Project documentation
└── docs/                                # Documentation directory
    ├── architecture.md                  # This document!
    ├── prd/                            # Product requirements
    │   ├── README.md
    │   ├── 01-overview-goals.md
    │   ├── 02-personas-stories.md
    │   └── 03-functional-requirements.md
    └── api/                            # API documentation
        └── openapi.json                # OpenAPI spec (auto-generated)
```

---

## Epic to Architecture Mapping

| Epic/Feature | Architecture Components | Key Files |
|--------------|------------------------|-----------|
| **F1: Camera Integration** | Camera service, RTSP capture, USB support | `camera_service.py`, `cameras.py` API, `CameraForm.tsx` |
| **F2: Motion Detection** | OpenCV background subtraction, zone filtering | `motion_detection.py`, `event_processor.py` |
| **F3: AI Descriptions** | Multi-provider AI service, fallback logic | `ai_service.py`, OpenAI/Gemini/Claude SDKs |
| **F4: Event Storage** | SQLAlchemy models, event API, database migrations | `event.py` model, `events.py` API, Alembic migrations |
| **F5: Alert Rules** | Rule engine, condition evaluation, cooldown | `alert_service.py`, `alert_rules.py` API, `AlertRuleForm.tsx` |
| **F6: Dashboard UI** | Next.js pages, React components, WebSocket updates | `app/events/page.tsx`, `EventTimeline.tsx`, WebSocket context |
| **F7: Authentication** | JWT tokens, password hashing, session management | `security.py`, `auth.py` API, `AuthContext.tsx` |
| **F8: System Admin** | Settings API, logging, health check | `settings.py` API, `logging.py`, `health.py` |
| **F9: Webhooks** | HTTP POST with retry, webhook dispatch service | `webhook_service.py`, alert rule webhook actions |

---

## Data Architecture

### Database Schema

**cameras** table:
```sql
CREATE TABLE cameras (
    id TEXT PRIMARY KEY,                    -- UUID
    name TEXT NOT NULL,                     -- User-friendly name
    type TEXT NOT NULL,                     -- 'rtsp' or 'usb'
    rtsp_url TEXT,                          -- RTSP URL (nullable for USB)
    username TEXT,                          -- RTSP auth username
    password TEXT,                          -- RTSP auth password (encrypted)
    device_index INTEGER,                   -- USB device index (nullable for RTSP)
    frame_rate INTEGER DEFAULT 5,           -- Capture FPS
    is_enabled BOOLEAN DEFAULT TRUE,        -- Active/inactive
    motion_sensitivity TEXT DEFAULT 'medium', -- 'low', 'medium', 'high'
    motion_cooldown INTEGER DEFAULT 60,     -- Seconds between motion triggers
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**events** table:
```sql
CREATE TABLE events (
    id TEXT PRIMARY KEY,                    -- UUID
    camera_id TEXT NOT NULL,                -- FK to cameras.id
    timestamp TIMESTAMP NOT NULL,           -- When motion detected
    description TEXT NOT NULL,              -- AI-generated description
    confidence INTEGER,                     -- 0-100 confidence score
    objects_detected TEXT,                  -- JSON array: ["person", "package"]
    thumbnail_path TEXT,                    -- Relative path to thumbnail image
    alert_triggered BOOLEAN DEFAULT FALSE,  -- Was any alert triggered?
    alert_rule_ids TEXT,                    -- JSON array of triggered rule IDs
    user_feedback TEXT,                     -- Optional user rating/feedback
    is_manual BOOLEAN DEFAULT FALSE,        -- Manual analysis vs motion-triggered
    processing_time_ms INTEGER,             -- Time to process (performance metric)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (camera_id) REFERENCES cameras(id) ON DELETE CASCADE
);

CREATE INDEX idx_events_timestamp ON events(timestamp DESC);
CREATE INDEX idx_events_camera_id ON events(camera_id);
CREATE INDEX idx_events_alert_triggered ON events(alert_triggered);
```

**alert_rules** table:
```sql
CREATE TABLE alert_rules (
    id TEXT PRIMARY KEY,                    -- UUID
    name TEXT NOT NULL,                     -- Rule name
    is_enabled BOOLEAN DEFAULT TRUE,        -- Active/inactive
    conditions TEXT NOT NULL,               -- JSON object with rule logic
    actions TEXT NOT NULL,                  -- JSON object with action config
    cooldown_minutes INTEGER DEFAULT 30,    -- Cooldown between alerts
    last_triggered_at TIMESTAMP,            -- Last time rule matched
    trigger_count INTEGER DEFAULT 0,        -- How many times triggered
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Conditions JSON structure:**
```json
{
  "object_types": ["person", "package"],      // OR logic
  "confidence_min": 70,                       // Minimum confidence threshold
  "time_range": {
    "start": "09:00",                         // Start time (HH:MM)
    "end": "18:00"                            // End time (HH:MM)
  },
  "days_of_week": [1, 2, 3, 4, 5],           // Mon=1, Sun=7
  "cameras": ["camera-uuid-1"],               // Specific cameras or empty for all
  "keywords": ["delivery", "package"]         // Description must contain (optional)
}
```

**Actions JSON structure:**
```json
{
  "dashboard_notification": true,             // Show in notification bell
  "webhook_url": "https://example.com/hook",  // HTTP POST target
  "webhook_headers": {                        // Custom headers for webhook
    "Authorization": "Bearer token123"
  }
}
```

**users** table (Phase 1.5):
```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,                    -- UUID
    username TEXT UNIQUE NOT NULL,          -- Login username
    email TEXT UNIQUE,                      -- Email (optional for MVP)
    hashed_password TEXT NOT NULL,          -- bcrypt hash
    is_active BOOLEAN DEFAULT TRUE,         -- Account enabled/disabled
    is_admin BOOLEAN DEFAULT FALSE,         -- Admin privileges
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**system_settings** table:
```sql
CREATE TABLE system_settings (
    key TEXT PRIMARY KEY,                   -- Setting name (unique)
    value TEXT NOT NULL,                    -- JSON-encoded value
    description TEXT,                       -- Human-readable description
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Example settings:**
- `ai_model_primary`: `"openai"`
- `ai_api_key_openai`: `"encrypted:..."` (Fernet encrypted)
- `data_retention_days`: `"30"`
- `timezone`: `"America/New_York"`

### Data Relationships

```
cameras (1) ──────< events (many)
                    │
                    └───> alert_rules (many-to-many via alert_rule_ids JSON array)
                    
users (1) ──────< events (many) [Phase 2: multi-user]
```

---

## API Contracts

### REST API Endpoints

**Base URL:** `http://localhost:8000/api/v1`

#### Cameras

**GET /cameras**
- List all cameras
- Query params: `is_enabled` (bool filter)
- Response: `{ data: Camera[], meta: {...} }`

**POST /cameras**
- Create new camera
- Body: `{ name, type, rtsp_url?, username?, password?, device_index?, frame_rate? }`
- Response: `{ data: Camera, meta: {...} }`

**GET /cameras/{id}**
- Get camera by ID
- Response: `{ data: Camera, meta: {...} }`

**PUT /cameras/{id}**
- Update camera
- Body: Partial `{ name?, is_enabled?, ...}`
- Response: `{ data: Camera, meta: {...} }`

**DELETE /cameras/{id}**
- Delete camera (and cascade delete events)
- Response: `{ data: { deleted: true }, meta: {...} }`

**POST /cameras/{id}/test**
- Test camera connection
- Response: `{ data: { success: bool, message: string, thumbnail?: string }, meta: {...} }`

**POST /cameras/{id}/analyze**
- Manual analysis trigger
- Response: `{ data: { event_id: string, message: string }, meta: {...} }`

#### Events

**GET /events**
- List events with pagination
- Query params:
  - `start_date` (ISO string)
  - `end_date` (ISO string)
  - `camera_id` (UUID)
  - `object_type` (string, can repeat for multiple)
  - `search` (full-text search)
  - `page` (default 1)
  - `per_page` (default 50, max 200)
- Response: `{ data: Event[], meta: { total, page, per_page, pages } }`

**GET /events/{id}**
- Get single event
- Response: `{ data: Event, meta: {...} }`

**GET /events/{id}/thumbnail**
- Get event thumbnail image
- Response: JPEG image (Content-Type: image/jpeg)

**DELETE /events/{id}**
- Delete event
- Response: `{ data: { deleted: true }, meta: {...} }`

**GET /events/stats**
- Event statistics
- Query params: `start_date`, `end_date`
- Response: `{ data: { total_events, by_object_type: {...}, by_camera: {...}, by_hour: [...] }, meta: {...} }`

#### Alert Rules

**GET /alert-rules**
- List all alert rules
- Response: `{ data: AlertRule[], meta: {...} }`

**POST /alert-rules**
- Create alert rule
- Body: `{ name, is_enabled, conditions, actions, cooldown_minutes }`
- Response: `{ data: AlertRule, meta: {...} }`

**GET /alert-rules/{id}**
- Get alert rule
- Response: `{ data: AlertRule, meta: {...} }`

**PUT /alert-rules/{id}**
- Update alert rule
- Body: Partial rule object
- Response: `{ data: AlertRule, meta: {...} }`

**DELETE /alert-rules/{id}**
- Delete alert rule
- Response: `{ data: { deleted: true }, meta: {...} }`

**POST /alert-rules/{id}/test**
- Test rule against recent events
- Response: `{ data: { matching_events: Event[] }, meta: {...} }`

#### Settings

**GET /settings**
- Get all system settings
- Response: `{ data: { [key]: value }, meta: {...} }`

**PUT /settings**
- Update settings (bulk update)
- Body: `{ [key]: value }`
- Response: `{ data: { updated: true }, meta: {...} }`

**GET /settings/{key}**
- Get single setting
- Response: `{ data: { key, value, description }, meta: {...} }`

**PUT /settings/{key}**
- Update single setting
- Body: `{ value }`
- Response: `{ data: { key, value }, meta: {...} }`

#### Health

**GET /health**
- System health check (no auth required)
- Response: 
```json
{
  "status": "healthy",
  "timestamp": "2025-11-15T10:30:00Z",
  "components": {
    "database": "healthy",
    "cameras": {
      "camera-1": "connected",
      "camera-2": "disconnected"
    },
    "ai_model": "healthy"
  },
  "metrics": {
    "uptime_seconds": 86400,
    "events_processed_today": 42,
    "queue_size": 0
  }
}
```

#### Authentication (Phase 1.5)

**POST /login**
- User login
- Body: `{ username, password }`
- Response: `{ data: { access_token, token_type: "bearer", user: {...} }, meta: {...} }`
- Sets HTTP-only cookie with JWT

**POST /logout**
- User logout
- Response: `{ data: { logged_out: true }, meta: {...} }`
- Clears session cookie

**GET /me**
- Get current user
- Requires: Bearer token or session cookie
- Response: `{ data: User, meta: {...} }`

### WebSocket Protocol

**Connection:** `ws://localhost:8000/ws`

**Authentication (Phase 1.5):**
- Query param: `?token={jwt_token}`
- Or send as first message: `{ "type": "AUTH", "data": { "token": "..." } }`

**Message Format (Server → Client):**
```json
{
  "type": "EVENT_CREATED",
  "data": {
    "event": { /* full Event object */ }
  },
  "timestamp": "2025-11-15T10:30:00Z"
}
```

**Message Types:**
- `EVENT_CREATED`: New event stored
- `ALERT_TRIGGERED`: Alert rule matched and action taken
- `CAMERA_STATUS_CHANGED`: Camera connected/disconnected
- `PROCESSING_STATUS`: Update on long-running operation
- `ERROR`: Server-side error notification

**Client → Server Messages:**
- `PING`: Keep-alive message
- Response: `PONG`

**Connection Management:**
- Auto-reconnect on disconnect (exponential backoff: 1s, 2s, 4s, 8s, max 30s)
- Heartbeat: Client sends PING every 30 seconds
- Server closes connection after 60 seconds without PING

---

## Implementation Patterns

### Naming Conventions

**Backend (Python):**
- **Files:** `snake_case.py` (e.g., `camera_service.py`, `event_processor.py`)
- **Classes:** `PascalCase` (e.g., `CameraService`, `EventProcessor`, `AlertRule`)
- **Functions/Methods:** `snake_case` (e.g., `process_event`, `get_camera_by_id`, `evaluate_rule`)
- **Constants:** `UPPER_SNAKE_CASE` (e.g., `MAX_RETRIES`, `DEFAULT_TIMEOUT`, `AI_MODEL_PRIMARY`)
- **Private methods:** `_leading_underscore` (e.g., `_capture_frame`, `_encrypt_api_key`)
- **Database tables:** `snake_case` plural (e.g., `cameras`, `events`, `alert_rules`, `system_settings`)
- **Database columns:** `snake_case` (e.g., `camera_id`, `created_at`, `is_enabled`, `rtsp_url`)
- **Foreign keys:** `{table_singular}_id` (e.g., `camera_id`, `user_id`, `alert_rule_id`)
- **API endpoints:** `kebab-case` (e.g., `/api/v1/alert-rules`, `/api/v1/event-stats`)

**Frontend (TypeScript/React):**
- **Component files:** `PascalCase.tsx` (e.g., `EventCard.tsx`, `CameraPreview.tsx`, `AlertRuleForm.tsx`)
- **Utility files:** `kebab-case.ts` (e.g., `api-client.ts`, `websocket.ts`, `utils.ts`)
- **Components:** `PascalCase` (e.g., `EventCard`, `CameraPreview`, `Header`)
- **Functions:** `camelCase` (e.g., `fetchEvents`, `handleSubmit`, `formatDate`)
- **Constants:** `UPPER_SNAKE_CASE` (e.g., `API_BASE_URL`, `WS_RECONNECT_DELAY`)
- **Types/Interfaces:** `PascalCase`, interfaces prefixed with `I` (e.g., `IEvent`, `ICameraConfig`, `IAlertRule`)
- **Hooks:** `use` prefix (e.g., `useEvents`, `useCameras`, `useWebSocket`)
- **Context:** `PascalCase` with `Context` suffix (e.g., `AuthContext`, `WebSocketContext`)
- **CSS classes:** Tailwind utilities (avoid custom classes unless necessary)

### Code Organization

**Backend Service Pattern:**
```python
# app/services/camera_service.py
from typing import Optional, List
import cv2
import threading
from app.models.camera import Camera
from app.core.logging import logger

class CameraService:
    """Handles camera capture and RTSP connection management."""
    
    def __init__(self):
        self._capture_threads: dict[str, threading.Thread] = {}
        self._active_captures: dict[str, cv2.VideoCapture] = {}
    
    async def start_camera(self, camera: Camera) -> bool:
        """Start capturing from camera in background thread."""
        try:
            # Implementation...
            logger.info(f"Started camera {camera.id}", extra={"camera_id": camera.id})
            return True
        except Exception as e:
            logger.error(f"Failed to start camera {camera.id}: {e}", exc_info=True)
            return False
    
    async def stop_camera(self, camera_id: str) -> None:
        """Stop camera capture thread."""
        # Implementation...
    
    def _capture_loop(self, camera: Camera) -> None:
        """Private method: continuous frame capture loop."""
        # Implementation...
```

**Frontend Hook Pattern:**
```typescript
// hooks/useEvents.ts
import { useState, useEffect } from 'react';
import { apiClient } from '@/lib/api-client';
import type { IEvent, EventFilters } from '@/types/event';

export function useEvents(filters?: EventFilters) {
  const [events, setEvents] = useState<IEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchEvents = async () => {
      try {
        setLoading(true);
        const data = await apiClient.get('/events', { params: filters });
        setEvents(data.data);
      } catch (err) {
        setError(err.message || 'Failed to fetch events');
      } finally {
        setLoading(false);
      }
    };

    fetchEvents();
  }, [filters]);

  return { events, loading, error };
}
```

### Error Handling

**Backend Error Pattern:**
```python
from fastapi import HTTPException, status
from app.core.logging import logger

async def process_event(event_id: str) -> Event:
    try:
        event = await event_service.process(event_id)
        return event
    except EventNotFoundError as e:
        logger.warning(f"Event not found: {event_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event {event_id} not found"
        )
    except AIServiceError as e:
        logger.error(f"AI service failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service temporarily unavailable"
        )
    except Exception as e:
        logger.error(f"Unexpected error processing event {event_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )
```

**Frontend Error Pattern:**
```typescript
try {
  const camera = await apiClient.post('/cameras', cameraData);
  toast.success('Camera added successfully');
  router.push('/cameras');
} catch (error) {
  console.error('Failed to add camera:', error);
  
  if (error.status === 400) {
    toast.error(error.message || 'Invalid camera configuration');
  } else if (error.status === 409) {
    toast.error('Camera with this name already exists');
  } else {
    toast.error('Failed to add camera. Please try again.');
  }
}
```

### Logging Standards

**Log Levels:**
- `DEBUG`: Detailed diagnostic info (frame capture details, motion detection metrics)
- `INFO`: General informational messages (event processed, alert triggered, camera started)
- `WARNING`: Something unexpected but not breaking (AI API slow, camera lagging, high queue)
- `ERROR`: Error occurred but handled (AI API failed with fallback, camera disconnected)
- `CRITICAL`: System cannot continue (database connection lost, all AI providers down)

**Structured Logging:**
```python
logger.info(
    f"Event {event_id} processed successfully",
    extra={
        "event_id": event_id,
        "camera_id": camera_id,
        "processing_time_ms": duration_ms,
        "confidence": confidence,
        "objects_detected": objects,
        "ai_provider": "openai"
    }
)
```

**What NOT to log:**
- Passwords or API keys (use `[REDACTED]` placeholder)
- Full RTSP URLs with credentials
- User personal data beyond IDs
- Full stack traces in production (sanitize)

### Date/Time Handling

**Backend:**
- Store all timestamps in UTC (no timezone)
- Use `datetime.datetime.utcnow()` for current time
- SQLAlchemy: `DateTime(timezone=False)` (SQLite doesn't support timezones)
- API responses: ISO 8601 format (`2025-11-15T10:30:00Z`)

```python
from datetime import datetime

# Create timestamp
timestamp = datetime.utcnow()

# Store in database
event.timestamp = timestamp

# Return in API response
return {
    "timestamp": timestamp.isoformat() + "Z"  # Add 'Z' for UTC indicator
}
```

**Frontend:**
- Display times in user's local timezone
- Use `date-fns` for all date formatting
- Recent events: relative time ("5 minutes ago", "2 hours ago")
- Older events: absolute time ("Nov 15, 10:30 AM")

```typescript
import { formatDistanceToNow, format } from 'date-fns';

// Display logic
const displayTime = (timestamp: string) => {
  const date = new Date(timestamp);
  const hoursAgo = (Date.now() - date.getTime()) / (1000 * 60 * 60);
  
  if (hoursAgo < 24) {
    return formatDistanceToNow(date, { addSuffix: true }); // "5 minutes ago"
  } else {
    return format(date, 'MMM d, h:mm a'); // "Nov 15, 10:30 AM"
  }
};
```

### Testing Patterns

**Backend Unit Test:**
```python
# tests/test_services/test_motion_detection.py
import pytest
from app.services.motion_detection import MotionDetectionService

@pytest.fixture
def motion_service():
    return MotionDetectionService(sensitivity='medium')

def test_detect_motion_with_significant_change(motion_service):
    # Arrange
    frame1 = load_test_image('empty_room.jpg')
    frame2 = load_test_image('person_enters.jpg')
    
    # Act
    motion_detected = motion_service.detect_motion(frame1, frame2)
    
    # Assert
    assert motion_detected is True

def test_detect_motion_no_change(motion_service):
    frame = load_test_image('empty_room.jpg')
    motion_detected = motion_service.detect_motion(frame, frame)
    assert motion_detected is False
```

**Frontend Component Test:**
```typescript
// components/events/EventCard.test.tsx
import { render, screen } from '@testing-library/react';
import { EventCard } from './EventCard';

const mockEvent = {
  id: 'event-123',
  timestamp: '2025-11-15T10:30:00Z',
  description: 'Person wearing blue jacket approaching front door',
  confidence: 85,
  objects_detected: ['person'],
  camera_id: 'camera-1'
};

test('renders event card with description', () => {
  render(<EventCard event={mockEvent} />);
  expect(screen.getByText(/Person wearing blue jacket/i)).toBeInTheDocument();
});

test('displays confidence score', () => {
  render(<EventCard event={mockEvent} />);
  expect(screen.getByText('85%')).toBeInTheDocument();
});
```

---

## Security Architecture

### Authentication Flow (Phase 1.5)

1. User submits username/password to `/api/v1/login`
2. Backend validates credentials (bcrypt comparison)
3. Backend generates JWT token with 24h expiration
4. Backend sets HTTP-only cookie with token
5. Frontend receives user data and stores in AuthContext
6. Subsequent requests include cookie automatically
7. Backend validates JWT on protected endpoints

**JWT Payload:**
```json
{
  "sub": "user-uuid",
  "username": "john_doe",
  "exp": 1731686400,
  "iat": 1731600000
}
```

### API Key Encryption

AI API keys stored encrypted in database:

```python
from cryptography.fernet import Fernet

# Generate key (store in environment variable)
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
fernet = Fernet(ENCRYPTION_KEY)

# Encrypt API key before storing
encrypted_key = fernet.encrypt(api_key.encode())
setting.value = f"encrypted:{encrypted_key.decode()}"

# Decrypt when needed
if setting.value.startswith("encrypted:"):
    encrypted_key = setting.value[10:]  # Remove "encrypted:" prefix
    api_key = fernet.decrypt(encrypted_key.encode()).decode()
```

### Input Validation

**Backend:**
- Pydantic schemas validate all request bodies
- Path parameters validated by type hints
- SQL injection prevented by SQLAlchemy ORM
- RTSP URL validation (format, protocol)

**Frontend:**
- React Hook Form + Zod for form validation
- API responses validated against TypeScript types
- XSS prevention: React auto-escapes by default
- CSRF protection: HTTP-only cookies + SameSite attribute

### CORS Configuration

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Production:** Replace with actual domain, restrict methods to needed ones.

---

## Performance Considerations

### Backend Optimizations

**Database:**
- Indexes on frequently queried columns (`events.timestamp`, `events.camera_id`)
- Connection pooling (SQLAlchemy default pool)
- Lazy loading for relationships
- Pagination for large result sets (max 200 per page)

**Image Processing:**
- Thumbnail generation asynchronous (BackgroundTasks)
- Compress thumbnails to <200KB JPEG
- Resize to 640x480 before storing
- Original frames discarded immediately after AI analysis

**Motion Detection:**
- Run in separate thread per camera
- Process at configurable FPS (default 5 FPS)
- Skip frames if processing can't keep up
- Background subtractor history: 500 frames

**AI API Calls:**
- Timeout: 10 seconds
- Retry with fallback provider on failure
- Queue if rate limit hit
- Cache provider availability status (5 min)

### Frontend Optimizations

**Next.js Features:**
- Server Components for initial page load (events, cameras)
- Client Components only where needed (forms, real-time)
- Image optimization via Next.js Image component
- Route prefetching for faster navigation

**Data Fetching:**
- SWR or React Query for caching API responses
- Optimistic updates for better UX
- Debounce search inputs (500ms)
- Virtual scrolling for large event lists

**WebSocket:**
- Single connection shared across app
- Automatic reconnection with exponential backoff
- Buffer messages during disconnect
- Heartbeat to detect stale connections

---

## Deployment Architecture

### Development Environment

```bash
# Terminal 1: Backend
cd backend
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Frontend
cd frontend
npm run dev

# Access:
# - Frontend: http://localhost:3000
# - Backend API: http://localhost:8000
# - API Docs: http://localhost:8000/docs
```

### Production Deployment (Docker)

**docker-compose.yml:**
```yaml
version: '3.8'

services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=sqlite:///data/app.db
      - ENCRYPTION_KEY=${ENCRYPTION_KEY}
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
    volumes:
      - ./backend/data:/app/data
      - /dev/video0:/dev/video0  # USB camera access
    restart: unless-stopped

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://backend:8000
      - NEXT_PUBLIC_WS_URL=ws://backend:8000
    depends_on:
      - backend
    restart: unless-stopped
```

**Dockerfile.backend:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libopencv-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Dockerfile.frontend:**
```dockerfile
FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

CMD ["npm", "start"]
```

---

## Architecture Decision Records (ADRs)

### ADR-001: Event-Driven Architecture

**Decision:** Use motion detection as trigger for AI processing, not continuous analysis.

**Rationale:**
- Cost: AI API calls expensive, motion-triggered reduces calls by 95%+
- Performance: System can process 2+ events/day per camera vs continuous strain
- Privacy: Only analyze when motion detected, not 24/7 recording

**Trade-offs:**
- May miss very slow-moving objects
- Depends on motion detection accuracy
- Requires tuning motion sensitivity

**Status:** Accepted

---

### ADR-002: Description Storage vs Video Storage

**Decision:** Store AI-generated descriptions and thumbnails, not video footage.

**Rationale:**
- Storage: 1 event = ~50KB vs 1 minute video = 10MB (200x smaller)
- Privacy: Descriptions less sensitive than video, easier GDPR compliance
- Searchability: Natural language searchable, video is not
- Accessibility: Descriptions readable by screen readers

**Trade-offs:**
- Cannot review full video context after the fact
- Description quality depends on AI model accuracy
- Single frame may miss context

**Status:** Accepted (core product philosophy)

---

### ADR-003: SQLite for MVP Database

**Decision:** Use SQLite instead of PostgreSQL or MySQL for MVP.

**Rationale:**
- Zero setup: File-based, no server to install
- Performance: Sufficient for 10,000+ events (tested)
- Simplicity: Single file backup, easy to distribute
- Migration path: SQLAlchemy makes PostgreSQL migration easy in Phase 2

**Trade-offs:**
- No concurrent write support (acceptable for single-camera)
- Limited full-text search (can use FTS5 extension)
- No native JSON query operators (store as TEXT)

**Status:** Accepted for MVP, revisit in Phase 2

---

### ADR-004: FastAPI BackgroundTasks vs External Queue

**Decision:** Use FastAPI's BackgroundTasks for event processing, not Celery/Redis.

**Rationale:**
- Simplicity: No additional services to manage
- MVP scope: Single camera means low throughput
- Async: Python asyncio handles concurrency well
- Cost: $0 infrastructure (no Redis hosting)

**Trade-offs:**
- No persistence: Tasks lost if server crashes during processing
- No distributed processing: Can't scale across machines
- Limited monitoring: No Celery Flower equivalent

**Status:** Accepted for MVP, consider Celery in Phase 2 for multi-camera

---

### ADR-005: Multi-Provider AI with Fallback

**Decision:** Support OpenAI, Google Gemini, and Anthropic Claude with automatic fallback.

**Rationale:**
- Reliability: One provider down doesn't break system
- Cost: Can switch to cheapest/free provider
- Quality: Can A/B test which gives best descriptions
- Flexibility: Users can choose based on ethics/preference

**Trade-offs:**
- Complexity: 3 SDK integrations instead of 1
- Testing: Must test all providers
- Inconsistency: Descriptions may vary by provider

**Status:** Accepted (key differentiator)

---

### ADR-006: Next.js App Router vs Pages Router

**Decision:** Use Next.js 15 App Router (not Pages Router).

**Rationale:**
- Future-proof: App Router is the future of Next.js
- Performance: React Server Components reduce client JS
- Layout: Better nested layout support
- Streaming: Suspense for progressive rendering

**Trade-offs:**
- Learning curve: Newer paradigm, fewer examples
- Ecosystem: Some libraries not optimized yet
- Complexity: Server/Client component distinction

**Status:** Accepted (Next.js recommendation)

---

### ADR-007: shadcn/ui vs Material-UI vs Chakra

**Decision:** Use shadcn/ui for component library.

**Rationale:**
- Ownership: Copy-paste components, full control
- Tailwind: Integrates perfectly with Tailwind CSS
- Customization: Easy to modify unlike npm packages
- Bundle size: Only include what you use

**Trade-offs:**
- Manual updates: Must copy new versions manually
- Initial setup: More components to set up initially
- No built-in themes: Must style from scratch

**Status:** Accepted (Tailwind ecosystem standard)

---

## Glossary

**Terms used throughout architecture:**

- **Event:** A detected occurrence (motion + AI analysis result)
- **Alert:** Notification triggered by event matching rule
- **Rule:** User-defined conditions that trigger alerts
- **Webhook:** HTTP POST sent to external URL when alert triggers
- **Thumbnail:** Small JPEG image captured during event (~200KB)
- **Confidence:** AI model's certainty score (0-100%)
- **Cooldown:** Time period where duplicate alerts suppressed
- **RTSP:** Real-Time Streaming Protocol (camera feed standard)
- **Motion Detection:** Algorithm to identify movement in frames
- **Background Subtraction:** Technique to detect motion by comparing frames
- **JWT:** JSON Web Token (authentication token format)
- **ORM:** Object-Relational Mapping (database abstraction)
- **Async:** Asynchronous programming (non-blocking I/O)
- **Server Component:** React component that renders on server
- **Client Component:** React component that renders in browser

---

## Next Steps

**After architecture approval:**

1. **Sprint Planning:** Break into implementable stories (4-8 hour chunks)
2. **Story Prioritization:** Backend core → Frontend dashboard → Integration
3. **Environment Setup:** Initialize repos with starters
4. **Database Migrations:** Create initial schema with Alembic
5. **Implementation:** Follow epic order from PRD

**First Sprint Stories (Example):**
1. Initialize frontend with Next.js starter
2. Initialize backend with FastAPI + SQLAlchemy
3. Create database models (cameras, events, alert_rules)
4. Implement camera CRUD API endpoints
5. Implement camera service (RTSP capture)
6. Implement motion detection service
7. Build camera management UI

---

**Architecture validation checklist:**

- ✅ All PRD functional requirements have architectural support
- ✅ All PRD non-functional requirements addressed (performance, security, usability)
- ✅ Technology stack versions specified and verified as current
- ✅ Project structure complete with all necessary directories
- ✅ Database schema supports all features with proper relationships
- ✅ API contracts defined for all endpoints
- ✅ Implementation patterns documented for consistency
- ✅ Security considerations addressed (auth, encryption, validation)
- ✅ Performance optimizations identified for critical paths
- ✅ Deployment approach defined (dev + production)
- ✅ Architectural decisions recorded with rationale

---

**Generated by:** BMad Architect Agent
**Date:** 2025-11-15 (Phase 2 updated: 2025-11-30)
**For Project:** Live Object AI Classifier MVP + Phase 2
**Owner:** Brent
**Status:** Ready for Review ✅

---

## Phase 2 Additions

This section documents the architectural additions for Phase 2, which adds native UniFi Protect integration and xAI Grok as an additional AI provider.

### Phase 2 Executive Summary

Phase 2 transforms the system from "works with any camera via RTSP" to "works *optimally* with your camera system" by adding native UniFi Protect integration. This unlocks:

- **Real-time WebSocket events** - No polling delays, instant detection
- **Camera auto-discovery** - No manual RTSP URL configuration
- **Smart detection filtering** - Person/Vehicle/Package/Animal pre-classification from Protect
- **Doorbell integration** - Ring events with visitor AI analysis
- **Multi-camera correlation** - Link related events across cameras

Additionally, xAI Grok joins the AI provider roster, giving users more options for event descriptions.

**Key Architectural Principles (Phase 2):**
1. **Native over Generic** - Purpose-built integrations for camera systems
2. **Coexistence** - UniFi Protect and RTSP/USB cameras work side-by-side
3. **Real-time First** - WebSocket-driven event flow
4. **Unified Pipeline** - All camera sources feed the same event system

---

### Phase 2 Technology Stack Additions

| Category | Technology | Version | Purpose |
|----------|------------|---------|---------|
| **UniFi Protect Client** | uiprotect | 4.x+ | Unofficial Python library for Protect API |
| **xAI Grok Client** | openai (OpenAI-compatible) | 1.x+ | xAI uses OpenAI-compatible API at api.x.ai |
| **WebSocket Client** | websockets | 12.x+ | Async WebSocket support for Protect |

**New Dependencies (backend/requirements.txt):**
```bash
# Phase 2: UniFi Protect
uiprotect>=4.0.0

# Phase 2: xAI Grok (uses OpenAI-compatible API)
# No new package needed - uses existing 'openai' package with custom base_url
# openai>=1.0.0  (already installed for GPT-4o support)

# WebSocket (if not already included)
websockets>=12.0
```

---

### Phase 2 Project Structure Additions

```
backend/
├── app/
│   ├── api/v1/
│   │   ├── protect.py              # NEW: UniFi Protect controller endpoints
│   │   └── ...
│   ├── models/
│   │   ├── protect_controller.py   # NEW: Protect controller model
│   │   └── ...
│   ├── schemas/
│   │   ├── protect.py              # NEW: Protect request/response schemas
│   │   └── ...
│   ├── services/
│   │   ├── protect_service.py      # NEW: Protect connection, WebSocket, events
│   │   ├── protect_event_handler.py # NEW: Process Protect events
│   │   ├── correlation_service.py  # NEW: Multi-camera event correlation
│   │   └── ai_service.py           # MODIFIED: Add xAI Grok provider
│   └── utils/
│       └── encryption.py           # MODIFIED: Encrypt Protect credentials
└── ...

frontend/
├── app/
│   └── settings/
│       └── page.tsx                # MODIFIED: Add UniFi Protect section
├── components/
│   ├── protect/                    # NEW: UniFi Protect components
│   │   ├── ControllerForm.tsx      # Add/edit controller connection
│   │   ├── ConnectionStatus.tsx    # Controller connection indicator
│   │   ├── DiscoveredCameraList.tsx # Auto-discovered cameras
│   │   ├── DiscoveredCameraCard.tsx # Single discovered camera
│   │   └── EventTypeFilter.tsx     # Smart detection filter selector
│   └── events/
│       ├── SourceTypeBadge.tsx     # NEW: Show camera source (Protect/RTSP/USB)
│       ├── SmartDetectionBadge.tsx # NEW: Show Protect detection type
│       └── CorrelationIndicator.tsx # NEW: Show correlated events
└── ...
```

---

### Phase 2 Database Schema Additions

**protect_controllers** table (NEW):
```sql
CREATE TABLE protect_controllers (
    id TEXT PRIMARY KEY,                    -- UUID
    name TEXT NOT NULL,                     -- User-friendly name (e.g., "Home UDM Pro")
    host TEXT NOT NULL,                     -- IP address or hostname
    port INTEGER DEFAULT 443,               -- HTTPS port (usually 443)
    username TEXT NOT NULL,                 -- Protect username
    password TEXT NOT NULL,                 -- Encrypted password (Fernet)
    verify_ssl BOOLEAN DEFAULT FALSE,       -- SSL certificate verification
    is_connected BOOLEAN DEFAULT FALSE,     -- Current connection status
    last_connected_at TIMESTAMP,            -- Last successful connection
    last_error TEXT,                        -- Last connection error message
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**cameras** table (EXTENDED):
```sql
-- Add new columns to existing cameras table
ALTER TABLE cameras ADD COLUMN source_type TEXT DEFAULT 'rtsp';  -- 'rtsp', 'usb', 'protect'
ALTER TABLE cameras ADD COLUMN protect_controller_id TEXT REFERENCES protect_controllers(id);
ALTER TABLE cameras ADD COLUMN protect_camera_id TEXT;           -- Native Protect camera ID
ALTER TABLE cameras ADD COLUMN protect_camera_type TEXT;         -- 'camera', 'doorbell'
ALTER TABLE cameras ADD COLUMN smart_detection_types TEXT;       -- JSON array: ["person", "vehicle", "package", "animal"]
ALTER TABLE cameras ADD COLUMN is_doorbell BOOLEAN DEFAULT FALSE;

-- Index for Protect camera lookups
CREATE INDEX idx_cameras_protect_camera_id ON cameras(protect_camera_id);
CREATE INDEX idx_cameras_source_type ON cameras(source_type);
```

**events** table (EXTENDED):
```sql
-- Add new columns to existing events table
ALTER TABLE events ADD COLUMN source_type TEXT DEFAULT 'rtsp';   -- 'rtsp', 'usb', 'protect'
ALTER TABLE events ADD COLUMN protect_event_id TEXT;             -- Native Protect event ID
ALTER TABLE events ADD COLUMN smart_detection_type TEXT;         -- 'person', 'vehicle', 'package', 'animal', 'motion'
ALTER TABLE events ADD COLUMN is_doorbell_ring BOOLEAN DEFAULT FALSE;
ALTER TABLE events ADD COLUMN correlated_event_ids TEXT;         -- JSON array of related event IDs
ALTER TABLE events ADD COLUMN correlation_group_id TEXT;         -- UUID for event groups

-- Index for correlation queries
CREATE INDEX idx_events_correlation_group ON events(correlation_group_id);
CREATE INDEX idx_events_protect_event_id ON events(protect_event_id);
```

---

### Phase 2 API Contracts

#### UniFi Protect Controller Endpoints

**Base URL:** `http://localhost:8000/api/v1/protect`

**POST /protect/controllers**
- Add UniFi Protect controller
- Body:
```json
{
  "name": "Home UDM Pro",
  "host": "192.168.1.1",
  "port": 443,
  "username": "admin",
  "password": "secretpassword",
  "verify_ssl": false
}
```
- Response: `{ data: ProtectController, meta: {...} }`
- **Side effect:** Validates connection before saving

**GET /protect/controllers**
- List all Protect controllers
- Response: `{ data: ProtectController[], meta: {...} }`

**GET /protect/controllers/{id}**
- Get controller with connection status
- Response: `{ data: ProtectController, meta: {...} }`

**PUT /protect/controllers/{id}**
- Update controller settings
- Body: Partial `{ name?, host?, port?, username?, password?, verify_ssl? }`
- Response: `{ data: ProtectController, meta: {...} }`

**DELETE /protect/controllers/{id}**
- Remove controller (disconnects WebSocket, removes discovered cameras)
- Response: `{ data: { deleted: true }, meta: {...} }`

**POST /protect/controllers/{id}/test**
- Test controller connection
- Response: `{ data: { success: bool, message: string, firmware_version?: string }, meta: {...} }`

**POST /protect/controllers/{id}/connect**
- Establish WebSocket connection
- Response: `{ data: { connected: true }, meta: {...} }`

**POST /protect/controllers/{id}/disconnect**
- Disconnect WebSocket
- Response: `{ data: { disconnected: true }, meta: {...} }`

**GET /protect/controllers/{id}/cameras**
- Get discovered cameras from controller
- Response:
```json
{
  "data": [
    {
      "protect_camera_id": "abc123",
      "name": "Front Door",
      "type": "doorbell",
      "model": "G4 Doorbell Pro",
      "is_enabled_for_ai": false,
      "smart_detection_types": ["person", "vehicle", "package"]
    }
  ],
  "meta": {...}
}
```

**POST /protect/controllers/{id}/cameras/{protect_camera_id}/enable**
- Enable camera for AI analysis
- Body: `{ smart_detection_types: ["person", "vehicle"] }`
- Response: `{ data: Camera, meta: {...} }`
- **Side effect:** Creates camera record in cameras table

**POST /protect/controllers/{id}/cameras/{protect_camera_id}/disable**
- Disable camera for AI analysis
- Response: `{ data: { disabled: true }, meta: {...} }`

#### xAI Grok Provider

**Settings key:** `ai_api_key_grok`

Uses existing `/api/v1/settings/{key}` endpoints for configuration.

**AI Provider order (configurable):**
```json
{
  "ai_provider_order": ["openai", "grok", "gemini", "anthropic"]
}
```

---

### Phase 2 Service Architecture

#### ProtectService (NEW)

**File:** `backend/app/services/protect_service.py`

**Responsibilities:**
- Manage connection to UniFi Protect controller
- Maintain WebSocket connection with auto-reconnect
- Discover cameras from controller
- Receive real-time events via WebSocket
- Fetch snapshots on event trigger

**Key Methods:**
```python
class ProtectService:
    """Manages UniFi Protect controller connections and events."""

    async def connect(self, controller: ProtectController) -> bool:
        """Establish authenticated WebSocket connection to Protect controller."""

    async def disconnect(self, controller_id: str) -> None:
        """Gracefully disconnect from controller."""

    async def discover_cameras(self, controller_id: str) -> List[ProtectCamera]:
        """Fetch all cameras from connected controller."""

    async def get_snapshot(self, controller_id: str, camera_id: str) -> bytes:
        """Fetch current snapshot from Protect camera."""

    async def _websocket_listener(self, controller: ProtectController) -> None:
        """Background task: Listen for real-time events from Protect."""

    async def _handle_event(self, event: dict) -> None:
        """Process incoming Protect event, filter, and queue for AI analysis."""

    async def _reconnect_with_backoff(self, controller: ProtectController) -> None:
        """Reconnect with exponential backoff (1s, 2s, 4s, 8s, max 30s)."""
```

**WebSocket Event Flow:**
```
UniFi Protect Controller
         │
         │ WebSocket (wss://)
         ▼
   ProtectService._websocket_listener()
         │
         │ Filter by enabled cameras + smart detection types
         ▼
   ProtectEventHandler.process_event()
         │
         │ Fetch snapshot via Protect API
         │
         ▼
   EventProcessor (existing pipeline)
         │
         │ AI description, store, alert evaluation
         ▼
   WebSocket broadcast to frontend
```

#### ProtectEventHandler (NEW)

**File:** `backend/app/services/protect_event_handler.py`

**Responsibilities:**
- Convert Protect events to internal event format
- Apply smart detection filtering
- Handle doorbell ring events differently
- Queue events for AI analysis

**Key Methods:**
```python
class ProtectEventHandler:
    """Converts UniFi Protect events into system events."""

    async def process_event(self, protect_event: dict, camera: Camera) -> Optional[Event]:
        """Convert Protect event to internal event, apply filters."""

    async def process_doorbell_ring(self, protect_event: dict, camera: Camera) -> Event:
        """Handle doorbell ring event (fetch snapshot, create event)."""

    def should_process_event(self, protect_event: dict, camera: Camera) -> bool:
        """Check if event passes camera's smart detection filters."""
```

#### CorrelationService (NEW)

**File:** `backend/app/services/correlation_service.py`

**Responsibilities:**
- Detect when multiple cameras capture the same real-world event
- Group correlated events with a shared correlation_group_id
- Time-window based correlation (configurable, default 10 seconds)

**Key Methods:**
```python
class CorrelationService:
    """Correlates events across multiple cameras."""

    async def check_correlation(self, event: Event) -> Optional[str]:
        """Check if event correlates with recent events, return group_id if so."""

    async def get_correlated_events(self, event_id: str) -> List[Event]:
        """Get all events in the same correlation group."""

    def _is_correlated(self, event1: Event, event2: Event) -> bool:
        """Determine if two events are likely the same real-world event."""
```

**Correlation Logic:**
- Events within `CORRELATION_WINDOW` seconds (default 10s)
- From different cameras
- Same or similar smart detection type
- Optional: Same Protect controller (stricter correlation)

#### AIService Extensions

**File:** `backend/app/services/ai_service.py` (MODIFIED)

**Add xAI Grok provider:**
```python
from openai import AsyncOpenAI

class AIService:
    PROVIDERS = ['openai', 'grok', 'gemini', 'anthropic']  # Updated

    def __init__(self):
        # ... existing initialization ...

        # xAI Grok uses OpenAI-compatible API with custom base_url
        self.grok_client = AsyncOpenAI(
            base_url="https://api.x.ai/v1",
            api_key=self._get_decrypted_key("ai_api_key_grok")
        )

    async def _call_grok(self, image_base64: str, prompt: str) -> str:
        """Call xAI Grok vision API for image description.

        Note: xAI provides an OpenAI-compatible API at api.x.ai/v1
        Uses the existing openai package with custom base_url.
        """
        response = await self.grok_client.chat.completions.create(
            model="grok-2-vision-1212",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                        {"type": "text", "text": prompt}
                    ]
                }
            ]
        )
        return response.choices[0].message.content
```

**Key Implementation Notes:**
- xAI Grok uses OpenAI-compatible API format
- No additional SDK required - reuses existing `openai` package
- Base URL: `https://api.x.ai/v1`
- Model: `grok-2-vision-1212` (vision-capable)

---

### Phase 2 WebSocket Protocol Additions

**New Message Types (Server → Client):**

```json
{
  "type": "PROTECT_CONNECTION_STATUS",
  "data": {
    "controller_id": "uuid",
    "status": "connected" | "disconnected" | "reconnecting",
    "error": null | "Connection refused"
  },
  "timestamp": "2025-11-30T10:30:00Z"
}
```

```json
{
  "type": "DOORBELL_RING",
  "data": {
    "event_id": "uuid",
    "camera_id": "uuid",
    "camera_name": "Front Door",
    "thumbnail_url": "/api/v1/events/uuid/thumbnail"
  },
  "timestamp": "2025-11-30T10:30:00Z"
}
```

```json
{
  "type": "EVENT_CREATED",
  "data": {
    "event": {
      "id": "uuid",
      "source_type": "protect",
      "smart_detection_type": "person",
      "correlated_event_ids": ["uuid2", "uuid3"],
      "...": "..."
    }
  },
  "timestamp": "2025-11-30T10:30:00Z"
}
```

---

### Phase 2 Security Considerations

**Credential Storage:**
- UniFi Protect passwords encrypted with Fernet (same as RTSP passwords)
- xAI Grok API key encrypted with Fernet (same as other AI keys)
- Never log credentials in plain text

**Network Security:**
- WebSocket connection uses WSS (TLS) when connecting to Protect
- `verify_ssl` option allows self-signed certificates (common in home setups)
- API keys transmitted only to respective provider APIs

**Authentication:**
- Protect API endpoints require same auth as other endpoints
- No credential caching in browser (server-side only)

---

### Phase 2 Performance Considerations

**WebSocket Connection:**
- Single persistent connection per Protect controller
- Automatic reconnection with exponential backoff
- Event buffering during brief disconnects (configurable buffer size)

**Snapshot Retrieval:**
- Target: < 1 second from Protect API
- Concurrent snapshot + AI analysis to minimize latency
- Cache controller authentication token (refresh on 401)

**Correlation Processing:**
- In-memory recent event buffer (last 60 seconds)
- O(n) scan for correlation candidates (acceptable for home-scale cameras)
- Async correlation check (doesn't block event storage)

**Scaling Limits (Phase 2):**
- Single Protect controller (multi-controller in future)
- Up to ~20 cameras per controller (Protect limit)
- ~100 events/day typical home usage

---

### Phase 2 Epic to Architecture Mapping

| Epic | Architecture Components | Key Files |
|------|------------------------|-----------|
| **Epic 1: Controller Integration** | ProtectService, controller model, WebSocket | `protect_service.py`, `protect.py` API, `ControllerForm.tsx` |
| **Epic 2: Camera Discovery** | ProtectService, camera model extensions | `protect_service.py`, `DiscoveredCameraList.tsx` |
| **Epic 3: Real-Time Events** | ProtectEventHandler, event pipeline | `protect_event_handler.py`, `event_processor.py` |
| **Epic 4: Doorbell & Correlation** | ProtectEventHandler, CorrelationService | `correlation_service.py`, `DoorbellEventCard.tsx` |
| **Epic 5: xAI Grok** | AIService extension | `ai_service.py`, Settings page |
| **Epic 6: Coexistence** | Event pipeline, unified frontend | `EventTimeline.tsx`, `SourceTypeBadge.tsx` |

---

### Phase 2 Architecture Decision Records

#### ADR-008: Native Integration over RTSP Polling

**Decision:** Build native UniFi Protect integration using `uiprotect` library instead of relying solely on RTSP streams.

**Rationale:**
- **Real-time:** WebSocket events arrive instantly vs 1-5 second RTSP polling delay
- **Smart Detection:** Leverage Protect's built-in person/vehicle/package detection
- **Auto-discovery:** No manual RTSP URL configuration needed
- **Reliability:** Native API more stable than RTSP stream management

**Trade-offs:**
- `uiprotect` is unofficial/community-maintained
- Firmware updates may break compatibility (mitigated by active community)
- Adds Protect-specific code path alongside generic RTSP

**Status:** Accepted (core Phase 2 feature)

---

#### ADR-009: Single Controller for Phase 2

**Decision:** Support only one UniFi Protect controller per system in Phase 2.

**Rationale:**
- **Simplicity:** Single controller covers 95%+ of home users
- **Complexity:** Multi-controller adds WebSocket management complexity
- **MVP Scope:** Get single-controller working well before expanding

**Trade-offs:**
- Users with multiple sites/controllers must choose one
- Multi-controller support deferred to Phase 3

**Status:** Accepted (revisit in Phase 3)

---

#### ADR-010: Time-Window Based Correlation

**Decision:** Use time-based correlation (10-second window) for multi-camera event grouping.

**Rationale:**
- **Simple:** Easy to understand and implement
- **Effective:** Most multi-camera captures happen within seconds
- **Low false positives:** Conservative window reduces incorrect correlations

**Trade-offs:**
- May miss slow-moving subjects crossing camera boundaries
- No spatial/object-based correlation (could add in future)
- Time sync assumes cameras/system have synchronized clocks

**Status:** Accepted (simple first approach)

---

#### ADR-011: xAI Grok as Additional Provider

**Decision:** Add xAI Grok to the AI provider fallback chain rather than replacing existing providers.

**Rationale:**
- **Choice:** Users can select preferred provider
- **Reliability:** More fallback options increase uptime
- **Comparison:** Users can compare description quality across providers

**Trade-offs:**
- More SDK dependencies
- More API keys to manage
- Testing complexity increases

**Status:** Accepted (aligns with multi-provider strategy)

---

### Phase 2 Integration Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             Event Sources                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐        │
│  │  UniFi Protect  │    │  RTSP Camera    │    │  USB Camera     │        │
│  │   Controller    │    │   (existing)    │    │   (existing)    │        │
│  └────────┬────────┘    └────────┬────────┘    └────────┬────────┘        │
│           │                      │                      │                  │
│     WebSocket               OpenCV               OpenCV                    │
│     (real-time)             (polling)            (polling)                 │
│           │                      │                      │                  │
│  ┌────────▼────────┐    ┌────────▼────────────────────▼────────┐          │
│  │ ProtectService  │    │        CameraService (existing)       │          │
│  │  - WebSocket    │    │        - RTSP capture                 │          │
│  │  - Snapshots    │    │        - USB capture                  │          │
│  │  - Discovery    │    │        - Motion detection              │          │
│  └────────┬────────┘    └────────────────────┬─────────────────┘          │
│           │                                   │                            │
│  ┌────────▼────────┐                          │                            │
│  │ProtectEventHdlr │                          │                            │
│  │ - Filter events │                          │                            │
│  │ - Doorbell ring │                          │                            │
│  └────────┬────────┘                          │                            │
│           │                                   │                            │
└───────────┼───────────────────────────────────┼────────────────────────────┘
            │                                   │
            └─────────────┬─────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Unified Event Pipeline                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │                     EventProcessor (existing)                      │      │
│  │   - Queue events from all sources                                 │      │
│  │   - Call AIService for descriptions                               │      │
│  │   - Store events in database                                      │      │
│  │   - Trigger alert evaluation                                      │      │
│  └────────────────────────────┬─────────────────────────────────────┘      │
│                               │                                             │
│  ┌────────────────────────────▼─────────────────────────────────────┐      │
│  │                   CorrelationService (NEW)                        │      │
│  │   - Check for multi-camera event correlation                      │      │
│  │   - Group related events                                          │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          AI Provider Chain                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐                │
│  │  OpenAI  │──▶│   Grok   │──▶│  Gemini  │──▶│  Claude  │                │
│  │ GPT-4o   │   │  (NEW)   │   │  Flash   │   │  Haiku   │                │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘                │
│        │              │              │              │                       │
│        └──────────────┴──────────────┴──────────────┘                       │
│                            │                                                │
│                     Fallback on failure                                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Frontend (Unified View)                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │                    EventTimeline (enhanced)                       │      │
│  │   - All events from all camera sources                           │      │
│  │   - Source type badges (Protect/RTSP/USB)                        │      │
│  │   - Smart detection badges (Person/Vehicle/Package)              │      │
│  │   - Correlated event indicators                                  │      │
│  │   - Doorbell ring notifications                                  │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │                    Settings Page (enhanced)                       │      │
│  │   - UniFi Protect section                                        │      │
│  │     - Controller connection form                                 │      │
│  │     - Discovered cameras list                                    │      │
│  │     - Event type filters per camera                              │      │
│  │   - AI Providers section                                         │      │
│  │     - xAI Grok configuration (NEW)                               │      │
│  │     - Provider order configuration                               │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### Phase 2 Validation Checklist

- ✅ All PRD Phase 2 functional requirements (FR1-FR36) have architectural support
- ✅ All PRD Phase 2 non-functional requirements (NFR1-NFR16) addressed
- ✅ UniFi Protect integration architecture defined (service, WebSocket, API)
- ✅ Database schema extensions for Protect controllers and cameras
- ✅ xAI Grok provider integration path defined
- ✅ Multi-camera correlation service designed
- ✅ Coexistence architecture ensures RTSP/USB cameras unaffected
- ✅ WebSocket protocol extended for new event types
- ✅ Security considerations documented for credential storage
- ✅ Performance considerations documented for real-time events
- ✅ Phase 2 ADRs documented with rationale

---

**Phase 2 Architecture Update:**
- **Updated by:** BMad Architect Agent
- **Date:** 2025-11-30
- **PRD Reference:** `docs/PRD-phase2.md`
- **UX Reference:** `docs/ux-design-specification.md` (Section 10)
