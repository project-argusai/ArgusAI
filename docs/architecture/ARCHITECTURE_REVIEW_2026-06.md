# ArgusAI — Senior Engineering Architecture Review

**Date:** 2026-06-27
**Author:** Reverse-engineering pass (new-engineer perspective)
**Scope:** Whole-system architecture, data flow, and a prioritized refactoring strategy.
**Constraint honored:** *No functional changes.* Recommendations and the one shipped
change (DB connection pooling) are strictly quality/scalability/maintainability upgrades.

> Method: the system was reverse-engineered bottom-up from the live code (backend
> `~59k` LOC across 119 service modules, FastAPI routers, and the Next.js frontend),
> with `file:line` evidence for every claim below. This document is the durable
> artifact; the shipped code change is `backend/app/core/{config,database}.py`.

---

## 1. Clean architecture breakdown

ArgusAI is a **stateful, single-process Python monolith** (FastAPI + asyncio) with a
Next.js 16 frontend, integrating cameras, vision-AI providers, and smart-home buses.

### 1.1 Layers (as they *should* be read)

```
┌─────────────────────────────────────────────────────────────────────┐
│  Frontend (Next.js 16 / React 19)                                     │
│   app/ (routes) → hooks/ (TanStack Query) → lib/api-client.ts         │
└───────────────────────────────┬─────────────────────────────────────┘
                                 │  HTTP/WS  (/api/v1/*)
┌───────────────────────────────▼─────────────────────────────────────┐
│  API layer  backend/app/api/v1/*.py  (27 routers)                     │
│   auth/RBAC deps → request validation → service calls → response      │
├───────────────────────────────────────────────────────────────────────
│  Service layer  backend/app/services/*  (~96 modules)                 │
│   ingestion · AI · entities · alerting · integrations (HK/MQTT/push)  │
├───────────────────────────────────────────────────────────────────────
│  Core  backend/app/core/  (db, config, decorators/singleton, crypto)  │
├───────────────────────────────────────────────────────────────────────
│  Data  SQLAlchemy 2.0 models (~35) → SQLite (dev) / PostgreSQL (prod) │
└───────────────────────────────────────────────────────────────────────
        Attached resources: Protect controllers, AI providers,
        MQTT broker, HomeKit bridge, push services (12-Factor IV)
```

### 1.2 The real data flow (event pipeline)

There are **two parallel ingestion paths that do *not* share their persistence tail** —
the single most important structural fact about this system:

**Path A — RTSP/USB (motion-driven), thread → asyncio → worker pool:**
1. `CameraCaptureWorker._capture_loop` — one **OS thread per camera** — reads frames into
   a bounded `queue.Queue(maxsize=4)` (`camera_capture_worker.py:93,376`; drop-oldest).
2. `CameraTaskManager._run_motion_detection_loop` — an **asyncio task per camera** — pulls
   frames via `camera_service.get_frame()` (`camera_task_manager.py:233`).
3. On motion, `MotionDetectionService.process_frame` (Lock-guarded singleton) → builds a
   `ProcessingEvent` → `EventProcessor.queue_event` → `asyncio.Queue.put_nowait`
   (`event_processor.py:435`).
4. `AIProcessingWorker.run` (N workers, `AIWorkerPool`) → `await event_queue.get()` →
   `_process_event` (`event_processor.py:525`): cost-cap → thumbnail → early embedding →
   AI description (semaphore-gated) → `_store_processed_event` → cost alerts → push → MQTT
   → HomeKit → embeddings.

**Path B — UniFi Protect (event-driven), fully self-contained:**
`ProtectEventHandler` consumes WebSocket events and calls
`ai_pipeline.submit_snapshot_for_analysis`, `storage_service.persist_protect_event`, and
`broadcaster.broadcast_event_created` **directly** (`protect_event_handler.py:408,455,468`).
**It never enters `queue_event` or the AI worker pool.**

Thread→loop handoff is via `run_coroutine_threadsafe`; loop→workers via one shared
`asyncio.Queue`; fan-out to WS/MQTT/HomeKit via fire-and-forget `asyncio.create_task`.

### 1.3 AI description subsystem

Entry `AIProcessingCoordinator.process_event` (`ai_processing_coordinator.py:667`) →
thumbnail → optional embedding → `_generate_ai_description` (`:1100`, OCR + semaphore) →
`ai_service.generate_description`. **Two competing provider stacks** are toggled by a
`use_litellm` flag:
- **Legacy/default:** `VisionAnalysisOrchestrator` owns provider order, circuit breaker
  (`AIResilienceService`), and a hand-rolled backoff loop over the clean
  `ai_providers/{openai,grok,claude,gemini}.py` strategy classes.
