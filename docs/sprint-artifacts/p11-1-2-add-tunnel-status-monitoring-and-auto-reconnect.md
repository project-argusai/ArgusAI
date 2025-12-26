# Story P11-1.2: Add Tunnel Status Monitoring and Auto-Reconnect

Status: complete

## Story

As a **user**,
I want **the tunnel to automatically reconnect if disconnected**,
so that **remote access remains reliable**.

## Acceptance Criteria

1. **AC-1.2.1**: System monitors tunnel connection health every 30 seconds
2. **AC-1.2.2**: Auto-reconnect triggers within 30 seconds of disconnect
3. **AC-1.2.3**: Connection events logged with structured format for troubleshooting
4. **AC-1.2.4**: API endpoint `/api/v1/system/tunnel-status` returns current state with uptime

## Tasks / Subtasks

- [x] Task 1: Add health check loop to TunnelService (AC: 1, 2)
  - [x] Implement `_health_check_loop()` async method
  - [x] Monitor process status every 30 seconds
  - [x] Detect disconnection via process exit or timeout
  - [x] Track connection state and uptime

- [x] Task 2: Implement auto-reconnect with exponential backoff (AC: 2)
  - [x] Add `_reconnect()` method with retry logic
  - [x] Implement exponential backoff (5s, 10s, 20s, 30s max)
  - [x] Set error state after 3 consecutive failures
  - [x] Reset backoff on successful reconnection

- [x] Task 3: Add structured logging for tunnel events (AC: 3)
  - [x] Log `tunnel.connected` with hostname and tunnel_id
  - [x] Log `tunnel.disconnected` with duration and reason
  - [x] Log `tunnel.reconnecting` with attempt count
  - [x] Log `tunnel.error` with error details

- [x] Task 4: Enhance tunnel status API with uptime tracking (AC: 4)
  - [x] Add `uptime_seconds` to TunnelStatusResponse
  - [x] Add `last_connected` timestamp tracking
  - [x] Add `reconnect_count` to status
  - [x] Expose detailed status via GET /api/v1/system/tunnel/status

- [x] Task 5: Add Prometheus metrics for monitoring
  - [x] Add `argusai_tunnel_connected` gauge (0/1)
  - [x] Add `argusai_tunnel_reconnect_total` counter
  - [x] Add `argusai_tunnel_uptime_seconds` gauge

- [x] Task 6: Write unit tests
  - [x] Test health check loop with mocked process
  - [x] Test auto-reconnect with simulated failures
  - [x] Test exponential backoff timing
  - [x] Test status API response schema

## Dev Notes

### Relevant Architecture Patterns

- **Health Check Loop**: Use `asyncio.create_task()` for background monitoring
- **Exponential Backoff**: 5s base, 2x multiplier, 30s max
- **Process Monitoring**: Check `process.returncode` and stderr
- **Metrics**: Follow existing Prometheus patterns from `app/core/metrics.py`

### Source Tree Components

```
backend/
├── app/
│   ├── services/
│   │   └── tunnel_service.py     # MODIFY: Add health check and reconnect
│   ├── api/v1/
│   │   └── system.py             # MODIFY: Enhance status response
│   └── core/
│       └── metrics.py            # MODIFY: Add tunnel metrics
└── tests/
    └── test_services/
        └── test_tunnel_service.py # MODIFY: Add health/reconnect tests
```

### Testing Standards

- Mock `asyncio.sleep` to speed up backoff tests
- Use `asyncio.wait_for` with timeout in tests
- Verify log output format matches structured logging
- Test edge cases: immediate failure, intermittent failures, recovery

### Security Considerations

- Never log tunnel token in reconnection attempts
- Ensure health check doesn't expose sensitive data
- Graceful degradation: local access unaffected by tunnel failures

### Project Structure Notes

- Extends TunnelService from P11-1.1
- Follows existing metrics patterns from Phase 1
- Uses structured JSON logging from Story 6.2

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P11-1.md#Workflows-and-Sequencing]
- [Source: docs/sprint-artifacts/tech-spec-epic-P11-1.md#Non-Functional-Requirements]
- [Source: docs/sprint-artifacts/tech-spec-epic-P11-1.md#Observability]
- [Source: docs/architecture/cloud-relay-architecture.md]

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

### Completion Notes List

- Implemented `_health_check_loop()` with 30-second monitoring interval (HEALTH_CHECK_INTERVAL constant)
- Added exponential backoff reconnection: 5s base, 2x multiplier, 30s max (BACKOFF_BASE, BACKOFF_MULTIPLIER, BACKOFF_MAX constants)
- Error state after 3 consecutive failures (MAX_RECONNECT_FAILURES constant)
- Added structured logging with event_type: `tunnel.connected`, `tunnel.disconnected`, `tunnel.reconnecting`, `tunnel.error`
- Enhanced TunnelStatusResponse with `uptime_seconds`, `last_connected`, `reconnect_count` fields
- Added Prometheus metrics: `argusai_tunnel_connected`, `argusai_tunnel_reconnect_total`, `argusai_tunnel_uptime_seconds`
- 45 unit tests covering health check, auto-reconnect, exponential backoff, and status API

### File List

- backend/app/services/tunnel_service.py (MODIFIED - added health check, auto-reconnect, uptime tracking)
- backend/app/api/v1/system.py (MODIFIED - enhanced TunnelStatusResponse with uptime fields)
- backend/app/core/metrics.py (MODIFIED - added tunnel metrics)
- backend/tests/test_services/test_tunnel_service.py (MODIFIED - added 24 new tests for P11-1.2)
- docs/sprint-artifacts/p11-1-2-add-tunnel-status-monitoring-and-auto-reconnect.md (MODIFIED - marked complete)
