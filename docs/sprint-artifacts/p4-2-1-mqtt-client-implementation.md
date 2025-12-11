# Story P4-2.1: MQTT Client Implementation

Status: done

## Story

As a **system administrator deploying Live Object AI Classifier**,
I want **the backend to connect to an MQTT broker with auto-reconnect**,
so that **events can be published to Home Assistant and other MQTT subscribers reliably**.

## Acceptance Criteria

| # | Criteria | Verification |
|---|----------|--------------|
| 1 | Paho MQTT client connects to configured broker with username/password auth | Unit test with mock broker |
| 2 | Auto-reconnect activates on connection loss with exponential backoff (1s → 60s max) | Integration test with broker restart |
| 3 | Event payloads serialized correctly to JSON with all required fields | Unit test payload validation |
| 4 | QoS levels 0, 1, 2 configurable and respected | Config test with each QoS level |
| 5 | Connection status tracked and queryable via API | API test for status endpoint |
| 6 | MQTT configuration stored in database with encrypted credentials | DB test with encryption verification |
| 7 | Connection/disconnection logged at INFO level, errors at WARNING | Log output verification |

## Tasks / Subtasks

- [x] **Task 1: Add paho-mqtt dependency** (AC: 1)
  - [x] Add `paho-mqtt>=2.0.0` to `backend/requirements.txt`
  - [x] Verify installation and import works

- [x] **Task 2: Create MQTT configuration model** (AC: 6)
  - [x] Create `backend/app/models/mqtt_config.py` with SQLAlchemy model
  - [x] Fields: broker_host, broker_port, username, password (encrypted), topic_prefix, qos, enabled, discovery_enabled, discovery_prefix, retain_messages
  - [x] Add model to `backend/app/models/__init__.py`
  - [x] Create Alembic migration for mqtt_config table

- [x] **Task 3: Implement MQTTService** (AC: 1, 2, 4, 7)
  - [x] Create `backend/app/services/mqtt_service.py`
  - [x] Implement `MQTTService` class with Paho client
  - [x] Add `connect()`, `disconnect()`, `publish()` async methods
  - [x] Implement auto-reconnect with exponential backoff (1s, 2s, 4s, ... 60s max)
  - [x] Add connection state tracking (`is_connected`, `last_connected_at`, `last_error`)
  - [x] Add QoS parameter to publish method
  - [x] Implement `on_connect`, `on_disconnect`, `on_publish` callbacks
  - [x] Add logging for connection events

- [x] **Task 4: Create event payload serializer** (AC: 3)
  - [x] Create `serialize_event_for_mqtt()` function
  - [x] Include: event_id, camera_id, camera_name, description, objects_detected, confidence, source_type, smart_detection_type, timestamp, thumbnail_url
  - [x] Ensure JSON serialization handles datetime and UUID types

- [x] **Task 5: Add MQTT API endpoints** (AC: 5, 6)
  - [x] Create `backend/app/api/v1/integrations.py` router
  - [x] `GET /api/v1/integrations/mqtt/config` - Get config (password omitted)
  - [x] `PUT /api/v1/integrations/mqtt/config` - Update config, trigger reconnect
  - [x] `GET /api/v1/integrations/mqtt/status` - Get connection status
  - [x] `POST /api/v1/integrations/mqtt/test` - Test connection without saving
  - [x] Add router to main app

- [x] **Task 6: Add Prometheus metrics** (AC: 5)
  - [x] Add `mqtt_connection_status` gauge (0=disconnected, 1=connected)
  - [x] Add `mqtt_messages_published_total` counter
  - [x] Add `mqtt_publish_errors_total` counter
  - [x] Add `mqtt_reconnect_attempts_total` counter

- [x] **Task 7: Integrate with app lifecycle** (AC: 1, 2)
  - [x] Initialize MQTTService on app startup (if enabled)
  - [x] Add graceful disconnect on app shutdown
  - [x] Load config from database on startup

- [x] **Task 8: Write tests** (AC: all)
  - [x] Unit tests for MQTTService methods with mocked client
  - [x] Unit tests for event payload serialization
  - [x] Integration tests for config API endpoints
  - [x] Test auto-reconnect behavior

## Dev Notes

### Architecture Alignment

