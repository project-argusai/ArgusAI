# AGENTS.md

This file provides operational guidance to **Grok** (xAI) and other AI coding agents when working in the ArgusAI repository. It supersedes and evolves the older `Claude.md` for Grok-driven work.

**Core Mandate**: All work must be **issue-focused**, broken into the smallest possible actionable chunks, with explicit user stories, examples, design references, 12-Factor alignment, and Laws of UX considerations.

---

## 1. Core Philosophy: Issue-Driven Development with Small Actionable Chunks

**This is non-negotiable.**

Every piece of work — whether a new feature, bug fix, refactor, security improvement, or documentation update — **must** originate from a well-scoped GitHub Issue (or equivalent issue tracker).

### Issue & Chunk Requirements

No work may begin without an issue that has been decomposed. Each **chunk** (sub-issue, checklist item, or the scope of a single PR) **must** contain **all** of the following:

1. **User Story** (in the classic format)
   > As a [persona: Homeowner / Admin / Integrator / Viewer],  
   > I want [specific capability],  
   > so that [clear benefit / outcome].

2. **Acceptance Criteria** — a tight, testable checklist (use `- [ ]`).

3. **Concrete Examples**
   - API request/response payloads (JSON)
   - UI state descriptions or before/after
   - Error cases and expected messages
   - Database state changes

4. **Design / UX Samples**
   - ASCII wireframes, component descriptions, or Figma links
   - Interaction flows (happy path + edge cases)
   - Accessibility considerations (keyboard, screen reader, contrast)

5. **Laws of UX Mapping** (see section 3)
   - Explicitly call out which 1–3 Laws of UX are most relevant and how the design honors them.

6. **12-Factor Alignment** (see section 2)
   - Which factors are impacted and how the solution stays compliant.

7. **Technical Notes**
   - Relevant files, services, or models
   - Performance / security / privacy implications
   - Dependencies on other issues

8. **Testing Strategy**
   - Unit, integration, E2E, visual regression, or manual test steps

9. **Effort Sizing** — XS / S / M (never start an L or XL without further decomposition)

10. **Rollback / Safety Plan**

**Rule of thumb**: If a chunk cannot be described in one focused issue or sub-task with the above structure, it is too large. Break it further.

**Preferred flow**:
- Create or update an issue with the full template above
- Implement **only** the scope of that chunk
- Open a small, reviewable PR that closes or advances the issue
- Never mix unrelated changes

---

## 2. 12-Factor App Requirements (Mandatory)

