# Story 5.3: Implement Webhook Integration

Status: done

## Story

As a **smart home enthusiast**,
I want **to trigger webhooks when events occur**,
so that **I can integrate with Home Assistant and other automation platforms**.

## Acceptance Criteria

1. **Webhook HTTP POST Request** - Send data to configured URLs
   - Method: POST, Content-Type: application/json
   - Timeout: 5 seconds
   - User-Agent: "LiveObjectAIClassifier/1.0"
   - Include user-defined headers from rule config (for authentication)
   - [Source: docs/epics.md#Story-5.3]

2. **Webhook Payload Format** - Structured JSON payload
   ```json
   {
     "event_id": "uuid",
     "timestamp": "2025-11-16T15:30:00Z",
     "camera": {"id": "uuid", "name": "Front Door"},
     "description": "Person approaching front door...",
     "confidence": 92,
     "objects_detected": ["person"],
     "thumbnail_url": "https://.../api/v1/events/uuid/thumbnail",
     "rule": {"id": "uuid", "name": "Front door visitor"}
   }
   ```
   - [Source: docs/epics.md#Story-5.3]

3. **Retry Logic for Failures** - Reliable delivery with backoff
   - Failed requests (non-2xx status, timeout, network error) → Retry
   - Retry attempts: 3 total (initial + 2 retries)
   - Backoff: Exponential (1s, 2s, 4s delays)
   - After 3 failures → Give up, log error
   - Success: Any 2xx status code
   - [Source: docs/epics.md#Story-5.3]

4. **Webhook Logging** - Track delivery history
   - Log every webhook attempt in webhook_logs table
   - Logged data: event_id, rule_id, url, status_code, response_time_ms, retry_count, error_message, created_at
   - Keep logs for 30 days (cleanup with event retention)
   - API endpoint: `GET /api/v1/webhooks/logs` with filters
   - [Source: docs/epics.md#Story-5.3]

5. **Security and Validation** - Prevent abuse
   - HTTPS required (reject http:// URLs in production)
   - URL validation: Must be valid HTTP(S) URL
   - No localhost/127.0.0.1 in production (prevent SSRF)
   - Rate limiting: Max 100 webhooks per minute per rule
   - [Source: docs/epics.md#Story-5.3]

6. **Webhook Testing Endpoint** - Verify configuration before saving
   - Test endpoint: `POST /api/v1/webhooks/test` with url and payload
   - Sample payload uses recent real event or mock data
   - Response: Status code, response body (first 200 chars), response time
   - Success: 2xx status codes
   - Error: Specific error message (timeout, connection refused, invalid URL)
   - [Source: docs/epics.md#Story-5.3]

7. **Webhook Logs UI** - View delivery history
   - Table: Timestamp, Rule, URL, Status, Response Time, Retries
   - Filter: By rule, by success/failure, by date range
   - Details modal: Click row to see full request/response details
   - Export: Download logs as CSV
   - Location: Rules page or dedicated Webhooks tab in Settings
   - [Source: docs/epics.md#Story-5.3]

## Tasks / Subtasks

- [x] Task 1: Implement webhook service (AC: #1, #2, #3)
  - [x] Create `/backend/app/services/webhook_service.py`
  - [x] Implement `send_webhook(url, headers, payload)` with httpx.AsyncClient
  - [x] Build payload from event and rule data
  - [x] Add timeout (5 seconds), User-Agent header
  - [x] Implement exponential backoff retry (1s, 2s, 4s)

- [x] Task 2: Implement webhook logging (AC: #4)
  - [x] Verify/create webhook_logs table (may exist from Story 5.1)
  - [x] Create Pydantic schema for WebhookLog
  - [x] Log each webhook attempt (success and failure)
  - [x] Store: event_id, rule_id, url, status_code, response_time_ms, retry_count, error_message

- [x] Task 3: Implement security validation (AC: #5)
  - [x] Add URL validation (HTTPS required in production)
  - [x] Add SSRF prevention (block localhost, private IPs)
  - [x] Add rate limiting (100/min per rule) using in-memory counter or Redis
  - [x] Create blocklist for private IP ranges (10.x, 172.16-31.x, 192.168.x)

- [x] Task 4: Implement webhook test endpoint (AC: #6)
  - [x] Create `POST /api/v1/webhooks/test` endpoint
  - [x] Accept: url, headers, optional payload
  - [x] Use sample/mock event data if no payload provided
  - [x] Return: status_code, response_body (truncated), response_time_ms
  - [x] Handle errors gracefully (timeout, connection refused, invalid URL)

- [x] Task 5: Implement webhook logs API (AC: #4, #7)
  - [x] Create `GET /api/v1/webhooks/logs` endpoint
  - [x] Support filters: rule_id, success/failure, date_range
  - [x] Support pagination (limit, offset)
  - [x] Support export as CSV via Accept header or query param

- [x] Task 6: Integrate webhook execution with alert engine (AC: #1, #2)
  - [x] Modify alert_engine.py to call webhook_service on rule trigger
  - [x] Ensure async execution (non-blocking)
  - [x] Handle webhook failures without blocking other rules

- [x] Task 7: Build webhook logs UI component (AC: #7)
  - [x] Create `WebhookLogs.tsx` component
  - [x] Display table with columns: Timestamp, Rule, URL, Status, Response Time, Retries
  - [x] Add filter controls (rule dropdown, success/fail toggle, date range)
  - [x] Add details modal for full request/response view
  - [x] Add CSV export button

- [x] Task 8: Add webhook logs to Rules page or Settings (AC: #7)
  - [x] Add "Webhook Logs" tab or section to Rules page
  - [x] Integrate WebhookLogs component
  - [x] Add TanStack Query for data fetching with pagination

- [x] Task 9: Testing and validation
  - [x] Write unit tests for webhook_service (retry logic, payload format)
  - [x] Write integration tests for webhook endpoints
  - [x] Test SSRF prevention (verify localhost blocked)
  - [x] Verify build passes: `npm run build`
  - [x] Run linting: `npm run lint`

## Dev Notes

### Architecture Context

From `docs/architecture.md`:
- **Backend Framework**: FastAPI with async support
- **HTTP Client**: Use `httpx.AsyncClient` for async HTTP requests
- **Database**: SQLAlchemy async with SQLite (webhook_logs table)
- **Background Tasks**: FastAPI BackgroundTasks or asyncio.create_task()

### Learnings from Previous Story

**From Story 5.2: Build Alert Rule Configuration UI (Status: done)**

- **WebhookConfig UI Component Created**: `frontend/components/rules/WebhookConfig.tsx` - REUSE this for webhook URL/headers display
- **Alert Rules API Client**: `frontend/lib/api-client.ts` alertRules namespace already exists - extend for webhooks
- **TypeScript Types**: `frontend/types/alert-rule.ts` includes `IWebhookConfig` interface
- **Zod Validation Pattern**: URL validation with regex already implemented in RuleFormDialog
- **shadcn/ui Components**: Dialog, Table patterns established
- **Advisory Note**: Webhook URL validation requires http:// or https:// prefix (HTTPS should be required in production - implement in this story)
[Source: docs/sprint-artifacts/5-2-build-alert-rule-configuration-ui.md#Dev-Agent-Record]

**From Story 5.1: Implement Alert Rule Engine (Status: done)**

- **Alert Engine**: `/backend/app/services/alert_engine.py` - Rule evaluation triggers webhook execution (placeholder exists)
- **WebhookLog Model**: `/backend/app/models/alert_rule.py` - WebhookLog SQLAlchemy model already created
- **Webhook Headers**: Rule actions.webhook.headers stored in database
[Source: docs/sprint-artifacts/5-1-implement-alert-rule-engine.md]

### Backend Implementation Notes

- **Service Location**: `/backend/app/services/webhook_service.py` (new)
- **API Routes**: `/backend/app/api/v1/webhooks.py` (new)
- **HTTP Client**: Use `httpx.AsyncClient` with `timeout=5.0`
- **Retry Library**: Consider `tenacity` library for retry decorator, or manual implementation
- **SSRF Prevention**: Use `ipaddress` module to check if URL resolves to private IP
- **Rate Limiting**: Simple in-memory dict with timestamp, or use fastapi-limiter

### Frontend Implementation Notes

- **New Component**: `/frontend/components/rules/WebhookLogs.tsx`
- **API Client Extension**: Add webhooks namespace to `/frontend/lib/api-client.ts`
- **Table Component**: Use existing table patterns from RulesList
- **Date Range Picker**: May need new component or use existing date picker

### Project Structure Notes

- Alignment with unified project structure:
  - Backend Service: `/backend/app/services/webhook_service.py`
  - Backend Routes: `/backend/app/api/v1/webhooks.py`
  - Frontend Component: `/frontend/components/rules/WebhookLogs.tsx`
  - Frontend API: Extend `/frontend/lib/api-client.ts`

### References

- [PRD: F9 - Webhook Integration](../prd.md#F9-Webhook-Integration)
- [Architecture: Backend Services](../architecture.md#Backend-Services)
- [Epic 5: Alert & Automation System](../epics.md#Epic-5)
- [Story 5.1: Alert Rule Engine](./5-1-implement-alert-rule-engine.md) - WebhookLog model
- [Story 5.2: Alert Rule Configuration UI](./5-2-build-alert-rule-configuration-ui.md) - WebhookConfig component

## Dev Agent Record

### Context Reference

- `docs/sprint-artifacts/5-3-implement-webhook-integration.context.xml`

### Agent Model Used

Claude Sonnet 4.5 (claude-sonnet-4-5-20250929)

### Debug Log References

N/A

### Completion Notes List

1. **Webhook Service Implementation** - Created comprehensive async webhook delivery service with:
   - httpx.AsyncClient for non-blocking HTTP POST requests
   - 5-second timeout with User-Agent header
   - Exponential backoff retry (1s, 2s, 4s delays, 3 total attempts)
   - Structured payload matching documented format

2. **Security Features** - Implemented robust security validation:
   - SSRF prevention using Python ipaddress module
   - Blocks localhost, 127.0.0.1, private IP ranges (10.x, 172.16-31.x, 192.168.x)
   - HTTPS required in production (configurable allow_http for development)
   - Rate limiting: 100 webhooks per minute per rule (in-memory cache)

3. **Webhook Logging** - Full audit trail:
   - Logs to WebhookLog model (created in Story 5.1)
   - Captures: rule_id, event_id, url, status_code, response_time_ms, retry_count, success, error_message
   - API endpoint for viewing/filtering logs

4. **API Endpoints** - Three new endpoints in /api/v1/webhooks:
   - POST /test - Test webhook configuration before saving
   - GET /logs - Paginated webhook delivery logs with filters
   - GET /logs/export - Download logs as CSV

5. **Frontend Integration** - WebhookLogs component added to Rules page:
   - Table display with filtering (rule, success/fail, date range)
   - Details modal for full request/response view
   - CSV export functionality
   - TanStack Query for data fetching with 30s auto-refresh

6. **Test Coverage** - 33 tests added:
   - 25 unit tests for webhook service (URL validation, SSRF, rate limiting, retry logic)
   - 8 API tests for webhook endpoints

### File List

**Backend - New Files:**
- `backend/app/services/webhook_service.py` - Core webhook delivery service
- `backend/app/api/v1/webhooks.py` - Webhook API endpoints
- `backend/tests/test_services/test_webhook_service.py` - Unit tests (25 tests)
- `backend/tests/test_api/test_webhooks.py` - API tests (8 tests)

**Backend - Modified Files:**
- `backend/main.py` - Added webhooks router

**Frontend - New Files:**
- `frontend/components/rules/WebhookLogs.tsx` - Webhook logs UI component

**Frontend - Modified Files:**
- `frontend/lib/api-client.ts` - Added webhooks namespace
- `frontend/types/alert-rule.ts` - Added webhook types (IWebhookTestRequest, IWebhookTestResponse, IWebhookLog, etc.)
- `frontend/app/rules/page.tsx` - Added WebhookLogs section

## Change Log

| Date | Version | Description |
|------|---------|-------------|
| 2025-11-23 | 1.0 | Story drafted from epics.md and Story 5.2 learnings |
| 2025-11-23 | 2.0 | Story completed - all 7 ACs met, 9 tasks done, 33 tests passing |
