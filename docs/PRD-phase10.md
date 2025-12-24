# ArgusAI Phase 10 - Product Requirements Document

**Author:** Brent
**Date:** 2025-12-24
**Version:** 1.0
**Phase:** 10 - Stability, Containerization & Platform Foundation

---

## Executive Summary

Phase 10 focuses on three strategic pillars: **stabilizing the platform** by fixing remaining bugs, **enabling modern deployment** through containerization, and **laying the foundation for platform expansion** with native Apple apps infrastructure.

### What Makes This Phase Special

This phase transforms ArgusAI from a locally-deployed application into a production-ready, enterprise-capable platform. Docker/Kubernetes support enables consistent deployment across environments, while the Apple apps foundation opens ArgusAI to the mobile-first world.

---

## Project Classification

**Technical Type:** Web Application + Backend API
**Domain:** Home Security / Smart Home / IoT
**Complexity:** Medium-High (multi-platform, containerization, mobile foundation)

### Project Context

ArgusAI has matured through 9 phases, delivering:
- UniFi Protect integration with smart detection
- Multi-frame video analysis with AI descriptions
- Entity recognition (people, vehicles)
- Daily activity summaries
- Push notifications and PWA support
- MQTT/Home Assistant integration
- HomeKit integration
- n8n workflow automation foundation

Phase 10 addresses the remaining gaps to achieve production-grade stability and modern deployment capabilities.

---

## Success Criteria

### Platform Stability
- Zero known P2 bugs in production
- All UI components render correctly without scrolling/positioning issues
- User authentication fully functional including password management

### Deployment Flexibility
- ArgusAI deployable via single `docker-compose up` command
- Kubernetes deployment available with Helm chart
- Container images published to registry (GitHub Container Registry)

### Mobile Foundation
- Architecture design complete for native Apple apps
- API specification documented for mobile clients
- Cloud relay architecture defined (no implementation required this phase)

---

## Product Scope

### MVP - Core Deliverables

**Bug Fixes (Critical Path)**
1. Admin password change functionality
2. Events page infinite scroll loading
3. Today's Activity date filtering
4. Entity card scrolling behavior
5. Events page button positioning

**Containerization (Primary Feature)**
1. Docker support with multi-stage builds
2. docker-compose for local/single-host deployment
3. Kubernetes manifests (Deployment, Service, ConfigMap, PVC)
4. Helm chart for configurable K8s deployments
5. CI/CD workflow for container image builds

**UX Improvements**
1. Entity assignment directly from event cards
2. Manual entity creation
3. Feedback adjustment (edit/change previous feedback)

### Growth Features (Post-MVP)

**Apple Platform Foundation**
1. API specification for mobile clients (OpenAPI 3.0)
2. Cloud relay architecture document
3. Authentication flow design for mobile
4. Push notification token management for mobile

**AI Enhancements**
1. Local MCP server for enhanced AI context
2. Query-adaptive frame selection

### Vision (Future Phases)

- Native iOS/iPadOS/watchOS/tvOS applications
- Cloud relay service implementation
- Edge deployment on dedicated hardware
- Multi-tenant SaaS offering

---

## Functional Requirements

### Bug Fix Requirements (FR1-FR5)

**User Authentication**
- FR1: Users can change their admin password through the Settings UI
- FR2: Password change requires current password verification
- FR3: Password change provides clear success/error feedback

**Events Page**
- FR4: Events page loads additional events automatically when scrolling to bottom
- FR5: Infinite scroll triggers correctly at scroll threshold
- FR6: Loading indicator shows during pagination fetch
- FR7: Today's Activity section filters to current calendar day only
- FR8: Date filtering accounts for user's timezone

**UI/UX**
- FR9: Events page action buttons (Select All, Refresh, Delete) don't overlap navigation
- FR10: Entity cards scroll correctly within their containers
- FR11: Entity card content is fully accessible via scroll

### Containerization Requirements (FR12-FR25)

**Docker Support**
- FR12: Backend runs in Docker container with all dependencies
- FR13: Frontend runs in Docker container with production build
- FR14: Containers use multi-stage builds for minimal image size
- FR15: Data persists via Docker volumes (database, thumbnails, frames, certificates)
- FR16: Environment variables configure all runtime settings
- FR17: Health check endpoints work with container orchestration
- FR18: Containers support both SQLite and PostgreSQL databases

**Docker Compose**
- FR19: Single `docker-compose up` starts complete ArgusAI stack
- FR20: docker-compose includes optional PostgreSQL service
- FR21: docker-compose includes optional nginx reverse proxy with SSL
- FR22: Compose profiles allow selective service startup

