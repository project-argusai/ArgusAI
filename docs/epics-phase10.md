# ArgusAI Phase 10 - Epic Breakdown

**Author:** Brent
**Date:** 2025-12-24
**Phase:** 10 - Stability, Containerization & Platform Foundation
**PRD Reference:** [PRD-phase10.md](./PRD-phase10.md)

---

## Overview

This document provides the complete epic and story breakdown for ArgusAI Phase 10, decomposing the requirements from the PRD into implementable stories. Phase 10 focuses on bug fixes, Docker/Kubernetes containerization, entity management UX improvements, and laying the foundation for native Apple apps.

**Living Document Notice:** This is the initial version. It will be updated after Architecture workflow adds technical details to stories.

### Epic Summary

| Epic | Title | Stories | Priority | FRs Covered |
|------|-------|---------|----------|-------------|
| P10-1 | Critical Bug Fixes | 5 | P1 | FR1-FR11 |
| P10-2 | Docker Containerization | 6 | P2 | FR12-FR22 |
| P10-3 | Kubernetes & Helm | 4 | P2 | FR23-FR32 |
| P10-4 | Entity Management UX | 4 | P2 | FR33-FR43 |
| P10-5 | Apple Platform Foundation | 4 | P3 | FR44-FR51 |
| P10-6 | AI & Quality Improvements | 2 | P3 | Future backlog |

**Total: 6 Epics, 25 Stories**

---

## Functional Requirements Inventory

### Bug Fixes (FR1-FR11)
- **FR1:** Users can change their admin password through the Settings UI
- **FR2:** Password change requires current password verification
- **FR3:** Password change provides clear success/error feedback
- **FR4:** Events page loads additional events automatically when scrolling to bottom
- **FR5:** Infinite scroll triggers correctly at scroll threshold
- **FR6:** Loading indicator shows during pagination fetch
- **FR7:** Today's Activity section filters to current calendar day only
- **FR8:** Date filtering accounts for user's timezone
- **FR9:** Events page action buttons don't overlap navigation
- **FR10:** Entity cards scroll correctly within their containers
- **FR11:** Entity card content is fully accessible via scroll

### Docker Containerization (FR12-FR22)
- **FR12:** Backend runs in Docker container with all dependencies
- **FR13:** Frontend runs in Docker container with production build
- **FR14:** Containers use multi-stage builds for minimal image size
- **FR15:** Data persists via Docker volumes
- **FR16:** Environment variables configure all runtime settings
- **FR17:** Health check endpoints work with container orchestration
- **FR18:** Containers support both SQLite and PostgreSQL databases
- **FR19:** Single `docker-compose up` starts complete stack
- **FR20:** docker-compose includes optional PostgreSQL service
- **FR21:** docker-compose includes optional nginx reverse proxy with SSL
- **FR22:** Compose profiles allow selective service startup

### Kubernetes & Helm (FR23-FR32)
- **FR23:** Kubernetes Deployment manifests deploy backend and frontend
- **FR24:** Kubernetes Service exposes application endpoints
- **FR25:** ConfigMap and Secret manage configuration and credentials
- **FR26:** PersistentVolumeClaim provides data persistence
- **FR27:** Helm chart packages all K8s resources with configurable values
- **FR28:** Helm values support different environments
- **FR29:** GitHub Actions builds container images on push to main
- **FR30:** Container images tagged with version and git SHA
- **FR31:** Images pushed to GitHub Container Registry
- **FR32:** CI validates Kubernetes manifests with dry-run

### Entity Management (FR33-FR43)
- **FR33:** Users can assign/change entity directly from event cards
- **FR34:** Entity selection modal accessible from event card actions
- **FR35:** Quick entity assignment reduces clicks vs current workflow
- **FR36:** Users can create entities manually without triggering event
- **FR37:** Manual entity creation supports name, type, description
- **FR38:** Vehicle entities support color, make, model fields
- **FR39:** Manual entities can have reference image uploaded
- **FR40:** Users can modify previously submitted feedback
- **FR41:** Feedback can be changed between thumbs up/down after submission
- **FR42:** Correction text can be edited or removed
- **FR43:** Feedback history or "edited" indicator shown