The MQTT service follows existing patterns in the codebase:
- Service class pattern similar to `CameraService`, `AIService`
- Database model pattern similar to `ProtectController` (encrypted credentials)
- API router pattern similar to `protect.py`, `cameras.py`

### Key Implementation Details

**Paho MQTT 2.0 Changes:**
- Use `mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)` for v2 callbacks
- Connection uses `client.connect_async()` for non-blocking connect
- Use `client.loop_start()` for background thread handling

**Auto-Reconnect Strategy:**
```python
RECONNECT_DELAYS = [1, 2, 4, 8, 16, 32, 60]  # seconds, max 60s

async def _reconnect_loop(self):
    attempt = 0
    while not self._connected and self._should_reconnect:
        delay = RECONNECT_DELAYS[min(attempt, len(RECONNECT_DELAYS) - 1)]
        await asyncio.sleep(delay)
        try:
            await self.connect()
        except Exception as e:
            logger.warning(f"Reconnect attempt {attempt + 1} failed: {e}")
            attempt += 1
```

**Credential Encryption:**
Use existing `EncryptionService` from `backend/app/services/encryption_service.py`:
```python
from app.services.encryption_service import encrypt_value, decrypt_value

# On save
encrypted_password = encrypt_value(plain_password)

# On load
plain_password = decrypt_value(encrypted_password)
```

### Project Structure Notes

New files to create:
- `backend/app/models/mqtt_config.py`
- `backend/app/services/mqtt_service.py`
- `backend/app/api/v1/integrations.py`
- `backend/alembic/versions/xxxx_add_mqtt_config_table.py`
- `backend/tests/test_services/test_mqtt_service.py`
- `backend/tests/test_api/test_integrations.py`

### Learnings from Previous Epic

**From Epic P4-1 (Push Notifications):**
- Service worker at `frontend/public/sw.js` already handles push - MQTT is backend-only
- Push subscription model at `backend/app/models/push_subscription.py` shows credential storage pattern
- Settings page has 8 tabs - MQTT will be 9th tab (Story P4-2.4)

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-p4-2.md#Services-and-Modules]
- [Source: docs/sprint-artifacts/tech-spec-epic-p4-2.md#Data-Models-and-Contracts]
- [Source: docs/PRD-phase4.md#FR15-FR18]
- [Source: docs/architecture.md#Phase-4-Additions]
- [Paho MQTT Python Docs](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html)

## Dev Agent Record

### Context Reference

- `docs/sprint-artifacts/p4-2-1-mqtt-client-implementation.context.xml`

### Agent Model Used

- Claude Opus 4.5

### Debug Log References

- All MQTT service tests passing (26 tests)
- All API schema tests passing (13 tests)

### Completion Notes List

- Implemented MQTTService with Paho MQTT 2.0+ client and CallbackAPIVersion.VERSION2
- Auto-reconnect uses exponential backoff: 1s, 2s, 4s, 8s, 16s, 32s, 60s (max)
- Password encryption using existing Fernet AES-256 via @validates decorator
- Prometheus metrics: mqtt_connection_status, mqtt_messages_published_total, mqtt_publish_errors_total, mqtt_reconnect_attempts_total
- QoS validation (0, 1, 2) and port validation (1-65535) in model
- Service initialized on app startup, graceful disconnect on shutdown
- Event serializer includes all required fields per tech spec

### File List

**New Files:**
- `backend/app/models/mqtt_config.py` - SQLAlchemy model with encrypted credentials
- `backend/app/services/mqtt_service.py` - MQTT service with auto-reconnect
- `backend/app/api/v1/integrations.py` - MQTT API endpoints
- `backend/alembic/versions/2b6ff2a9ef8b_add_mqtt_config_table.py` - Database migration
- `backend/tests/test_services/test_mqtt_service.py` - Service tests (26 tests)
- `backend/tests/test_api/test_integrations.py` - API schema tests (13 tests)

**Modified Files:**
- `backend/requirements.txt` - Added paho-mqtt>=2.0.0
- `backend/app/models/__init__.py` - Added MQTTConfig export
- `backend/app/core/metrics.py` - Added MQTT Prometheus metrics
- `backend/main.py` - Added MQTT lifecycle integration

---

## Change Log

| Date | Author | Change |
|------|--------|--------|
| 2025-12-10 | Claude Opus 4.5 | Initial story draft |
| 2025-12-10 | Claude Opus 4.5 | Story implementation complete |