- **Parallel:** `LiteLLMProvider` re-implements fallback, retry, and cost via litellm's
  `Router`.

Cost is recorded per call into an `AIUsage` row (`ai_cost_and_usage_tracker.py:59-73`).

---

## 2. Critical problem areas (prioritized)

Severity = impact × likelihood for a production home-security system.

### P0 — Scalability: the app cannot be horizontally scaled
- **57 `@singleton` services**, an **in-process `asyncio.Queue`**, **per-camera OS threads**
  bound to one event loop, and **APScheduler jobs** all live in-process
  (`decorators.py:18`, `event_processor.py:211`, `camera_service.py:76`, `main.py:299`).
- Running ≥2 uvicorn workers / k8s replicas would **double-fire scheduled jobs** (cleanup,
  backups, digests) and contend on the singleton HomeKit bridge, Protect WS, and MQTT
  client. The app is effectively `WEB_CONCURRENCY=1`. *(Violates 12-Factor VI/VIII.)*
- **No DB connection-pool configuration** existed — `create_engine(url, echo, connect_args)`
  only. On Postgres that means no `pool_pre_ping` (stale-connection errors after idle) and
  an unbounded-by-intent default pool. **→ Fixed in this pass (see §4.1).**

### P0 — Correctness: alert rules are a dead stub on the motion path
- `event_processor.py:689` literally reads `# Evaluate alert rules (stub / Epic 5)`.
  RTSP/USB events **never** run `AlertEngine.evaluate_all_rules`; only the Protect path
  triggers alerts. This is a latent functional gap masquerading as code — flagged for the
  owner, **not** changed here (changing it *is* a behavior change).

### P1 — Concurrency: sync DB sessions held across `await`
- ~38 sites open `with get_db_session()` then `await` network I/O while the synchronous
  SQLAlchemy connection stays checked out (`event_processor.py:293`,
  `protect_event_handler.py:363-518`). Pins a pooled connection for the full I/O duration
  and risks interleaved use of one `Session` across suspended tasks.
- `SessionLocal()` is also called **raw** (outside the context manager) in 10+ files
  (`event_processor.py` alone ~9×), bypassing rollback/close guarantees → connection leaks
  on early return.

### P1 — Performance: blocking CPU on the event loop + backoff blows the SLA
- `cv2.imencode` and PIL encode / `b64decode` run **synchronously** in async paths
  (`ai_processing_coordinator.py:1312,1319`, `vision_analysis_orchestrator.py:426-509`) —
  no `asyncio.to_thread`. Under concurrency these stall the loop.
- Retry backoff is a fixed `2/4/8s asyncio.sleep` against a **5000 ms** p95 SLA — a single
  retry blows the latency target (`vision_analysis_orchestrator.py:534`).

### P2 — Maintainability: god classes and god modules
Every one of these exceeds the project's own **800-line rule**:

| File | LOC | Concerns mashed together |
|---|---|---|
| `api/v1/system.py` | ~3,972 | 27 endpoints + 12 inline admin checks |
| `lib/api-client.ts` | ~3,129 | 168 methods, one file |
| `api/v1/events.py` | ~3,243 | — |
| `event_processor.py` | ~2,540 | ingest + AI orchestration + MQTT + HK + push |
| `homekit_service.py` | ~2,233 | HAP lifecycle + **6 copy-pasted sensor state machines** |
| `ai_processing_coordinator.py` | ~1,940 | AI + embeddings + MQTT + HK + push |
| `entity_service.py` | ~1,760 | matching + CRUD + linking + file IO |
| `protect_service.py` | ~1,710 | connection + WS + discovery + broadcasting |

### P2 — Duplicate logic (DRY violations with 2+ sites)
- **Exponential-backoff reconnect** reimplemented in `protect_service.py:819` and
  `mqtt_service.py:727` (identical algorithm).
- **Two persistence/broadcast tails** for events (Protect handler vs `event_processor`),
  including duplicated MQTT publish + thumbnail generation
  (`event_processor.py:744` vs `ai_processing_coordinator.py:1769`).
- **AI cost constants** duplicated across 4 provider classes + litellm, with Gemini using
  inline magic numbers (`ai_providers/*.py`, `gemini_provider.py:59,117`).
- **Image preprocessing** `_preprocess_image` vs `_preprocess_image_bytes` ~95% identical
  (`vision_analysis_orchestrator.py:426,472`).