### Apple Platform Foundation (FR44-FR51)
- **FR44:** OpenAPI 3.0 specification documents all API endpoints
- **FR45:** API spec includes authentication flows for mobile clients
- **FR46:** API spec defines push notification registration endpoints
- **FR47:** API spec versioned and published with documentation
- **FR48:** Cloud relay architecture document defines secure tunnel approach
- **FR49:** Architecture addresses NAT traversal for remote access
- **FR50:** Architecture defines device pairing and authentication flow
- **FR51:** Architecture considers bandwidth optimization

---

## FR Coverage Map

| FR | Description | Epic | Story |
|----|-------------|------|-------|
| FR1-FR3 | Password change | P10-1 | 1.1 |
| FR4-FR6 | Infinite scroll | P10-1 | 1.2 |
| FR7-FR8 | Today's Activity filter | P10-1 | 1.3 |
| FR9 | Button positioning | P10-1 | 1.4 |
| FR10-FR11 | Entity card scroll | P10-1 | 1.5 |
| FR12-FR18 | Docker containers | P10-2 | 2.1-2.3 |
| FR19-FR22 | docker-compose | P10-2 | 2.4-2.6 |
| FR23-FR26 | K8s manifests | P10-3 | 3.1-3.2 |
| FR27-FR28 | Helm chart | P10-3 | 3.3 |
| FR29-FR32 | CI/CD for containers | P10-3 | 3.4 |
| FR33-FR35 | Entity assignment | P10-4 | 4.1 |
| FR36-FR39 | Manual entity creation | P10-4 | 4.2 |
| FR40-FR43 | Feedback adjustment | P10-4 | 4.3-4.4 |
| FR44-FR47 | API specification | P10-5 | 5.1-5.2 |
| FR48-FR51 | Cloud relay architecture | P10-5 | 5.3-5.4 |

---

## Epic P10-1: Critical Bug Fixes

**Goal:** Resolve all remaining P2 bugs to achieve platform stability.

**Value:** Users experience reliable functionality without unexpected errors. All UI components work correctly.

**Backlog Items:** BUG-012, BUG-013, BUG-014, BUG-015, IMP-010

---

### Story P10-1.1: Implement Admin Password Change

As a **user**,
I want **to change my admin password through the Settings UI**,
So that **I can maintain account security**.

**Acceptance Criteria:**

**Given** I navigate to Settings > Security or Account
**When** I view the password section
**Then** I see a password change form with current password, new password, and confirm password fields

**Given** I enter my current password correctly and a valid new password
**When** I submit the form
**Then** my password is updated in the database
**And** a success toast appears "Password updated successfully"
**And** my session remains active

**Given** I enter an incorrect current password
**When** I submit the form
**Then** an error message appears "Current password is incorrect"
**And** my password is not changed

**Given** I enter a weak new password
**When** I submit the form
**Then** an error message shows password requirements (minimum length, complexity)

**Prerequisites:** None

**Technical Notes:**
- Create `PUT /api/v1/auth/password` endpoint
- Verify current password with bcrypt compare
- Hash new password with bcrypt before storage
- Validate password strength (min 8 chars, mixed case, number)
- Add password change form to Settings page
- Backlog: BUG-012

---

### Story P10-1.2: Fix Events Page Infinite Scroll

As a **user**,
I want **events to load automatically as I scroll**,
So that **I can browse my event history without manual pagination**.

**Acceptance Criteria:**

**Given** I'm on the Events page with more events than initially displayed
**When** I scroll to near the bottom of the list
**Then** a loading indicator appears
**And** additional events are fetched and appended to the list
**And** scrolling continues smoothly

**Given** there are no more events to load
**When** I scroll to the bottom
**Then** no additional fetch is triggered
**And** a "No more events" message may appear

**Given** the next page of events fails to load
**When** an error occurs
**Then** an error message is shown
**And** a "Retry" button allows re-fetching

