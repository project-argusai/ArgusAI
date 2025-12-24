# Story P10-3.2: Create Kubernetes Service and Config Resources

Status: done

## Story

As a **developer**,
I want **Kubernetes Service, ConfigMap, Secret, PVC, and Ingress resources**,
So that **ArgusAI pods can communicate and receive configuration**.

## Acceptance Criteria

1. **Given** manifests are applied
   **When** I check services with kubectl get svc
   **Then** backend (ClusterIP:8000) and frontend (ClusterIP:3000) Services exist with correct selectors

2. **Given** ConfigMap is applied
   **When** backend pods start
   **Then** configuration values (DEBUG, LOG_LEVEL, etc.) are available as environment variables

3. **Given** Secret is applied with base64-encoded values
   **When** backend pods start
   **Then** sensitive values (ENCRYPTION_KEY, JWT_SECRET_KEY) are available and not visible in plain text

4. **Given** PVC is created
   **When** backend pod mounts it
   **Then** data at /app/data persists across pod restarts

5. **Given** Ingress is applied (optional)
   **When** I access the host
   **Then** requests route to frontend (/) and backend (/api, /ws, /docs) correctly

## Tasks / Subtasks

- [x] Task 1: Create backend Service manifest (AC: 1)
  - [x] Subtask 1.1: Create `k8s/backend-service.yaml`
  - [x] Subtask 1.2: Configure ClusterIP type with port 8000
  - [x] Subtask 1.3: Add selector matching backend Deployment labels

- [x] Task 2: Create frontend Service manifest (AC: 1)
  - [x] Subtask 2.1: Create `k8s/frontend-service.yaml`
  - [x] Subtask 2.2: Configure ClusterIP type with port 3000
  - [x] Subtask 2.3: Add selector matching frontend Deployment labels

- [x] Task 3: Create ConfigMap manifest (AC: 2)
  - [x] Subtask 3.1: Create `k8s/configmap.yaml`
  - [x] Subtask 3.2: Add DEBUG, LOG_LEVEL, CORS_ORIGINS, DATABASE_URL, SSL_ENABLED

- [x] Task 4: Create Secret manifest template (AC: 3)
  - [x] Subtask 4.1: Create `k8s/secret.yaml` with placeholder values
  - [x] Subtask 4.2: Add ENCRYPTION_KEY, JWT_SECRET_KEY (required)
  - [x] Subtask 4.3: Add optional API keys (OPENAI, XAI, ANTHROPIC, GOOGLE_AI)
  - [x] Subtask 4.4: Document base64 encoding requirement in comments

- [x] Task 5: Create PVC manifest (AC: 4)
  - [x] Subtask 5.1: Create `k8s/pvc.yaml`
  - [x] Subtask 5.2: Configure ReadWriteOnce access mode
  - [x] Subtask 5.3: Request 10Gi storage

- [x] Task 6: Create Ingress manifest (AC: 5)
  - [x] Subtask 6.1: Create `k8s/ingress.yaml`
  - [x] Subtask 6.2: Configure nginx ingress class
  - [x] Subtask 6.3: Route /api, /ws, /docs, /openapi.json to backend
  - [x] Subtask 6.4: Route / to frontend
  - [x] Subtask 6.5: Add WebSocket upgrade annotation

- [x] Task 7: Validate manifests (AC: 1-5)
  - [x] Subtask 7.1: Validate YAML syntax with PyYAML

## Dev Notes

### Architecture Alignment

From tech-spec-epic-P10-3.md:
- ClusterIP Services for internal pod communication
- ConfigMap for non-sensitive environment variables
- Secret for encrypted credentials
- PVC with ReadWriteOnce for SQLite database
- Optional Ingress for external access

### Learnings from Previous Story

**From Story P10-3.1 (Status: done)**

- **K8s directory created**: k8s/ directory already exists
- **Labels established**: app: argusai, component: backend/frontend
- **envFrom pattern**: Deployments expect ConfigMap (argusai-config) and Secret (argusai-secrets)
- **PVC name**: Deployments reference PVC named argusai-data

[Source: docs/sprint-artifacts/p10-3-1-create-kubernetes-deployment-manifests.md#Dev-Agent-Record]

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P10-3.md#Story-P10-3.2]
- [Source: docs/epics-phase10.md#Story-P10-3.2]
- [Source: docs/PRD-phase10.md#FR24-FR26]

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p10-3-2-create-kubernetes-service-and-config-resources.context.xml

### Agent Model Used

Claude Opus 4.5

### Debug Log References

- All YAML files validated with PyYAML parser

### Completion Notes List

- Created backend-service.yaml with ClusterIP on port 8000
- Created frontend-service.yaml with ClusterIP on port 3000
- Created configmap.yaml with non-sensitive configuration
- Created secret.yaml template with placeholder values and documentation
- Created pvc.yaml with 10Gi ReadWriteOnce storage
- Created ingress.yaml with nginx routing for API, WebSocket, and frontend

### File List

NEW:
- k8s/backend-service.yaml - Backend ClusterIP Service
- k8s/frontend-service.yaml - Frontend ClusterIP Service
- k8s/configmap.yaml - Non-sensitive configuration
- k8s/secret.yaml - Secret template (requires values)
- k8s/pvc.yaml - Persistent Volume Claim
- k8s/ingress.yaml - Optional nginx Ingress

MODIFIED:
- docs/sprint-artifacts/sprint-status.yaml - Updated story status

---

## Change Log

| Date | Change |
|------|--------|
| 2025-12-24 | Story drafted and implemented |