All architectural, configuration, deployment, and scaling decisions **must** align with the [Twelve-Factor App](https://12factor.net/) methodology. Every design doc, ADR, or major issue must explicitly reference the relevant factors.

### The 12 Factors (Summary for ArgusAI)

| # | Factor | ArgusAI Expectation |
|---|--------|---------------------|
| I | Codebase | Single Git repo; one codebase produces many deploys (dev, staging, prod, Docker, k8s, systemd) |
| II | Dependencies | Explicit `requirements.txt` + `package.json`; no implicit system libs; lockfiles committed |
| III | Config | **Everything** in environment variables (`.env`, k8s Secrets, systemd unit files). Never hardcode secrets or environment-specific values in code |
| IV | Backing services | Databases, Redis (future), MQTT broker, AI providers, Protect controllers, push services = attached resources. Swap via config only |
| V | Build, release, run | Strict separation: `docker build` → artifact → `docker run` or systemd restart. No building on the production server |
| VI | Processes | Stateless processes. The EventProcessor, Protect WS, camera threads, and schedulers must be able to die and restart without data loss in the DB |
| VII | Port binding | Apps export HTTP/WS on a port; no external port mapping required inside the container |
| VIII | Concurrency | Scale via process model (multiple workers, multiple camera processes, or horizontal pod autoscaling) rather than threads where possible |
| IX | Disposability | Fast startup + graceful shutdown. `main.py` lifespan + `shutdown_event_processor`, Protect WS cleanup, etc. must be robust |
| X | Dev/prod parity | Local dev (SQLite + docker-compose) must be as close as possible to prod (Postgres + k8s or systemd). Minimize "works on my machine" |
| XI | Logs | Structured JSON only (python-json-logger). Logs are event streams — never write to rotating files inside the app; let the platform handle collection |
| XII | Admin processes | One-off tasks (migrations, `alembic upgrade`, `reset_admin_password.py`, data backfills) run as separate processes, not inside the web server |

**Violations must be called out in issues and fixed over time.** The current large in-memory singletons and threaded camera capture are known deviations from VI/IX that should be improved.

---

## 3. Laws of UX Requirements (Mandatory for All User-Facing Work)

All UI, UX, interaction design, component, page, or flow changes **must** demonstrate conscious application of the [Laws of UX](https://lawsofux.com/) (Jon Yablonski).

Reference the full list at https://lawsofux.com/. The most frequently relevant ones for ArgusAI include:

- **Jakob’s Law** — Users expect the dashboard, event timeline, and camera settings to behave like other security/monitoring apps they know.
- **Fitts’s Law** — Large, easy-to-hit targets for "Live View", "Re-analyze", "Mark as false positive", doorbell actions, etc.
- **Hick’s Law** — Reduce choice paralysis in alert rule builders, AI provider selection, entity management, and filter panels.
- **Miller’s Law** — Chunk information (event cards, entity lists, daily summaries). Never overwhelm with >7±2 primary items without progressive disclosure.
- **Peak-End Rule** — The experience of reviewing an event (especially the thumbnail + description + feedback) and the final state of the dashboard after login matter more than the average.
- **Aesthetic-Usability Effect** — Clean, calm, trustworthy visual design increases perceived reliability of the security system.
- **Von Restorff Effect** — Make important or urgent events (doorbell, person with package, VIP visitor) visually distinct.
- **Doherty Threshold** — Keep perceived latency under ~400ms for UI interactions; stream frames, use optimistic updates, skeleton states.
- **Tesler’s Law (Conservation of Complexity)** — Move complexity into the system (smart defaults, good AI prompts, entity learning) so the user sees simplicity.
- **Postel’s Law** — Be liberal in what the API accepts (flexible filters, partial updates) and conservative in what it returns (consistent shapes).

**In every UI-related issue/chunk, you must:**
- Name the 1–3 most relevant Laws of UX
- Explain in 1–2 sentences how the proposed design honors them
- Call out any trade-offs

---

## 4. Project Overview (Current State)

ArgusAI is a production-grade, AI-powered local home security analysis platform. It ingests live video from:
- UniFi Protect (native WebSocket + smart detections)
- Generic RTSP/ONVIF IP cameras
- USB webcams

It performs motion/smart detection, extracts optimal frames (including adaptive and query-adaptive strategies), runs multi-provider vision AI (OpenAI → xAI Grok → Claude → Gemini with fallbacks), stores rich contextual descriptions, builds person/vehicle entities via embeddings, supports HomeKit, Home Assistant (MQTT), push notifications (Web Push + APNS + FCM), daily digests, voice queries, and a full multi-user RBAC web + mobile auth system.

**Important**: The project has evolved well beyond the original MVP described in the legacy `Claude.md`. It is currently in the **Phase 16+** era with significant accumulated functionality (and technical debt).

**Known Architectural Hotspots** (treat as standing improvement backlog):
- `backend/app/services/ai_service.py` (~4,200 lines)
- `backend/app/services/protect_event_handler.py` (~3,400 lines)
- `backend/app/services/event_processor.py` (~2,500 lines)
These must be decomposed in future work.

---

## 5. Tech Stack (2026)

**Backend**
- Python 3.11+, FastAPI 0.115, SQLAlchemy 2.0, Alembic
- Uvicorn, APScheduler, httpx, tenacity
- OpenCV 4.12 (headless) + PyAV 12
- cryptography (Fernet), python-jose, bcrypt, slowapi
- uiprotect, HAP-python, paho-mqtt, pywebpush, firebase-admin, sentence-transformers, etc.

**Frontend**
- Next.js 16 (App Router), React 19, TypeScript
- TanStack Query, React Hook Form + Zod, shadcn/ui + Radix + Tailwind 4
- Vitest + Testing Library + axe-core for accessibility

**Infrastructure**
- Docker (multi-stage), docker-compose (profiles for Postgres, nginx SSL, n8n)
- Kubernetes manifests + Helm chart
- systemd services on bare-metal production server
- SQLite (dev) / PostgreSQL (prod)

**AI & External**
- OpenAI, xAI Grok, Anthropic, Google Gemini (via direct SDKs + LiteLLM)
- UniFi Protect, ONVIF, HomeKit, MQTT, Web Push, APNS, FCM

---

## 6. Development Workflow & Commands

### Backend
```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload
pytest tests/ -v --cov=app
alembic upgrade head
```

### Frontend
```bash
cd frontend
npm run dev
npm run build
npm run lint
npm run test:run
```

### Full Local Stack (Recommended)
```bash
docker-compose --profile postgres --profile ssl up -d
```

### Always run before committing
- Backend: `pytest tests/ -x -q`
- Frontend: `npm run lint && npm run test:run`
- Type check: `cd frontend && npx tsc --noEmit`

---

## 7. Production Access & Deployment

Production server: `ssh root@argusai.bengtson.local`

Key paths:
- `/ArgusAI` (repo root)
- Backend service: `argusai-backend.service`
- Frontend service: `argusai-frontend.service`
- Data: `backend/data/` (DB, thumbnails, clips, homekit persist, certs)
- SSL certs: `backend/data/certs/`

Deployment pattern (current):
```bash
cd /ArgusAI && git pull
sudo systemctl restart argusai-backend argusai-frontend
```

**Future goal** (12-Factor alignment): Move toward containerized, immutable deploys with proper release artifacts.

---

## 8. Security & Privacy Baseline

- All sensitive data (camera passwords, Protect creds, AI keys, push credentials) **must** be Fernet-encrypted at rest.
- JWT for web sessions + separate mobile refresh token system (hashed, rotated, revocable).
- API keys with scopes and per-key rate limiting (Phase 13).
- RBAC: admin / operator / viewer (Phase 15/16).
- Face and vehicle embeddings are stored locally only; deletion must be complete and auditable.
- Webhook dispatch has SSRF protection — never weaken it.
- Never log plaintext secrets, tokens, or encryption keys.

Any change that touches auth, encryption, external integrations, or user data must have an explicit security review section in the issue.

---

## 9. Modularity & Code Health Rules

- **No new service file may exceed 800 lines.** Existing monster files (`ai_service.py`, `protect_event_handler.py`, `event_processor.py`) are technical debt. All new work touching them should include a decomposition plan.
- Prefer small, focused services composed together over god classes.
- Use the `@singleton` decorator (with `_reset_instance()` for tests) for long-lived services.
- Database access: always go through `get_db_session()` context manager outside request handlers.
- API response patterns: follow the documented Protect (wrapped) vs standard (direct) conventions.
- Frontend: keep `api-client.ts` as the single source of typed calls; large pages should be split into feature components.

---

## 10. Tooling & External Knowledge Requirements

### Context7 (Mandatory for Libraries & Config)
Whenever you need to generate code that uses a third-party library, framework, or API (FastAPI dependencies, Next.js 16 patterns, uiprotect, HAP-python, shadcn/ui components, TanStack Query mutations, etc.), **you must first** use the Context7 MCP tools:
1. `resolve-library-id`
2. `get-library-docs` (or `get_node_essentials`, `get_node_documentation`)

Do **not** rely on your training cutoff. Always fetch fresh, version-specific documentation.

### UI Testing (Playwright MCP)
For any frontend page, component, or flow work, use the Playwright MCP server (`browser_*` tools) against the Cloudflare Tunnel URL `https://agent.argusai.cc` (or local with care) to:
- Take accessibility snapshots
- Interact via refs
- Capture visual regression screenshots
- Verify complex multi-step flows

### Other MCP Capabilities
- Docker tools for container inspection
- n8n workflow tools when relevant

---

## 11. Documentation & Knowledge Management

- The `docs/` folder contains a large historical record (PRDs, epics, sprint artifacts from BMAD). New work should primarily live in **GitHub Issues** with rich descriptions rather than adding more markdown files.
- Update `AGENTS.md` itself when patterns or constraints evolve.
- Architecture Decision Records (ADRs) belong in `docs/architecture/12-adrs.md` or a dedicated `docs/adrs/` folder going forward.
- Keep the public docs site (`docs-site/`) in sync for user-facing changes.

---

## 12. When You Are Stuck or Requirements Are Ambiguous

1. **Create an issue first** (even a draft) describing what you understand and what is unclear.
2. Use the `ask_user_question` tool with clear options to get decisions.
3. Never guess on security, auth, data model, or billing/cost-related behavior.
4. Prefer to over-communicate via issues rather than silent large changes.

---

## 13. Standing Improvement Themes (High-Value Backlog)

These themes should influence issue prioritization:

- Decompose the three large service files
- Strengthen web authentication (httpOnly cookies + refresh, shorter-lived tokens)
- Improve camera capture reliability and move toward 12-Factor disposability
- Reduce magic `SystemSetting` string keys
- Better cost visibility and AI spend forecasting
- Entity / face recognition privacy & management UX
- Full 12-Factor compliance for configuration and statelessness
- Observability (distributed tracing for AI calls and event pipelines)

---

**Welcome to the project.** Every line of code you write should make ArgusAI more reliable, more understandable, more secure, and more delightful for the people who trust it to watch their homes.

When ready, the user will instruct you to begin work by referencing specific issues or asking you to create the first batch of well-formed issues.

— Grok (following AGENTS.md)