**Prerequisites:** None

**Technical Notes:**
- Check useInfiniteQuery hook implementation in events page
- Verify IntersectionObserver is configured correctly
- Ensure hasNextPage flag is set properly from API response
- Check if fetchNextPage is being called on scroll trigger
- Debug offset/limit pagination parameters
- Backlog: BUG-014

---

### Story P10-1.3: Fix Today's Activity Date Filtering

As a **user**,
I want **Today's Activity to show only today's events**,
So that **I get an accurate view of current day activity**.

**Acceptance Criteria:**

**Given** I view the Dashboard
**When** I look at the "Today's Activity" section
**Then** only events from the current calendar day are displayed
**And** events from yesterday or earlier are excluded

**Given** it's 11:59 PM
**When** midnight passes
**Then** the activity resets to show only new day's events
**And** yesterday's events no longer appear in Today's Activity

**Given** I'm in a different timezone than the server
**When** I view Today's Activity
**Then** filtering respects my local timezone
**And** "today" is based on my local date

**Prerequisites:** None

**Technical Notes:**
- Check dashboard API endpoint for date filtering logic
- Verify RecentActivity component passes correct date range
- Backend query should filter: `WHERE event_time >= start_of_today`
- Handle timezone by passing client timezone to API or filtering client-side
- Backlog: BUG-015

---

### Story P10-1.4: Fix Events Page Button Positioning

As a **user**,
I want **action buttons that don't overlap with navigation**,
So that **I can use both without visual interference**.

**Acceptance Criteria:**

**Given** I view the Events page on desktop (1024px+)
**When** I look at the action buttons (Select All, Refresh, Delete)
**Then** they are positioned below the page header
**And** they don't overlap with top-right navigation/user buttons
**And** there's clear visual separation (at least 16px gap)

**Given** I view the Events page on mobile
**When** I look at the action buttons
**Then** they're positioned appropriately for the viewport
**And** touch targets are at least 44x44px
**And** no overlap with other controls

**Prerequisites:** None

**Technical Notes:**
- Add margin-top to action bar: `mt-4` or `mt-6` (16px or 24px)
- Ensure header has fixed/known height for consistent spacing
- Test at viewport widths: 320px, 768px, 1024px, 1920px
- Adjust z-index if layering issues exist
- Backlog: IMP-010

---

### Story P10-1.5: Fix Entity Card Scrolling

As a **user**,
I want **entity cards to scroll correctly**,
So that **I can view all entity information**.

**Acceptance Criteria:**

**Given** I'm on the Entities page
**When** I view an entity card with overflow content
**Then** the content is scrollable within the card
**And** scrolling is smooth and responsive

**Given** an entity has many linked events
**When** I view the entity detail
**Then** I can scroll through all events
**And** scroll position is maintained when interacting

**Given** I'm on mobile
**When** I interact with entity cards
**Then** touch scrolling works correctly
**And** no content is cut off or inaccessible

**Prerequisites:** None

**Technical Notes:**
- Check ScrollArea component configuration in entity cards
- Verify CSS overflow properties (overflow-y: auto)
- Check container height constraints
- Test on both desktop and mobile devices
- May need to set explicit max-height on card content areas
- Backlog: BUG-013

---

## Epic P10-2: Docker Containerization

**Goal:** Enable ArgusAI deployment via Docker containers.

**Value:** Simplified deployment, reproducible environments, easier updates and rollbacks.

**Backlog Items:** FF-032

---

### Story P10-2.1: Create Backend Dockerfile

As a **developer**,
I want **a Docker container for the FastAPI backend**,
So that **I can deploy the backend consistently across environments**.

**Acceptance Criteria:**

**Given** the Dockerfile is built
**When** the container starts
**Then** the FastAPI backend runs successfully
**And** all Python dependencies are installed
**And** database migrations can be applied

**Given** the container is running
**When** I access the health endpoint
**Then** it returns a healthy status

