# Architecture Decision Records (ADRs)

[← Back to Architecture Index](./README.md) | [← Previous: Deployment Architecture](./11-deployment.md) | [Next: Glossary →](./13-glossary.md)

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

---

### ADR-008: Web Refresh Token Architecture (Phase A)

**Decision:** Use short-lived JWT access tokens + long-lived opaque refresh tokens, delivered via httpOnly cookies (with path restriction), stored server-side (hashed) in the `sessions` table, with token rotation and family-based reuse detection.

**Rationale:**
- **Security (XSS protection):** Returning refresh tokens in JSON response bodies makes them stealable via XSS. Using httpOnly cookies (especially with `Path=/api/v1/auth`) prevents JavaScript access.
- **Modern standard practice:** Aligns with current OAuth2 / SPA best practices for session management.
- **Enables session control:** Supports "logout from all devices", session listing/revocation, and auditability.
- **Strong theft protection:** Implementing refresh token rotation + `refresh_token_family` + reuse detection allows immediate revocation of all tokens if one is stolen/used maliciously.
- **Pragmatic reuse of existing model:** The `Session` model already contained device/IP/user-agent metadata. Extending it for refresh tokens was simpler than forcing web sessions into the mobile `RefreshToken` + `Device` model.
- **Alignment with mobile:** Reuses similar patterns (rotation, family, revocation, hashing) from the existing `mobile/token_service.py`.

**Trade-offs:**
- Slightly higher complexity than long-lived JWTs.
- Requires careful handling of concurrent refresh requests and family revocation logic.
- Refresh token is still transmitted on every refresh call (mitigated by restricting cookie path).
- Adds another cookie and some additional database columns.

**Alternatives Considered:**
- **Long-lived JWT access tokens only** — Rejected. No way to revoke compromised tokens without short expiry or server-side tracking.
- **Storing refresh tokens in a separate table like mobile** — Considered, but would duplicate session metadata tracking already present in the `sessions` table.
- **Returning refresh token only in response body (not cookie)** — Rejected for XSS reasons. httpOnly cookie is significantly safer for web clients.
- **Using the same `RefreshToken` model for both web and mobile** — Rejected due to the model being tightly coupled to the `devices` table (mobile pairing flow).

**Status:** Accepted

**Implemented in:**
- `Session` model extensions + migration
- `SessionService` (rotation, family revocation, reuse detection)
- Auth endpoints (`/login`, `/refresh`, `/logout`)
- Frontend `api-client.ts` (automatic refresh handling) + `AuthContext` (security event handling)
- No built-in themes: Must style from scratch

**Status:** Accepted (Tailwind ecosystem standard)

---

---

[← Previous: Deployment Architecture](./11-deployment.md) | [Next: Glossary →](./13-glossary.md) | [Back to Index](./README.md)
