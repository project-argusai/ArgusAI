# ArgusAI — Production Deployment Architecture & Runbook

**Date:** 2026-06-27
**Author:** DevOps readiness pass
**Audience:** Operators deploying ArgusAI to a real production environment.

> This document delivers the six requested artifacts — infrastructure architecture,
> deployment workflow, CI/CD pipeline, Docker/Kubernetes setup, monitoring strategy, and a
> production checklist — grounded in the repo's existing assets (`backend/Dockerfile`,
> `frontend/Dockerfile`, `docker-compose.yml`, `k8s/`, `charts/argusai/`,
> `.github/workflows/`). Concrete fixes shipped this pass are listed in §8.

---

## 0. The one constraint that shapes everything

The backend is a **stateful single-process singleton**: 57 `@singleton` services, an
in-process `asyncio.Queue`, one OS thread per camera bound to a single event loop,
in-process APScheduler jobs, and singleton HomeKit/Protect-WS/MQTT clients. **Running >1
backend replica double-fires scheduled jobs and double-consumes Protect events.**

➡️ **The backend runs at `replicas: 1` with a `Recreate` strategy. The frontend (stateless
Next.js) scales freely.** True backend horizontal scaling requires the web/worker split in
§6. Every decision below honors this.

---

## 1. Infrastructure architecture

```
                              Internet / LAN
                                    │  HTTPS (443)
                          ┌─────────▼──────────┐
                          │  Ingress / nginx   │  TLS termination, WS upgrade,
                          │  (cert-manager)    │  proxy-body-size for snapshots
                          └─────┬──────────┬───┘
                  /api, /ws ────┘          └──── / (UI)
                          │                      │
                ┌─────────▼────────┐    ┌────────▼─────────┐
                │ argusai-backend  │    │ argusai-frontend │
                │  Deployment      │    │  Deployment      │
                │  replicas: 1     │    │  replicas: 1..N  │ ← HPA-eligible
                │  Recreate        │    │  RollingUpdate   │
                │  PDB maxUnavail=0│    │  PDB minAvail=1  │
                └───┬───────┬──────┘    └──────────────────┘
       RWO PVC ─────┘       │ scrape /metrics
   (thumbnails, clips,      │
    homekit persist, certs) │
                 ┌──────────▼───────────┐   ┌───────────────────────────┐
                 │ Prometheus + Grafana │   │ Attached resources (12-F IV)│
                 │ Alertmanager         │   │ • PostgreSQL (managed)      │
                 └──────────────────────┘   │ • MQTT broker               │
                                            │ • AI providers (OpenAI/xAI/ │
                                            │   Anthropic/Gemini)         │
                                            │ • UniFi Protect controllers │
                                            │ • Push (WebPush/APNS/FCM)   │
                                            └───────────────────────────┘
```

**Environments:** `staging` (mirror, auto-deploy) → `production` (manual approval). Each is a
namespace (`argusai-staging` / `argusai`) with its own secrets and managed Postgres.