**Given** I want to use PostgreSQL instead of SQLite
**When** I set the DATABASE_URL environment variable
**Then** the backend connects to PostgreSQL
**And** all features work correctly

**Prerequisites:** P10-1.1 (CI must pass)

**Technical Notes:**
- Use Python 3.11 slim base image
- Multi-stage build: builder stage for dependencies, runtime stage minimal
- Install system dependencies: ffmpeg, opencv libs
- Copy requirements.txt and install with pip
- Set proper PYTHONPATH and working directory
- ENTRYPOINT runs uvicorn with health checks
- Expose port 8000

---

### Story P10-2.2: Create Frontend Dockerfile

As a **developer**,
I want **a Docker container for the Next.js frontend**,
So that **I can deploy the frontend consistently**.

**Acceptance Criteria:**

**Given** the Dockerfile is built
**When** the container starts
**Then** the Next.js production build is served
**And** the frontend is accessible on port 3000

**Given** I need to configure the API URL
**When** I set NEXT_PUBLIC_API_URL environment variable
**Then** the frontend connects to the specified backend

**Prerequisites:** P10-2.1

**Technical Notes:**
- Use Node 20 alpine base image
- Multi-stage build: deps, builder, runner stages
- Install dependencies with npm ci
- Build production with npm run build
- Run with next start or standalone output
- Minimize image size with standalone output mode
- Expose port 3000

---

### Story P10-2.3: Configure Docker Volumes and Environment

As a **developer**,
I want **persistent storage and environment configuration for containers**,
So that **data survives container restarts and configuration is flexible**.

**Acceptance Criteria:**

**Given** the backend container is running with volumes
**When** the container is stopped and restarted
**Then** all database data persists
**And** all thumbnails and frames persist
**And** SSL certificates persist

**Given** I configure environment variables
**When** the container starts
**Then** all settings are applied from environment
**And** no secrets are baked into the image

**Prerequisites:** P10-2.1, P10-2.2

**Technical Notes:**
- Define volumes: data/app.db, data/thumbnails, data/frames, data/certs
- Environment variables: DATABASE_URL, ENCRYPTION_KEY, SSL_*, AI provider keys
- Document all environment variables in README
- Add .env.example file for reference
- Ensure ENCRYPTION_KEY is required (fail if not set)

---

### Story P10-2.4: Create docker-compose.yml

As a **user**,
I want **to deploy ArgusAI with a single docker-compose command**,
So that **setup is simple and quick**.

**Acceptance Criteria:**

**Given** I have Docker and docker-compose installed
**When** I run `docker-compose up -d`
**Then** both backend and frontend containers start
**And** the application is accessible at localhost
**And** data is persisted in named volumes

**Given** the containers are running
**When** I run `docker-compose down`
**Then** containers stop gracefully
**And** volumes are preserved
**And** `docker-compose up` restores the previous state

**Prerequisites:** P10-2.3

**Technical Notes:**
- Define services: backend, frontend
- Use build context for local development
- Use image references for production
- Define named volumes for persistence
- Configure internal network for service communication
- Add healthcheck for each service
- Default ports: 8000 (backend), 3000 (frontend)

---

### Story P10-2.5: Add PostgreSQL Service to docker-compose

As a **user**,
I want **optional PostgreSQL for production deployments**,
So that **I can use a robust database for larger installations**.

**Acceptance Criteria:**

**Given** I want to use PostgreSQL
**When** I run `docker-compose --profile postgres up`
**Then** PostgreSQL container starts alongside the app
**And** backend connects to PostgreSQL
**And** migrations are applied automatically

**Given** PostgreSQL is running
**When** I check the database
**Then** all tables are created correctly
**And** data is persisted in a named volume

**Prerequisites:** P10-2.4

**Technical Notes:**
- Add postgres service with profile: ["postgres"]
- Use postgres:16-alpine image
- Configure POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
- Backend DATABASE_URL points to postgres service
- Add volume for postgres data
- Include initialization script if needed

---

### Story P10-2.6: Add Nginx Reverse Proxy with SSL