**Kubernetes Support**
- FR23: Kubernetes Deployment manifests deploy backend and frontend
- FR24: Kubernetes Service exposes application endpoints
- FR25: ConfigMap and Secret manage configuration and credentials
- FR26: PersistentVolumeClaim provides data persistence
- FR27: Helm chart packages all K8s resources with configurable values
- FR28: Helm values support different environments (dev, staging, prod)

**CI/CD**
- FR29: GitHub Actions builds container images on push to main
- FR30: Container images tagged with version and git SHA
- FR31: Images pushed to GitHub Container Registry (ghcr.io)
- FR32: CI validates Kubernetes manifests with dry-run

### Entity Management Requirements (FR33-FR38)

**Entity Assignment**
- FR33: Users can assign/change entity directly from event cards without opening detail view
- FR34: Entity selection modal accessible from event card actions
- FR35: Quick entity assignment reduces clicks vs current workflow

**Manual Entity Creation**
- FR36: Users can create entities manually without triggering event
- FR37: Manual entity creation supports name, type (person/vehicle), description
- FR38: Vehicle entities support color, make, model fields for signature generation
- FR39: Manual entities can have reference image uploaded

**Feedback Adjustment**
- FR40: Users can modify previously submitted feedback on event descriptions
- FR41: Feedback can be changed between thumbs up/down after submission
- FR42: Correction text can be edited or removed
- FR43: Feedback history or "edited" indicator shown if feedback was changed

### Apple Platform Foundation Requirements (FR44-FR50)

**API Specification**
- FR44: OpenAPI 3.0 specification documents all API endpoints
- FR45: API spec includes authentication flows for mobile clients
- FR46: API spec defines push notification registration endpoints
- FR47: API spec versioned and published with documentation

**Architecture Design**
- FR48: Cloud relay architecture document defines secure tunnel approach
- FR49: Architecture addresses NAT traversal for remote access
- FR50: Architecture defines device pairing and authentication flow
- FR51: Architecture considers bandwidth optimization for thumbnails/video

---

## Non-Functional Requirements

### Performance

- NFR1: Docker containers start within 30 seconds
- NFR2: Container memory footprint under 1GB for backend, 512MB for frontend
- NFR3: Events page pagination loads within 500ms
- NFR4: Health check endpoints respond within 100ms

### Security

- NFR5: Container images scanned for vulnerabilities in CI
- NFR6: No secrets baked into container images
- NFR7: Password change validates password strength requirements
- NFR8: API authentication tokens have configurable expiration

### Scalability

- NFR9: Kubernetes deployment supports horizontal pod autoscaling
- NFR10: Database connection pooling configured for multi-replica deployment
- NFR11: Session state externalized for stateless replicas

### Accessibility

- NFR12: Entity assignment modal fully keyboard navigable
- NFR13: Manual entity creation form has proper ARIA labels
- NFR14: Feedback adjustment controls accessible via screen reader

### Integration

- NFR15: Docker deployment compatible with existing UniFi Protect connections
- NFR16: Kubernetes deployment supports external PostgreSQL
- NFR17: Container networking allows MQTT broker connectivity

---

## Implementation Planning

### Epic Breakdown Required

This PRD will be decomposed into the following epics:

| Epic | Title | Stories | Priority |
|------|-------|---------|----------|
| P10-1 | Critical Bug Fixes | 5 | P1 |
| P10-2 | Docker Containerization | 6 | P2 |
| P10-3 | Kubernetes & Helm | 5 | P2 |
| P10-4 | Entity Management UX | 4 | P2 |
| P10-5 | Apple Platform Foundation | 4 | P3 |
| P10-6 | AI & Quality Improvements | 3 | P3 |

**Total: 6 Epics, ~27 Stories**

---

## References

- Product Brief: docs/product-brief.md
- Previous PRDs: docs/PRD-phase9.md, docs/prd.md
- Backlog: docs/backlog.md
- Architecture: docs/architecture/

---

## Next Steps

1. **Epic & Story Breakdown** - Run: `workflow create-epics-and-stories`
2. **Architecture Update** - Run: `workflow create-architecture` (for containerization additions)
3. **Sprint Planning** - Run: `workflow sprint-planning`

---

_This PRD captures Phase 10 of ArgusAI - transforming it from a locally-deployed application into a production-ready, containerized platform with foundations for mobile expansion._

_Created through BMAD workflow by Brent and AI facilitator._