- **Inline admin checks** `if current_user.role != ADMIN` repeated 12× in `system.py`
  while `users.py` already uses the declarative `Depends(require_role(ADMIN))`. *(Also an
  authz-correctness risk — a forgotten check is a privilege-escalation bug.)*
- **~28 magic `SystemSetting` string keys** across 56 call sites, no central enum.

---

## 3. Refactoring strategy (sequenced, all behavior-preserving)

Ordered by value-to-risk. Each is a *pure* refactor — same inputs → same outputs.

**Wave 1 — Foundations (low risk, high leverage):**
1. **DB pool configuration** *(shipped, §4.1)* — `pool_pre_ping`, `pool_recycle`, and
   env-driven `pool_size/max_overflow/timeout` for Postgres.
2. **`core/settings_keys.py`** — a `SettingKeys` `StrEnum` of the ~28 setting keys; values
   equal today's strings, so call-site migration is mechanical and verifiable.
3. **`core/backoff.py`** — one `reconnect_with_backoff()` utility; migrate the two reconnect
   loops (`protect_service.py:819`, `mqtt_service.py:727`) onto it.
4. **`api/v1/responses.py`** — relocate `create_meta`/envelope out of `protect.py:81`.

**Wave 2 — Concurrency & performance (medium risk, needs tests):**
5. **Scope sessions to sync work only** — fetch → close → *then* `await`. Start with the 38
   await-spanning sites; replace raw `SessionLocal()` with `get_db_session()`.
6. **Offload encoding to threads** — wrap `cv2.imencode`/PIL/`b64decode` in `asyncio.to_thread`.
7. **Track fire-and-forget tasks** — a `TaskRegistry` so `create_task` fan-out is bounded
   and tasks aren't GC'd mid-flight.

**Wave 3 — Decomposition (mechanical, high test coverage required):**
8. **Parameterize the HomeKit sensor** — collapse the 6 trigger/timer/coroutine/clear copies
   (`homekit_service.py:957-1685`) into one `DetectionSensor`. Largest single dedup win.
9. **Split god services along their seams** — `entity_service` → `EntityMatcher /
   EntityRepository / EntityEventLinker / EntityImageStore`; `protect_service` →
   `ConnectionManager / EventListener / CameraDiscovery / StatusBroadcaster`;
   `mcp_context` → `ContextGatherer / ContextFormatter`.
10. **Unify the two ingestion tails** into one `EventFinalizer` so Protect and motion events
    share identical persist/WS/MQTT code.

**Wave 4 — Scalability (architectural, schedule deliberately):**
11. **Leader-gate replica-unsafe singletons** — wrap APScheduler/HomeKit/Protect-WS/MQTT
    init behind `ENABLE_BACKGROUND_JOBS` so web replicas can scale while one leader runs
    background work (first real step toward 12-Factor VIII).
12. **Externalize the event queue** (Redis/broker) for durability + cross-process fan-out.
13. **Collapse the dual AI provider stacks** — pick the orchestrator path, retire litellm
    duplication (or vice-versa); single `PROVIDER_PRICING` table.

**Refactoring guardrails:** each wave behind its own PR; characterization tests captured
*before* touching god classes; `pytest -x -q` + `tsc --noEmit` + `npm run test:run` green
before merge; security note required for the `system.py` authz dedup (#5-adjacent).

---

## 4. Production-grade code delivered this pass

### 4.1 Database connection pooling (`backend/app/core/{config,database}.py`)

The highest value-to-risk fix and the prerequisite for any horizontal scaling. Added
env-driven pool settings whose **defaults equal SQLAlchemy's own defaults**, so existing
behavior is unchanged, while production gains stale-connection resilience and a bounded pool.

- `config.py`: `DB_POOL_SIZE/MAX_OVERFLOW/POOL_TIMEOUT/POOL_RECYCLE/POOL_PRE_PING`.
- `database.py`: `pool_pre_ping` + `pool_recycle` applied to all engines; `pool_size/
  max_overflow/pool_timeout` applied to **non-SQLite only** (SQLite is single-writer).

Verified: SQLite engine builds (`QueuePool`, `pre_ping=True`), `SELECT 1` round-trips, and
the Postgres branch constructs lazily (local failure is only the missing `psycopg2` driver,
which is prod-pinned). No behavior change for the dev SQLite default.

Everything in §3 beyond §4.1 is **recommended, not yet applied** — deliberately, to honor
the "no functional change" constraint and keep each refactor independently reviewable.