As a **user**,
I want **optional nginx reverse proxy with SSL termination**,
So that **I can serve ArgusAI securely in production**.

**Acceptance Criteria:**

**Given** I want SSL/HTTPS
**When** I run `docker-compose --profile ssl up`
**Then** nginx container starts as reverse proxy
**And** HTTPS is available on port 443
**And** HTTP redirects to HTTPS

**Given** I have certificates in data/certs
**When** nginx starts
**Then** it uses my SSL certificates
**And** connections are properly secured

**Given** I use compose profiles
**When** I run without --profile ssl
**Then** nginx is not started
**And** I can access backend/frontend directly

**Prerequisites:** P10-2.5

**Technical Notes:**
- Add nginx service with profile: ["ssl"]
- Use nginx:alpine image
- Mount nginx.conf and certs volumes
- Configure upstream backends
- Add SSL configuration with TLS 1.2+
- Add HTTP to HTTPS redirect

---

## Epic P10-3: Kubernetes & Helm

**Goal:** Enable ArgusAI deployment on Kubernetes with Helm charts.

**Value:** Horizontal scaling, enterprise deployment, cloud-native operations.

**Backlog Items:** FF-032

---

### Story P10-3.1: Create Kubernetes Deployment Manifests

As a **developer**,
I want **Kubernetes manifests for ArgusAI**,
So that **I can deploy to any K8s cluster**.

**Acceptance Criteria:**

**Given** I have a Kubernetes cluster
**When** I apply the manifests with kubectl
**Then** backend and frontend Deployments are created
**And** pods start successfully
**And** health checks pass

**Given** the deployments are running
**When** I check pod status
**Then** all pods are in Running state
**And** readiness probes succeed

**Prerequisites:** P10-2.3

**Technical Notes:**
- Create k8s/ directory for manifests
- backend-deployment.yaml: replicas, resources, probes
- frontend-deployment.yaml: replicas, resources, probes
- Add resource requests/limits
- Configure liveness and readiness probes
- Use configurable image tags

---

### Story P10-3.2: Create Kubernetes Service and Config Resources

As a **developer**,
I want **Kubernetes Services and ConfigMaps**,
So that **applications can communicate and be configured**.

**Acceptance Criteria:**

**Given** manifests are applied
**When** I check services
**Then** backend and frontend Services exist
**And** they have correct selectors and ports

**Given** ConfigMap is applied
**When** pods start
**Then** configuration values are available as environment variables
**And** application uses the configured values

**Given** Secrets are applied
**When** pods start
**Then** sensitive values (ENCRYPTION_KEY, API keys) are available
**And** they're not visible in plain text in manifests

**Prerequisites:** P10-3.1

**Technical Notes:**
- backend-service.yaml: ClusterIP type, port 8000
- frontend-service.yaml: ClusterIP type, port 3000
- configmap.yaml: non-sensitive configuration
- secret.yaml: template with placeholder values
- PVC for data persistence
- Optional Ingress manifest

---

### Story P10-3.3: Create Helm Chart

As a **developer**,
I want **a Helm chart for ArgusAI**,
So that **deployment is templated and configurable**.

**Acceptance Criteria:**

**Given** the Helm chart is installed
**When** I run `helm install argusai ./charts/argusai`
**Then** all Kubernetes resources are created
**And** the application is running

**Given** I want to customize the deployment
**When** I provide custom values (--set or -f values.yaml)
**Then** the deployment reflects my configuration
**And** I can change replicas, resources, ingress, etc.

**Given** I want to upgrade
**When** I run `helm upgrade argusai ./charts/argusai`
**Then** the deployment is updated
**And** pods are rolled out gracefully

**Prerequisites:** P10-3.2

**Technical Notes:**
- Create charts/argusai/ directory structure
- Chart.yaml: name, version, appVersion
- values.yaml: defaults for all configurable options
- templates/: deployment, service, configmap, secret, pvc, ingress
- Add NOTES.txt for post-install instructions
- Support values for: replicas, resources, persistence, ingress, ssl

---

