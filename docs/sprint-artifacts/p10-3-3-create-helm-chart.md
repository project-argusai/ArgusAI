# Story P10-3.3: Create Helm Chart

Status: done

## Story

As a **developer**,
I want **a Helm chart for ArgusAI**,
So that **I can deploy with customizable configuration via values.yaml**.

## Acceptance Criteria

1. **Given** the Helm chart exists
   **When** I run helm install argusai ./charts/argusai with required secrets
   **Then** all Kubernetes resources are created and the application is running

2. **Given** I want to customize the deployment
   **When** I provide custom values via --set or -f values.yaml
   **Then** the deployment reflects my configuration (replicas, resources, ingress)

3. **Given** ArgusAI is installed
   **When** I run helm upgrade
   **Then** the deployment is updated with rolling restart and zero downtime

4. **Given** the chart is installed
   **When** I run helm uninstall
   **Then** all resources are removed except PVCs (data preserved)

5. **Given** I run helm lint
   **Then** the chart passes validation with no errors

## Tasks / Subtasks

- [x] Task 1: Create Helm chart structure (AC: 1, 5)
  - [x] Subtask 1.1: Create charts/argusai/ directory
  - [x] Subtask 1.2: Create Chart.yaml with metadata
  - [x] Subtask 1.3: Create values.yaml with all options

- [x] Task 2: Create template helpers (AC: 1)
  - [x] Subtask 2.1: Create _helpers.tpl with naming functions
  - [x] Subtask 2.2: Add labels, selectors, fullname helpers

- [x] Task 3: Create deployment templates (AC: 1, 2, 3)
  - [x] Subtask 3.1: Create backend-deployment.yaml template
  - [x] Subtask 3.2: Create frontend-deployment.yaml template

- [x] Task 4: Create service templates (AC: 1, 2)
  - [x] Subtask 4.1: Create backend-service.yaml template
  - [x] Subtask 4.2: Create frontend-service.yaml template

- [x] Task 5: Create config templates (AC: 1, 2)
  - [x] Subtask 5.1: Create configmap.yaml template
  - [x] Subtask 5.2: Create secret.yaml template

- [x] Task 6: Create storage and networking (AC: 1, 2, 4)
  - [x] Subtask 6.1: Create pvc.yaml template (with enabled flag)
  - [x] Subtask 6.2: Create ingress.yaml template (with enabled flag)
  - [x] Subtask 6.3: Create serviceaccount.yaml template

- [x] Task 7: Create post-install notes (AC: 1)
  - [x] Subtask 7.1: Create NOTES.txt with usage instructions

- [x] Task 8: Validate chart (AC: 5)
  - [x] Subtask 8.1: Run helm lint
  - [x] Subtask 8.2: Run helm template with test values

## Dev Notes

### Chart Structure

```
charts/argusai/
├── Chart.yaml           # Chart metadata
├── values.yaml          # Default configuration values
└── templates/
    ├── _helpers.tpl           # Template functions
    ├── backend-deployment.yaml
    ├── frontend-deployment.yaml
    ├── backend-service.yaml
    ├── frontend-service.yaml
    ├── configmap.yaml
    ├── secret.yaml
    ├── pvc.yaml
    ├── ingress.yaml
    ├── serviceaccount.yaml
    └── NOTES.txt
```

### Key Values

| Value | Default | Description |
|-------|---------|-------------|
| backend.replicaCount | 1 | Backend replicas |
| frontend.replicaCount | 1 | Frontend replicas |
| secrets.encryptionKey | "" | Required: Fernet key |
| secrets.jwtSecretKey | "" | Required: JWT secret |
| persistence.enabled | true | Enable PVC |
| ingress.enabled | false | Enable Ingress |

### Usage Examples

```bash
# Install with required secrets
helm install argusai ./charts/argusai \
  --set secrets.encryptionKey=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  --set secrets.jwtSecretKey=$(openssl rand -hex 32)

# Install with custom values file
helm install argusai ./charts/argusai -f my-values.yaml

# Upgrade
helm upgrade argusai ./charts/argusai

# Uninstall (keeps PVC)
helm uninstall argusai
```

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P10-3.md#Story-P10-3.3]
- [Source: docs/epics-phase10.md#Story-P10-3.3]
- [Source: docs/PRD-phase10.md#FR27-FR28]

## Dev Agent Record

### Context Reference

### Agent Model Used

Claude Opus 4.5

### Debug Log References

- helm lint passed with 0 errors
- helm template generated valid K8s manifests

### Completion Notes List

- Created complete Helm chart in charts/argusai/
- Chart.yaml with metadata (version 0.1.0, appVersion 1.0.0)
- values.yaml with all configurable options
- _helpers.tpl with naming and label functions
- All K8s resource templates with Helm templating
- NOTES.txt with post-install instructions and warnings
- Secret template uses stringData for easier value passing

### File List

NEW:
- charts/argusai/Chart.yaml
- charts/argusai/values.yaml
- charts/argusai/templates/_helpers.tpl
- charts/argusai/templates/backend-deployment.yaml
- charts/argusai/templates/frontend-deployment.yaml
- charts/argusai/templates/backend-service.yaml
- charts/argusai/templates/frontend-service.yaml
- charts/argusai/templates/configmap.yaml
- charts/argusai/templates/secret.yaml
- charts/argusai/templates/pvc.yaml
- charts/argusai/templates/ingress.yaml
- charts/argusai/templates/serviceaccount.yaml
- charts/argusai/templates/NOTES.txt

---

## Change Log

| Date | Change |
|------|--------|
| 2025-12-24 | Story drafted and implemented |
