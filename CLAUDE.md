# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) and any other AI coding agent working in the ArgusAI repository. **It is the single source of truth** — `AGENTS.md` is a thin pointer back to this file. (This supersedes the earlier Grok-specific `AGENTS.md`.)

Always use Context7 when you need code generation, setup/configuration steps, or library/API documentation. Use the Context7 MCP tools (`resolve-library-id` → `get-library-docs`) to fetch fresh, version-specific docs automatically rather than relying on training-cutoff knowledge — especially for FastAPI, Next.js 16, uiprotect, HAP-python, shadcn/ui, and TanStack Query.

---

## Project Overview

ArgusAI is a production-grade, AI-powered local home security analysis platform. It analyzes video feeds from UniFi Protect cameras, RTSP/ONVIF IP cameras, and USB webcams, detects motion and smart events, and generates natural-language descriptions using multi-provider vision AI (OpenAI, xAI Grok, Anthropic Claude, Google Gemini).

Beyond detection + description, it builds person/vehicle entities via embeddings, and supports HomeKit, Home Assistant (MQTT auto-discovery), push notifications (Web Push + APNS + FCM), daily digests, voice queries, and a multi-user RBAC web + mobile auth system.

**Current state**: The project has evolved well beyond the original MVP. It is in the **Phase 16+** era with significant accumulated functionality (and technical debt). When in doubt about scope, treat the code as the source of truth over older docs in `docs/`.

## Tech Stack

**Backend** (pinned in `backend/requirements.txt`)
- Python 3.11+, FastAPI 0.136 (`fastapi[standard]`) + SQLAlchemy 2.0.49+ + Alembic 1.18+
- Uvicorn 0.47, APScheduler 3.11, httpx, tenacity
- OpenCV 4.13 (headless) + PyAV 17 (secure `rtsps://` streams)
- cryptography 48 (Fernet), python-jose 3.5, bcrypt, slowapi
- uiprotect 10.4+, HAP-python 5, paho-mqtt 2.1, pywebpush 2.3, firebase-admin 7.4, sentence-transformers 5.5 (CLIP embeddings)
- AI SDKs: openai 2.30+, anthropic 0.102+, plus **litellm 1.83+** as the unified LLM gateway (fallbacks + cost tracking)
- **Database**: SQLite (dev default) or PostgreSQL (prod)

**Frontend** (`frontend/package.json`)
- Next.js 16 (App Router) + React 19.2 + TypeScript 6
- TanStack Query 5, React Hook Form 7 + Zod 4, shadcn/ui + Radix + Tailwind CSS 4, @dnd-kit
- Vitest 4 + Testing Library + axe-core 4 (accessibility)

**AI provider fallback order**: OpenAI GPT-4o mini → xAI Grok Vision → Anthropic Claude Haiku → Google Gemini Flash

**Infrastructure**: Docker (multi-stage) + docker-compose (profiles for Postgres, nginx SSL, n8n), Kubernetes manifests + Helm chart (`charts/`, `k8s/`), systemd services on the bare-metal production server.

## Build & Test Commands

### Backend
```bash
cd backend
source venv/bin/activate         # Activate virtualenv
uvicorn main:app --reload        # Run dev server (localhost:8000)
pytest tests/ -v                 # Run all tests (~160 test files)
pytest tests/test_services/test_camera_service.py -v  # Single test file
pytest tests/ --cov=app --cov-report=html  # Coverage report
alembic upgrade head             # Apply migrations
alembic downgrade -1             # Rollback one migration
```

### Frontend
```bash
cd frontend
npm run dev          # Dev server (localhost:3000)
npm run build        # Production build
npm run lint         # ESLint
npm run test:run     # Run Vitest once (CI mode)
```

### Full Local Stack (recommended)
```bash
docker-compose --profile postgres --profile ssl up -d
```

### Always run before committing
- Backend: `pytest tests/ -x -q`
- Frontend: `npm run lint && npm run test:run`
- Type check: `cd frontend && npx tsc --noEmit`

---

## Development Workflow & Standards

These standards are mandatory for substantial work. They keep changes small, reviewable, and aligned with the project's operational and UX goals.

### 1. Issue-Driven Development with Small Actionable Chunks

Substantial work should originate from a well-scoped issue, decomposed into the smallest reasonable chunks. A good chunk (the scope of a single PR) carries:

1. **User Story** — *As a [Homeowner / Admin / Integrator / Viewer], I want [capability], so that [outcome].*
2. **Acceptance Criteria** — a tight, testable `- [ ]` checklist.
3. **Concrete Examples** — API request/response JSON, UI before/after, error cases, DB state changes.
4. **Design / UX Notes** — wireframes or component descriptions, happy path + edge cases, accessibility (keyboard, screen reader, contrast).
5. **Laws of UX mapping** (see §3) for any user-facing work.
6. **12-Factor alignment** (see §2) for config/deploy/scaling work.
7. **Technical Notes** — relevant files/services/models, performance/security/privacy implications, dependencies.
8. **Testing Strategy** — unit / integration / E2E / visual regression / manual steps.
9. **Effort Sizing** — XS / S / M (decompose anything L/XL further).
10. **Rollback / Safety Plan**.

**Preferred flow**: scope the issue → implement only that chunk → open a small, reviewable PR → never mix unrelated changes. If a chunk can't be described in one focused issue with the above, it's too large — break it down.

### 2. 12-Factor Alignment (config, deploy, scaling)

All architectural, configuration, deployment, and scaling decisions should align with the [Twelve-Factor App](https://12factor.net/) methodology.

| # | Factor | ArgusAI expectation |
|---|--------|---------------------|
| I | Codebase | Single Git repo; one codebase → many deploys (dev, staging, prod, Docker, k8s, systemd) |
| II | Dependencies | Explicit `requirements.txt` + `package.json`; lockfiles committed; no implicit system libs |
| III | Config | **Everything** in env vars (`.env`, k8s Secrets, systemd units). Never hardcode secrets or env-specific values |
| IV | Backing services | DBs, MQTT broker, AI providers, Protect controllers, push services = attached resources, swappable via config |
| V | Build, release, run | Strict separation: `docker build` → artifact → run/restart. No building on the prod server |
| VI | Processes | Stateless processes. EventProcessor, Protect WS, camera threads, schedulers must die & restart without DB data loss |
| VII | Port binding | Apps export HTTP/WS on a port; no external port mapping required inside the container |
| VIII | Concurrency | Scale via the process model rather than threads where possible |
| IX | Disposability | Fast startup + graceful shutdown (`main.py` lifespan, `shutdown_event_processor`, Protect WS cleanup) |
| X | Dev/prod parity | Local dev (SQLite + docker-compose) as close as possible to prod (Postgres + k8s/systemd) |
| XI | Logs | Structured JSON only (python-json-logger). Logs are event streams; don't write rotating files inside the app |
| XII | Admin processes | One-offs (`alembic upgrade`, `reset_admin_password.py`, backfills) run as separate processes |

Known deviations (large in-memory singletons, threaded camera capture) are tracked in §13 — call out new violations in issues and improve over time.

### 3. Laws of UX (mandatory for user-facing work)

All UI/UX/interaction/component/page/flow changes should consciously apply the [Laws of UX](https://lawsofux.com/). For each UI change, name the 1–3 most relevant laws and explain in 1–2 sentences how the design honors them. Most frequently relevant here:

- **Jakob's Law** — dashboard, event timeline, and camera settings should behave like other security apps users know.
- **Fitts's Law** — large, easy targets for "Live View", "Re-analyze", "Mark as false positive", doorbell actions.
- **Hick's Law** — reduce choice paralysis in alert-rule builders, provider selection, entity management, filters.
- **Miller's Law** — chunk information (event cards, entity lists, digests); progressive disclosure beyond 7±2 items.
- **Peak-End Rule** — the event-review moment (thumbnail + description + feedback) and post-login dashboard state matter most.
- **Aesthetic-Usability Effect** — calm, trustworthy visuals raise perceived reliability of the system.
- **Von Restorff Effect** — make urgent events (doorbell, person-with-package, VIP) visually distinct.
- **Doherty Threshold** — keep perceived UI latency under ~400ms (stream frames, optimistic updates, skeletons).
- **Tesler's Law** — push complexity into the system (smart defaults, good prompts, entity learning) so the user sees simplicity.
- **Postel's Law** — be liberal in what the API accepts (flexible filters, partial updates), conservative in what it returns (consistent shapes).

---

## Architecture

### Event Processing Pipeline
```
Camera Capture → Motion Detection → Event Queue → AI Description → Database → Alert Rules → Webhooks/Notifications → WebSocket
(background)     (per frame)        (asyncio)     (multi-provider)             (eval + retry)                       (broadcast)
```

### Key Services (`backend/app/services/`)

The backend has ~96 service modules (~53k lines). Core ones:
- `camera_service.py` — RTSP/USB capture with background threading, auto-reconnect
- `protect_service.py` — UniFi Protect controller connection, WebSocket management, camera discovery
- `protect_event_handler.py` — Protect event parsing, smart-detection filtering, snapshot retrieval
- `motion_detection_service.py` — MOG2/KNN/frame-diff algorithms, detection zones
- `event_processor.py` — async queue pipeline, <5s p95 latency target, event correlation
- `ai_service.py` — provider abstraction / image preprocessing (much of the heavy lifting now lives in `ai_processing_coordinator.py`)
- `ai_processing_coordinator.py` — orchestrates the multi-provider AI description flow (fallbacks, retries, cost tracking)
- `entity_service.py` — person/vehicle entity building from embeddings
- `alert_engine.py` — rule evaluation, webhook dispatch with retry (SSRF-protected)
- `homekit_service.py` — HomeKit Accessory Protocol bridge
- `mqtt_service.py` / `mqtt_discovery_service.py` — Home Assistant integration + auto-discovery
- `push_notification_service.py` — Web Push / APNS / FCM
- `frame_extractor.py` — key-frame extraction from video clips
- `snapshot_service.py` — snapshot retrieval from Protect cameras

> **Architectural hotspots** (standing decomposition backlog — verified counts): `event_processor.py` (~2,540), `homekit_service.py` (~2,230), `ai_processing_coordinator.py` (~1,940), `entity_service.py` (~1,760), `protect_service.py` (~1,710), then `mcp_context.py`/`mqtt_service.py`/`alert_engine.py`/`frame_extractor.py` (~1,200–1,450). `ai_service.py` (~710) and `protect_event_handler.py` (~1,010) were already substantially decomposed.

### API Routes

All routes prefixed with `/api/v1`. Routers in `backend/app/api/v1/` include: `cameras`, `protect`, `events`, `ai`, `alert_rules`, `system`, `auth`, `mobile_auth`, `users`, `api_keys`, `devices`, `discovery`, `context`, `feedback`, `homekit`, `integrations`, `digests`, `summaries`, `push`, `notifications`, `system_notifications`, `motion_events`, `audio`, `voice`, `webhooks`, `logs`, `metrics`, `websocket`.

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

### API Response Format Standards

**Pattern 1: Wrapped Response (Protect API).** All `/api/v1/protect/*` endpoints wrap with metadata:
```json
{
  "data": { /* model or array of models */ },
  "meta": { "request_id": "uuid", "timestamp": "2025-12-30T00:00:00Z", "count": 5 }
}
```
Provides request tracking (`request_id`), generation timestamp, and `count` for lists.

**Pattern 2: Direct Model Response (Standard APIs).** All other endpoints return models directly:
```json
{ "id": "...", "name": "..." }
// or for lists:
[ { /* model */ }, { /* model */ } ]
```
Used for `/api/v1/cameras/*`, `/api/v1/events/*`, `/api/v1/alert_rules/*`, and all other endpoints.

**Frontend handling**: `api-client.ts` handles both automatically — Protect methods read `response.data`; standard methods use the response directly.

**New endpoints**: use Pattern 2 (direct) for simple CRUD; use Pattern 1 (wrapped) only when request tracking or pagination metadata is needed.

### Frontend Structure
- Pages: `frontend/app/` (App Router)
- Components: `frontend/components/` (`cameras/`, `events/`, `dashboard/`, `rules/`, `settings/`, `ui/`)
- State: React Context (Auth, Notifications, Settings) + TanStack Query (server state)
- API Client: `frontend/lib/api-client.ts` — the single source of typed API calls

## Database Models (`backend/app/models/`)

~35 models. Frequently touched ones:
- `Camera` — RTSP/USB/Protect config with encrypted passwords, `source_type` field
- `ProtectController` — UniFi Protect controller credentials and connection state
- `Event` — detected events with AI descriptions, thumbnails, correlation
  - `source_type` — 'rtsp', 'usb', or 'protect'
  - `protect_event_id` — native Protect event ID
  - `smart_detection_type` — person, vehicle, package, animal, ring
  - `is_doorbell_ring` — doorbell ring flag
  - `correlation_group_id` — links events from the same time window
  - `description_retry_needed` — AI retry-on-failure flag
- `MotionEvent`, `AlertRule`, `Notification`, `AIUsage`
- Phase 4+ models: `RecognizedEntity`, `FaceEmbedding`/`VehicleEmbedding`/`FrameEmbedding`/`EventEmbedding`, `EventFeedback`, `ActivitySummary`, `Device`, `ApiKey`, `RefreshToken`, `User`/`UserAuditLog`, `MqttConfig`, `PushSubscription`, `SystemSetting`. See `backend/app/models/` for the full list.

## Environment Variables

### Backend (.env)
```
DATABASE_URL=sqlite:///./data/app.db
ENCRYPTION_KEY=<fernet-key>  # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
DEBUG=True
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:3000,http://localhost:8000

# SSL Configuration
SSL_ENABLED=false           # Enable HTTPS
SSL_CERT_FILE=data/certs/cert.pem
SSL_KEY_FILE=data/certs/key.pem
SSL_REDIRECT_HTTP=true
SSL_MIN_VERSION=TLSv1_2     # TLSv1_2 or TLSv1_3
SSL_PORT=443
```
See `.env.example` for the complete, current list of variables.

### Frontend (.env.local)
```
NEXT_PUBLIC_API_URL=http://localhost:8000  # Use https:// when SSL is enabled
```

## SSL/HTTPS Configuration

ArgusAI supports SSL/HTTPS. **SSL is required for push notifications.**

**Quick setup**: place certs in `data/certs/`, set `SSL_ENABLED=true` + `SSL_CERT_FILE` + `SSL_KEY_FILE`, restart backend.

- `GET /api/v1/system/ssl-status` — SSL configuration and certificate info
- `GET /api/v1/push/requirements` — HTTPS status and push warnings

**Generate self-signed certs (dev):**
```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout data/certs/key.pem -out data/certs/cert.pem -subj "/CN=localhost"
```

---

## Key Patterns & Code Health

- **Backend**: service layer in `app/services/`, FastAPI dependency injection, async/await for I/O.
- **Frontend**: hooks in `hooks/`, Zod validation with React Hook Form, shadcn/ui components.
- **Logging**: structured JSON via python-json-logger; Prometheus metrics at `/metrics`.
- **No new service file should exceed ~800 lines.** The hotspots in §Architecture are technical debt — new work touching them should include a decomposition plan. Prefer small, composed services over god classes.
- Use the `@singleton` decorator from `backend/app/core/decorators.py` (with `_reset_instance()` for tests) for long-lived services.
- Database access: always go through the `get_db_session()` context manager (`backend/app/core/database.py`) outside request handlers.
- Frontend: keep `api-client.ts` as the single source of typed calls; split large pages into feature components.
- Follow the documented Protect (wrapped) vs standard (direct) API response conventions.

## Security & Privacy Baseline

- All sensitive data (camera passwords, Protect creds, AI keys, push credentials) **must** be Fernet-encrypted at rest.
- JWT for web sessions + a separate mobile refresh-token system (hashed, rotated, revocable).
- API keys carry scopes and per-key rate limiting; RBAC roles are admin / operator / viewer.
- Face and vehicle embeddings are stored locally only; deletion must be complete and auditable.
- Webhook dispatch has SSRF protection — **never weaken it.**
- **Never log plaintext secrets, tokens, or encryption keys.**

Any change touching auth, encryption, external integrations, or user data must include an explicit security-review note in the issue/PR. Never guess on security, auth, data-model, or billing/cost behavior — ask.

## Current Limitations
- Web auth could be hardened (move toward httpOnly cookies + shorter-lived tokens; see §13).
- Stores AI descriptions and thumbnails/clips, not full video archival.

---

## Phase 2 Architecture (UniFi Protect)

### Protect Event Flow
```
Protect Controller → WebSocket → ProtectService → ProtectEventHandler → SnapshotService → AI flow → Event DB
                                  (uiprotect)      (filter/dedupe)       (get image)       (describe)
```

### Camera Sources Coexistence
All three sources coexist and appear in a unified timeline (filterable by `source_type`):
- **Protect** — real-time events via WebSocket, smart detection types
- **RTSP** — polling-based frame capture, motion detection
- **USB** — direct capture, motion detection

## Phase 3 Architecture (Video Analysis)

### Analysis Modes
- **single_frame** — legacy snapshot analysis (fastest, lowest cost)
- **multi_frame** — extract 3–5 key frames from clips (balanced)
- **video_native** — send full video to providers that support it (highest quality)

### Video Processing Pipeline
```
Protect Event → Clip Download → Frame Extraction → AI Analysis → Description
                (uiprotect)     (PyAV/OpenCV)      (multi-image)
```

## Phase 4+ Capabilities (Context, Entities, Smart Home)

Much of the Phase 4 roadmap is now implemented: push notifications (Web Push + thumbnails, PWA), Home Assistant MQTT auto-discovery, temporal context / recurring-visitor recognition, activity summaries / daily digests, and user feedback (thumbs up/down) to improve descriptions.

Representative APIs:
```
GET  /api/v1/context/similar/{event_id}    # Find similar past events
GET  /api/v1/entities                      # List recognized people/vehicles
POST /api/v1/push/subscribe                # Register for push notifications
GET  /api/v1/summaries/daily               # Daily activity digest
POST /api/v1/events/{id}/feedback          # Submit feedback on a description
GET  /api/v1/integrations/mqtt/status      # MQTT connection status
```
Background docs: `docs/PRD-phase4.md`, `docs/epics-phase4.md`, `docs/architecture.md`.

---

## Production Server Access & Deployment

Claude Code has SSH access for troubleshooting and deployment:
```bash
ssh root@argusai.bengtson.local      # 10.0.1.46
```

### Server Details
- **Application path**: `/ArgusAI`
- **Backend venv**: `/ArgusAI/backend/venv`
- **Frontend**: HTTPS on port 3000 (custom SSL server); **Backend**: HTTP on port 8000 (proxied by frontend)
- Services: `argusai-backend.service`, `argusai-frontend.service` (`/etc/systemd/system/`)
- Frontend env: `/ArgusAI/frontend/.env.local`; SSL certs: `/ArgusAI/backend/data/certs/`
- Data: `backend/data/` (DB, thumbnails, clips, HomeKit persist, certs)

### Common Server Commands
```bash
# Deploy latest changes
cd /ArgusAI && git pull && sudo systemctl restart argusai-backend argusai-frontend

# Logs
sudo journalctl -u argusai-backend -f
sudo journalctl -u argusai-frontend -f

# Run Python in backend context
cd /ArgusAI/backend && source venv/bin/activate && python3 -c "..."

# Test API endpoints
curl -s http://127.0.0.1:8000/api/v1/cameras
curl -s -H "X-API-Key: <key>" http://127.0.0.1:8000/api/v1/events?limit=5
```

**Deployment is currently `git pull` + systemd restart.** Future 12-Factor goal: containerized, immutable deploys with proper release artifacts (no building on the prod server).

---

## BMAD Workflows

This project uses the BMAD Method. Key slash commands:
- `/bmad:bmm:workflows:dev-story` — execute a story implementation
- `/bmad:bmm:workflows:create-story` — create the next story from epics
- `/bmad:bmm:workflows:story-context` — assemble story context
- `/bmad:bmm:workflows:yolo` — create story + context, then implement
- `/bmad:bmm:agents:dev` — activate the dev agent

The `docs/` folder holds a large historical record (PRDs, epics, sprint artifacts). Prefer rich GitHub Issues over adding more markdown. Keep the public docs site (`docs-site/`) in sync for user-facing changes. ADRs go in `docs/architecture/` going forward.

---

## AI Agent UI Testing (Playwright MCP)

Full E2E UI testing is available via the Playwright MCP server.

- **Access URL (Cloudflare Tunnel)**: `https://agent.argusai.cc` (valid SSL). Local access needs an SSL-cert bypass that Docker containers don't support.

| Tool | Purpose |
|------|---------|
| `browser_navigate` | Navigate to a URL |
| `browser_snapshot` | Get accessibility tree (best for AI interaction) |
| `browser_take_screenshot` | Capture a visual screenshot |
| `browser_click` / `browser_type` / `browser_fill_form` | Interact via refs from the snapshot |
| `browser_wait_for` | Wait for text/element/time |
| `browser_evaluate` | Execute JavaScript on the page |
| `browser_press_key` / `browser_select_option` | Keyboard / dropdowns |

**Workflow**: `browser_navigate` → `browser_snapshot` (get refs) → interact with refs → verify with `browser_snapshot`/`browser_take_screenshot` → repeat for multi-step flows. Supports full E2E scenarios, form flows, visual regression, console/network inspection, and JS execution.

---

## Standing Improvement Themes (high-value backlog)

These should influence prioritization:
- Decompose the largest service files (see §Architecture hotspots).
- Strengthen web auth (httpOnly cookies + refresh, shorter-lived tokens).
- Improve camera-capture reliability; move toward 12-Factor disposability/statelessness.
- Reduce magic `SystemSetting` string keys.
- Better cost visibility and AI spend forecasting.
- Entity / face-recognition privacy & management UX.
- Observability (distributed tracing for AI calls and the event pipeline).

When requirements are ambiguous, prefer to over-communicate via an issue and ask for a decision rather than making a silent large change.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