### Story P10-3.4: Add Container CI/CD Pipeline

As a **developer**,
I want **GitHub Actions to build and push container images**,
So that **releases are automated and consistent**.

**Acceptance Criteria:**

**Given** I push to the main branch
**When** the CI workflow runs
**Then** Docker images are built for backend and frontend
**And** images are tagged with version and git SHA
**And** images are pushed to ghcr.io

**Given** I create a release tag
**When** the CI workflow runs
**Then** images are tagged with the release version
**And** Helm chart version is updated

**Given** I open a pull request
**When** CI runs
**Then** Docker build is tested (no push)
**And** K8s manifests are validated with dry-run

**Prerequisites:** P10-3.3

**Technical Notes:**
- Add .github/workflows/docker.yml
- Use docker/build-push-action
- Login to ghcr.io with GITHUB_TOKEN
- Multi-platform build (linux/amd64, linux/arm64)
- Tag: latest, version, git-sha
- Add helm lint step
- Add kubectl dry-run validation

---

## Epic P10-4: Entity Management UX

**Goal:** Improve entity management workflows with direct assignment and manual creation.

**Value:** Faster entity management, fewer clicks, user control over entity creation.

**Backlog Items:** IMP-023, FF-031, IMP-018

---

### Story P10-4.1: Add Entity Assignment from Event Cards

As a **user**,
I want **to assign entities directly from event cards**,
So that **I don't need to open the event detail first**.

**Acceptance Criteria:**

**Given** I view an event card
**When** I click the entity action button
**Then** an entity selection modal opens
**And** I can search for existing entities
**And** I can select one to assign

**Given** I select an entity in the modal
**When** I confirm the selection
**Then** the event is linked to the selected entity
**And** the event card updates to show the entity
**And** a success toast appears

**Given** the event already has an entity
**When** I click the entity action button
**Then** I see options to "Change Entity" or "Remove Entity"

**Prerequisites:** P10-1 complete

**Technical Notes:**
- Add entity action button to EventCard component
- Create EntitySelectModal with search functionality
- API: POST /api/v1/events/{id}/entity
- Show current entity if assigned
- Reduce clicks: current flow requires opening detail first
- Backlog: IMP-023

---

### Story P10-4.2: Implement Manual Entity Creation

As a **user**,
I want **to create entities manually**,
So that **I can pre-register known people and vehicles**.

**Acceptance Criteria:**

**Given** I'm on the Entities page
**When** I click "Create Entity"
**Then** a creation modal opens with form fields

**Given** the creation form is open
**When** I fill in name, type (person/vehicle), and optional description
**Then** I can submit to create the entity
**And** for vehicles, I can add color, make, model

**Given** I submit a valid entity
**When** the entity is created
**Then** it appears in the entities list
**And** a success toast confirms creation
**And** I can optionally upload a reference image

**Prerequisites:** P10-4.1

**Technical Notes:**
- Add "Create Entity" button on Entities page
- Create EntityCreateModal component
- Form fields: name (required), type (required), description, color/make/model (vehicles)
- API: POST /api/v1/context/entities
- Optional image upload for reference thumbnail
- Generate vehicle signature from color-make-model
- Backlog: FF-031

---

### Story P10-4.3: Allow Feedback Modification

As a **user**,
I want **to change my feedback on event descriptions**,
So that **I can correct mistakes in my initial rating**.

**Acceptance Criteria:**

**Given** I previously submitted thumbs up on an event
**When** I click the thumbs up button again
**Then** I see options to change or remove my feedback

**Given** I change from thumbs up to thumbs down
**When** the change is submitted
**Then** my feedback is updated in the database
**And** I can add/edit correction text
**And** the UI reflects my new feedback

**Given** I want to remove my feedback entirely
**When** I click "Remove Feedback"
**Then** my feedback is cleared
**And** the buttons return to neutral state

**Prerequisites:** P10-1 complete

