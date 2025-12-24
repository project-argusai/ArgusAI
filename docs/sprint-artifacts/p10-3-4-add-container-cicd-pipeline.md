# Story P10-3.4: Add Container CI/CD Pipeline

Status: done

## Story

As a **developer**,
I want **GitHub Actions CI/CD for container builds**,
So that **Docker images are automatically built and pushed to ghcr.io**.

## Acceptance Criteria

1. **Given** I push to the main branch
   **When** the CI workflow runs
   **Then** Docker images are built for both backend and frontend for linux/amd64 and linux/arm64

2. **Given** the build succeeds
   **When** images are pushed
   **Then** they are tagged with branch name (main), git SHA, and latest

3. **Given** I create a release tag (v1.0.0)
   **When** the CI workflow runs
   **Then** images are tagged with the semantic version (v1.0.0, v1.0)

4. **Given** I open a pull request
   **When** CI runs
   **Then** Docker builds are tested (no push) and K8s manifests are validated with dry-run

5. **Given** the validate-k8s job runs
   **When** helm lint executes
   **Then** the Helm chart passes linting with no errors

6. **Given** images are pushed
   **When** I check ghcr.io
   **Then** both argusai-backend and argusai-frontend images are available with multi-arch manifests

## Tasks / Subtasks

- [x] Task 1: Create GitHub Actions workflow file (AC: 1, 2, 3, 4)
  - [x] Subtask 1.1: Create .github/workflows/docker.yml
  - [x] Subtask 1.2: Configure triggers (push, PR, tags)
  - [x] Subtask 1.3: Set up environment variables for registry

- [x] Task 2: Configure backend build job (AC: 1, 2, 3)
  - [x] Subtask 2.1: Set up QEMU for multi-arch
  - [x] Subtask 2.2: Set up Docker Buildx
  - [x] Subtask 2.3: Configure registry login
  - [x] Subtask 2.4: Configure metadata action for tags
  - [x] Subtask 2.5: Configure build-push-action

- [x] Task 3: Configure frontend build job (AC: 1, 2, 3)
  - [x] Subtask 3.1: Mirror backend job structure
  - [x] Subtask 3.2: Add NEXT_PUBLIC_API_URL build arg

- [x] Task 4: Configure validation job (AC: 4, 5)
  - [x] Subtask 4.1: Set up kubectl
  - [x] Subtask 4.2: Run kubectl dry-run on manifests
  - [x] Subtask 4.3: Set up Helm
  - [x] Subtask 4.4: Run helm lint
  - [x] Subtask 4.5: Run helm template

## Dev Notes

### Workflow Structure

```yaml
jobs:
  build-backend:    # Build and push backend image
  build-frontend:   # Build and push frontend image
  validate-k8s:     # Validate manifests and Helm chart
```

All jobs run in parallel for faster CI.

### Trigger Matrix

| Event | Backend | Frontend | K8s Validate | Push Images |
|-------|---------|----------|--------------|-------------|
| Push to main | Build | Build | Yes | Yes |
| Pull Request | Build | Build | Yes | No |
| Tag v* | Build | Build | Yes | Yes |

### Image Tags

| Trigger | Tags Applied |
|---------|-------------|
| Push to main | main, latest, sha-abc123 |
| Tag v1.2.3 | v1.2.3, v1.2, sha-abc123 |
| PR #123 | pr-123 (no push) |

### GitHub Actions Used

| Action | Version | Purpose |
|--------|---------|---------|
| actions/checkout | v4 | Repository checkout |
| docker/setup-qemu-action | v3 | Multi-arch emulation |
| docker/setup-buildx-action | v3 | Docker buildx |
| docker/login-action | v3 | ghcr.io login |
| docker/metadata-action | v5 | Image tagging |
| docker/build-push-action | v5 | Build and push |
| azure/setup-kubectl | v4 | kubectl CLI |
| azure/setup-helm | v4 | Helm CLI |

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P10-3.md#Story-P10-3.4]
- [Source: docs/epics-phase10.md#Story-P10-3.4]
- [Source: docs/PRD-phase10.md#FR29-FR32]

## Dev Agent Record

### Context Reference

### Agent Model Used

Claude Opus 4.5

### Debug Log References

- Workflow file created with proper YAML syntax
- All three jobs configured in parallel
- Validation job skips secret.yaml (empty values by design)

### Completion Notes List

- Created .github/workflows/docker.yml with complete CI/CD pipeline
- Backend job: Multi-arch build (amd64, arm64) with GHA caching
- Frontend job: Multi-arch build with NEXT_PUBLIC_API_URL build arg
- Validation job: kubectl dry-run + helm lint + helm template
- Automatic tagging via docker/metadata-action
- Only pushes on non-PR events
- Uses GITHUB_TOKEN for ghcr.io authentication (no secrets needed)

### File List

NEW:
- .github/workflows/docker.yml - Docker build and push CI/CD workflow

MODIFIED:
- docs/sprint-artifacts/sprint-status.yaml - Updated story status

---

## Change Log

| Date | Change |
|------|--------|
| 2025-12-24 | Story drafted and implemented |