**State & storage:**
- **PostgreSQL** (managed/external) — *not* SQLite — for any real deploy. SQLite is dev-only.
- **RWO PVC** at `/app/data` for thumbnails, clips, HomeKit persist, and certs. RWO is why
  the backend uses `Recreate` (a surge pod can't co-mount the volume).
- **Secrets** (Fernet key, JWT secret, AI keys) via **External Secrets / SealedSecrets / CSI
  driver** — never committed. `k8s/secret.yaml` and `values.yaml` ship empty placeholders.

---

## 2. Deployment workflow (build-once / promote)

```
 commit → PR ──► CI (lint, test, typecheck, migration check)         [ci.yml]
   merge to main ──► build multi-arch images, push ghcr by sha+semver [docker.yml]
   tag / GitHub Release ──► DEPLOY pipeline                           [deploy.yml]
        │
        ├─ scan (Trivy HIGH/CRITICAL = fail) + SBOM + SARIF
        ├─ staging: alembic upgrade (Job) → helm upgrade --atomic → smoke /health
        ├─ ⏸ manual approval (Environment: production, required reviewers)
        ├─ production: alembic upgrade (Job) → helm upgrade --atomic → verify /health
        └─ on failure: helm rollback (automatic)
```

**Principles:** build the image **once**, promote the **same digest** staging→prod (12-Factor
V). Migrations run as a **gate** (a completed k8s Job) *before* the app rolls. `helm
upgrade --atomic` auto-rolls-back a failed release. Approvals and secrets live in GitHub
**Environments**, not in the workflow file.

**Rollback:** `helm rollback argusai <REV> -n argusai --wait`. Because migrations run
separately, keep them **backward-compatible** (expand/contract) so an app rollback never
faces a schema it can't read.

---

## 3. CI/CD pipeline

### Today (assessed)
- **`ci.yml`** — backend pytest+coverage, frontend lint/typecheck/test → Codecov. *Gaps:* no
  lint/mypy for backend, no migration check, no `concurrency` guard, a plaintext fallback key.
- **`docker.yml`** — multi-arch Buildx, GHA cache, semver/sha/latest tags → ghcr, plus
  `kubectl --dry-run` + `helm lint`. *Gaps:* no image scan, no SBOM, no signing; frontend
  bakes `NEXT_PUBLIC_API_URL=localhost`.
- **CD — none.** Images are pushed but nothing consumes them; prod is hand-deployed by SSH +
  `git pull` + `systemctl restart`. **This is the biggest gap.**

### Shipped this pass — `.github/workflows/deploy.yml`
A production CD pipeline: **scan → staging (migrate+deploy+smoke) → approval → prod
(migrate+deploy+verify) → auto-rollback**, with `concurrency` (no overlapping prod deploys),
OIDC-ready `id-token` permission, and GitHub Environments for approvals.

### Recommended CI hardening (follow-ups, not yet applied)
1. Add to `ci.yml`: `concurrency: {group: ci-${{github.ref}}, cancel-in-progress: true}`;
   backend `ruff`/`mypy`; an `alembic upgrade head` check against an ephemeral Postgres service.
2. Add to `docker.yml`: Trivy scan at build, `anchore/sbom-action`, `cosign` signing + provenance.
3. Fix the frontend image's `NEXT_PUBLIC_API_URL` to the public URL (build arg per environment).

---

## 4. Docker / Kubernetes setup

### Docker (assessed — already solid)
Both images are **multi-stage, non-root, with HEALTHCHECKs**; frontend uses Next.js
`output: standalone`; `.dockerignore` files exclude secrets/data. **Recommended hardening:**
- Pin base images by **digest**; replace built-image `:latest` with release tags.
- Install **CPU-only torch** (`--index-url …/cpu`) in `backend/Dockerfile` — cuts GBs of CUDA.
- Run backend under **gunicorn + uvicorn workers** with `--proxy-headers`; add `STOPSIGNAL`.
- Remove `changeme` default passwords and the n8n repo `rw` mount from `docker-compose.yml`.

### Kubernetes / Helm (fixed this pass)
| Concern | Before | After (shipped) |
|---|---|---|
| Probe path | `/api/v1/system/health` (**404 — route doesn't exist**) | `/health` (real, `main.py:1105`) |
| Backend strategy | `RollingUpdate maxSurge:1` (**RWO deadlock**) | `Recreate` |
| Startup | none → slow boot trips liveness | `startupProbe` (≤150s for CLIP/WS init) |
| Grace period | 30s (truncates 30s queue drain) | 45s (drain + cameras + buffer) |
| Disruptions | no PDB | `PodDisruptionBudget` (backend `maxUnavailable:0`, frontend `minAvailable:1`) |
| Autoscaling | undefined | explicit: backend HPA **disabled**, frontend HPA opt-in |

Applies to **both** `k8s/` raw manifests and the `charts/argusai` Helm chart (helm lint passes).

**Still recommended (not yet applied):** `readOnlyRootFilesystem: true` with explicit writable
mounts; a `NetworkPolicy` restricting backend ingress to frontend + ingress controller; a
`preStop` sleep to let the LB stop sending traffic before drain; the frontend container
`securityContext` in the raw manifests.

---

## 5. Monitoring strategy

The app **already exports rich Prometheus metrics** (`backend/app/core/metrics.py`, scrape
`/metrics`): HTTP rate/latency, `events_processed_total`, **`event_queue_depth`**,
`ai_api_duration_seconds`, `ai_api_cost_total`, `ai_circuit_breaker_state`,
`protect_ws_connected`, plus camera/alert/push/MQTT/HomeKit and `psutil` system metrics.
Logging is **structured JSON with `request_id` correlation** (`logging_config.py`).

### Shipped this pass — `deploy/monitoring/argusai-alerts.yaml`
Recording rules + SLO alerts over the real metrics:
- **AI p95 latency > 5s** (the event-pipeline SLO) · **HTTP 5xx > 1%** · **backend down**
- **event_queue_depth** backlog (>50/5m warn, >200/1m critical — overflow drops events)
- **circuit breaker OPEN** · **Protect WS disconnected** · **memory > 90% of limit**

### SLOs to adopt
| SLO | Target | Source metric |
|---|---|---|
| AI description latency | p95 < 5s | `ai_api_duration_seconds` |
| API availability | 5xx < 1% | `http_requests_total` |
| Event pipeline | queue depth bounded, 0 drops | `event_queue_depth` |
| Protect liveness | WS connected | `protect_ws_connected` |

### Recommended observability follow-ups (app-side)
- **Split liveness vs readiness:** keep `/health` (static 200, liveness) and add a `/readyz`
  that checks DB `SELECT 1`, queue depth, and MQTT/Protect state, returning 503 when degraded
  so the LB drains the pod. Then point the **readinessProbe** at `/readyz`.
- **Stop writing rotating log files** (`logging_config.py:204,218`) — emit JSON to **stdout**
  only (12-Factor XI); gate file handlers behind an opt-in env for bare-metal.
- **Add an explicit SIGTERM handler** and keep `terminationGracePeriodSeconds` (45s) ≥ the
  in-process drain; add `3.0`/`4.0` buckets to `ai_api_duration_seconds` for a sharp p95-at-5s.
- Ship a **Grafana dashboard** over these metrics (the data exists; the dashboard does not).

---

## 6. Reliability, downtime, and scaling

**Reduce downtime risk:**
- Migrations as a **gate** + **expand/contract** schema changes → safe rollback.
- `helm upgrade --atomic` + post-deploy `/health` verify + auto `helm rollback`.
- `Recreate` for the singleton backend avoids rollout deadlock; **PDB** prevents node-drain
  surprises; **startupProbe** prevents slow-boot crash loops.
- Brief backend downtime during `Recreate` is the current trade-off — accept it, or implement
  the split below to eliminate it.

**Path to real horizontal scaling (future, sequenced):**
1. **Leader flag** — gate APScheduler/HomeKit/Protect-WS/MQTT behind `ENABLE_BACKGROUND_JOBS`
   so only one pod runs them.
2. **Split web vs worker** — stateless API Deployment (HPA-eligible) + a single worker
   Deployment owning the pipeline/integrations.
3. **Externalize the queue** (Redis/RabbitMQ) for durability + cross-process fan-out; move off
   the RWO PVC to object storage (S3) for thumbnails/clips.
   Until (1)–(3) land, **backend HPA stays disabled** (enforced in `values.yaml`).

---

## 7. Production deployment checklist

**Pre-flight (once per environment)**
- [ ] Managed **PostgreSQL** provisioned; `DATABASE_URL` set (not SQLite).
- [ ] Secrets in External Secrets/SealedSecrets: `ENCRYPTION_KEY` (Fernet), `JWT_SECRET_KEY`,
      AI keys, VAPID, MQTT — **none committed**; app fails fast if `ENCRYPTION_KEY`/`JWT` unset.
- [ ] TLS: cert-manager issuer + `ingress.tls` populated (HTTPS is **required** for push).
- [ ] `CORS_ORIGINS` set to the real frontend origin; frontend image built with the public
      `NEXT_PUBLIC_API_URL`.
- [ ] RWO `PersistentVolumeClaim` bound; storage class supports it.
- [ ] GitHub Environments `staging`/`production` created; `production` has required reviewers;
      cluster credentials (OIDC or `KUBECONFIG`) set per environment.
- [ ] Prometheus scraping `/metrics`; `deploy/monitoring/argusai-alerts.yaml` loaded;
      Alertmanager routing configured.

**Per release**
- [ ] CI green (tests, lint, typecheck, migration check).
- [ ] Image built + pushed by sha/semver; **Trivy scan clean** (no HIGH/CRITICAL); SBOM attached.
- [ ] DB migration is **backward-compatible** (expand/contract).
- [ ] Deploy to **staging**; migration Job completes; smoke `/health` 200; manual UI sanity.
- [ ] **Approve** production in the GitHub Environment.
- [ ] Production migration Job completes; `helm upgrade --atomic` succeeds; rollout healthy.
- [ ] Post-deploy: `/health` 200, queue depth normal, AI p95 < 5s, no new 5xx/alerts (~15 min).

**Rollback (if needed)**
- [ ] `helm rollback argusai <REV> -n argusai --wait`.
- [ ] Confirm schema compatibility (expand/contract guarantees app N-1 reads schema N).
- [ ] Verify `/health`, alerts clear; post-mortem.

---

## 8. Changes shipped this pass (validated)

| File | Change |
|---|---|
| `k8s/backend-deployment.yaml` | probe path → `/health`; `Recreate`; `startupProbe`; grace 45s |
| `charts/argusai/templates/backend-deployment.yaml` | same, parameterized via values |
| `charts/argusai/values.yaml` | `strategy`, `terminationGracePeriodSeconds`, `startupProbe`, PDB + autoscaling blocks |
| `k8s/poddisruptionbudget.yaml` *(new)* | backend `maxUnavailable:0`, frontend `minAvailable:1` |
| `charts/argusai/templates/poddisruptionbudget.yaml` *(new)* | Helm PDBs (toggleable) |
| `.github/workflows/deploy.yml` *(new)* | production CD: scan → staging → approval → prod → rollback |
| `deploy/monitoring/argusai-alerts.yaml` *(new)* | Prometheus recording rules + SLO alerts |

**Validation:** `helm lint` passes; `helm template` renders the new strategy/probes/PDBs; all
raw `k8s/*.yaml` and both new YAML files parse; alert metric names verified against
`metrics.py`. The critical fix — probes were pointing at a non-existent `/api/v1/system/health`
(404) — would have broken the first real k8s deploy and is now corrected to `/health`.

Everything in §3/§4/§5/§6 marked "recommended/follow-up" is intentionally **not** applied here
(app-code or supply-chain changes that warrant their own reviewed PRs), keeping this pass to
validated, infra-level, low-risk improvements.