**Technical Notes:**
- Modify FeedbackButtons component to support editing
- Add edit/change button next to existing feedback indicator
- API: PUT /api/v1/events/{id}/feedback for updates
- API: DELETE /api/v1/events/{id}/feedback for removal
- Show "edited" indicator if feedback was changed
- Backlog: IMP-018

---

### Story P10-4.4: Show Feedback History Indicator

As a **user**,
I want **to see if feedback was edited**,
So that **I know the current rating may have changed**.

**Acceptance Criteria:**

**Given** an event has feedback that was modified
**When** I view the event card
**Then** I see an "edited" indicator next to the feedback

**Given** I hover over the edited indicator
**When** the tooltip appears
**Then** it shows when the feedback was last modified

**Given** an event has original (never edited) feedback
**When** I view the event card
**Then** no "edited" indicator is shown

**Prerequisites:** P10-4.3

**Technical Notes:**
- Add updated_at field to feedback model if not exists
- Compare created_at and updated_at to detect edits
- Add small "edited" badge or icon next to feedback buttons
- Tooltip shows: "Edited on [date]"
- Backlog: IMP-018

---

## Epic P10-5: Apple Platform Foundation

**Goal:** Document APIs and architecture for future native Apple apps.

**Value:** Clear path to mobile apps, reduced future development effort, stakeholder alignment.

**Backlog Items:** FF-024, FF-025

---

### Story P10-5.1: Generate OpenAPI 3.0 Specification

As a **developer**,
I want **a complete OpenAPI spec for the ArgusAI API**,
So that **mobile clients can be developed against a documented contract**.

**Acceptance Criteria:**

**Given** the OpenAPI spec is generated
**When** I view the specification
**Then** all API endpoints are documented
**And** request/response schemas are defined
**And** authentication requirements are specified

**Given** I have the OpenAPI spec
**When** I use a code generator (openapi-generator)
**Then** I can generate Swift client code
**And** the generated code is functional

**Given** the API changes
**When** I regenerate the spec
**Then** the spec reflects current endpoints
**And** versioning tracks breaking changes

**Prerequisites:** None (can run in parallel with P10-1)

**Technical Notes:**
- FastAPI auto-generates OpenAPI at /openapi.json
- Enhance with descriptions, examples, tags
- Add authentication schemas (JWT, API key)
- Document push notification registration endpoints
- Save versioned spec to docs/api/openapi-v1.yaml
- Add redoc or swagger-ui for browsing
- Backlog: FF-024

---

### Story P10-5.2: Document Mobile Authentication Flow

As a **developer**,
I want **authentication flows documented for mobile apps**,
So that **mobile development has clear security patterns**.

**Acceptance Criteria:**

**Given** I'm developing a mobile app
**When** I read the authentication documentation
**Then** I understand how to authenticate users
**And** I know how to refresh tokens
**And** I understand device registration

**Given** the documentation is complete
**When** I implement authentication
**Then** the documented flows work as described
**And** security best practices are followed

**Prerequisites:** P10-5.1

**Technical Notes:**
- Document JWT token flow for mobile
- Define token refresh mechanism
- Document device pairing/registration
- Define push notification token management
- Consider biometric authentication integration
- Add sequence diagrams for flows
- Backlog: FF-024

---

### Story P10-5.3: Design Cloud Relay Architecture

As an **architect**,
I want **a cloud relay architecture document**,
So that **remote access is planned without requiring port forwarding**.

**Acceptance Criteria:**

**Given** I read the architecture document
**When** I understand the relay design
**Then** I know how NAT traversal is handled
**And** I understand the security model
**And** I know the hosting requirements

**Given** the architecture is documented
**When** future development begins
**Then** implementation follows the documented design
**And** trade-offs are understood

**Prerequisites:** P10-5.2

**Technical Notes:**
- Document relay architecture options:
  - Cloudflare Tunnel
  - AWS IoT / API Gateway + WebSocket
  - Self-hosted relay server
- Define end-to-end encryption requirements
- Document device pairing flow
- Address bandwidth optimization for thumbnails/video
- Consider fallback to local network when available
- Backlog: FF-025

---

### Story P10-5.4: Define Mobile Push Architecture

As a **developer**,
I want **push notification architecture for mobile apps**,
So that **mobile devices receive real-time alerts**.

**Acceptance Criteria:**

**Given** the architecture is documented
**When** I implement mobile push
**Then** I understand token registration flow
**And** I know how APNS/FCM integration works
**And** I understand the notification payload format

**Given** multiple devices per user
**When** notifications are sent
**Then** all registered devices receive alerts

**Prerequisites:** P10-5.2

**Technical Notes:**
- Document APNS (Apple) integration
- Document FCM (Google) as backup
- Define device token storage model
- Define notification payload structure (matches web push)
- Consider notification preferences per device
- Address token refresh/expiration
- Backlog: FF-024

---

## Epic P10-6: AI & Quality Improvements

**Goal:** Enhance AI capabilities and code quality.

**Value:** Better AI context, improved code maintainability.

**Backlog Items:** IMP-016, FF-022

---

### Story P10-6.1: Research Local MCP Server

As a **developer**,
I want **research on local MCP server implementation**,
So that **AI can leverage local context for better descriptions**.

**Acceptance Criteria:**

**Given** I read the research document
**When** I understand MCP server patterns
**Then** I know implementation options
**And** I understand performance implications
**And** I know what context data to expose

**Given** the research is complete
**When** implementation begins (future phase)
**Then** the research informs design decisions

**Prerequisites:** None

**Technical Notes:**
- Research Model Context Protocol specification
- Evaluate hosting options (sidecar, embedded, standalone)
- Define context data schema:
  - User feedback history
  - Entity corrections
  - Known entities with attributes
  - Time-of-day patterns
  - Camera-specific context
- Assess performance impact
- Backlog: IMP-016

---

### Story P10-6.2: Research Query-Adaptive Frame Selection

As a **developer**,
I want **research on query-adaptive frame selection**,
So that **re-analysis can use smarter frame selection**.

**Acceptance Criteria:**

**Given** I read the research document
**When** I understand the approach
**Then** I know how to score frames by query relevance
**And** I understand embedding comparison techniques
**And** I know the implementation requirements

**Given** the research is complete
**When** implementation begins (future phase)
**Then** the research guides the technical approach

**Prerequisites:** None

**Technical Notes:**
- Research VL model embeddings (CLIP, SigLIP)
- Define query-to-frame relevance scoring
- Evaluate embedding storage requirements
- Consider compute requirements for embedding generation
- Define when query-adaptive applies (re-analysis, specific queries)
- Backlog: FF-022

---

## Summary

### Epic Breakdown Summary

| Epic | Stories | Priority | Backlog Items |
|------|---------|----------|---------------|
| P10-1: Critical Bug Fixes | 5 | P1 | BUG-012, BUG-013, BUG-014, BUG-015, IMP-010 |
| P10-2: Docker Containerization | 6 | P2 | FF-032 |
| P10-3: Kubernetes & Helm | 4 | P2 | FF-032 |
| P10-4: Entity Management UX | 4 | P2 | IMP-023, FF-031, IMP-018 |
| P10-5: Apple Platform Foundation | 4 | P3 | FF-024, FF-025 |
| P10-6: AI & Quality Improvements | 2 | P3 | IMP-016, FF-022 |
| **Total** | **25** | | **11 backlog items** |

### Recommended Execution Order

1. **P10-1.1 - P10-1.5** - Fix all bugs first (stability)
2. **P10-2.1 - P10-2.6** - Docker support (deployment foundation)
3. **P10-3.1 - P10-3.4** - Kubernetes & CI/CD (enterprise deployment)
4. **P10-4.1 - P10-4.4** - Entity management UX (user value)
5. **P10-5.1 - P10-5.4** - Apple platform docs (future foundation)
6. **P10-6.1 - P10-6.2** - Research (lowest dependency)

---

_For implementation: Use the `create-story` workflow to generate individual story implementation plans from this epic breakdown._

_This document will be updated after Architecture workflow to incorporate technical decisions._
