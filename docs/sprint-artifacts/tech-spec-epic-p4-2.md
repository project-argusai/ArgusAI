# Epic Technical Specification: Home Assistant Integration

Date: 2025-12-10
Author: Brent
Epic ID: P4-2
Status: Draft

---

## Overview

Epic P4-2 enables seamless integration with Home Assistant via MQTT, allowing users to create smart home automations based on AI-detected events. This transforms the Live Object AI Classifier from a standalone monitoring system into a connected hub that can trigger actions across the entire smart home ecosystem.

The integration uses MQTT Discovery protocol for automatic sensor registration in Home Assistant, publishes event data in real-time, and provides status sensors for each camera.

## Objectives and Scope

### In Scope

- MQTT client implementation with Paho MQTT library
- Connection management with auto-reconnect and retry logic
- Home Assistant MQTT Discovery for automatic sensor registration
- Event publishing to camera-specific topics
- Camera status sensors (online/offline, last event, event counts)
- Settings UI for MQTT broker configuration
- Connection testing functionality
- QoS settings for message reliability

### Out of Scope

- HomeKit Accessory Protocol integration (Epic P4-6)
- Direct Alexa/Google Home integration (handled via Home Assistant bridge)
- Two-way communication (HA controlling cameras)
- MQTT broker hosting (user provides their own broker)
- SSL/TLS certificate management UI

## System Architecture Alignment

### Component Integration

This epic integrates with the existing event processing pipeline:

```
Event Processor → AI Service → Database → MQTT Service → Home Assistant
                                            ↓
                                     Event Published
```

### Architecture References

- **Event Processor** (`backend/app/services/event_processor.py`): Add MQTT publish hook after event creation
- **Settings System** (`backend/app/services/settings_service.py`): Store MQTT configuration
- **Database Models** (`backend/app/models/`): Add MQTT config model
- **API Layer** (`backend/app/api/v1/`): Add integrations endpoints

### Key Constraints

- MQTT publishing must not block event processing (<100ms latency target)
- Connection failures must not crash the application
- Auto-reconnect must restore publishing without manual intervention
- Configuration changes must take effect without server restart

## Detailed Design

### Services and Modules

| Service | Responsibility | Input | Output |
|---------|----------------|-------|--------|
| `MQTTService` | Manage MQTT connection lifecycle | Config from settings | Connection state |
| `MQTTPublisher` | Publish events to topics | Event data | Published message |
| `MQTTDiscovery` | Send HA discovery payloads | Camera list | Registered sensors |
| `MQTTStatusTracker` | Track camera status changes | Camera state | Status updates |

### Service Implementation

**MQTTService** (`backend/app/services/mqtt_service.py`)
```python
class MQTTService:
    """MQTT connection manager with auto-reconnect."""

    def __init__(self, config: MQTTConfig):
        self.client = mqtt.Client(client_id=f"liveobject-{uuid.uuid4().hex[:8]}")
        self.config = config
        self._connected = False
        self._reconnect_delay = 1  # exponential backoff

    async def connect(self) -> bool:
        """Establish connection to MQTT broker."""

    async def disconnect(self) -> None:
        """Gracefully disconnect from broker."""

    async def publish(self, topic: str, payload: dict, qos: int = 1) -> bool:
        """Publish message to topic with QoS."""

    def on_disconnect(self, client, userdata, rc):
        """Handle disconnection with auto-reconnect."""
```

### Data Models and Contracts

**MQTT Configuration Model** (`backend/app/models/mqtt_config.py`)
```python
class MQTTConfig(Base):
    __tablename__ = "mqtt_config"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    broker_host: Mapped[str] = mapped_column(String(255), nullable=False)
    broker_port: Mapped[int] = mapped_column(Integer, default=1883)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password: Mapped[str | None] = mapped_column(Text, nullable=True)  # Encrypted
    topic_prefix: Mapped[str] = mapped_column(String(100), default="liveobject")
    discovery_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    discovery_prefix: Mapped[str] = mapped_column(String(100), default="homeassistant")
    qos: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    retain_messages: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
```

**Event Payload Schema** (published to MQTT)
```json
{
  "event_id": "uuid",
  "camera_id": "uuid",
  "camera_name": "Front Door",
  "description": "Person at door with package",
  "objects_detected": ["person", "package"],
  "confidence": 85,
  "source_type": "protect",
  "smart_detection_type": "person",
  "timestamp": "2025-12-10T14:30:00Z",
  "thumbnail_url": "http://host:8000/api/v1/events/{id}/thumbnail"
}
```

**Discovery Config Payload** (for Home Assistant)
```json
{
  "name": "Front Door AI Events",
  "unique_id": "liveobject_camera_uuid_event",
  "state_topic": "liveobject/camera/uuid/event",
  "value_template": "{{ value_json.description[:255] }}",
  "json_attributes_topic": "liveobject/camera/uuid/event",
  "icon": "mdi:cctv",
  "device": {
    "identifiers": ["liveobject_camera_uuid"],
    "name": "Front Door Camera",
    "manufacturer": "Live Object AI",
    "model": "AI Classifier",
    "sw_version": "4.0.0"
  }
}
```

### APIs and Interfaces

**GET /api/v1/integrations/mqtt/config**
- Get current MQTT configuration
- Response: `MQTTConfigResponse` with password omitted

**PUT /api/v1/integrations/mqtt/config**
- Update MQTT configuration
- Request: `MQTTConfigUpdate`
- Triggers reconnect if enabled

**GET /api/v1/integrations/mqtt/status**
- Get connection status
- Response:
```json
{
  "connected": true,
  "broker": "192.168.1.100:1883",
  "last_connected_at": "2025-12-10T14:00:00Z",
  "messages_published": 1234,
  "last_error": null
}
```

**POST /api/v1/integrations/mqtt/test**
- Test MQTT connection (doesn't persist config)
- Request: `MQTTTestRequest` with broker details
- Response: `{ "success": true, "message": "Connected successfully" }`

**POST /api/v1/integrations/mqtt/publish-discovery**
- Manually trigger discovery payload publishing
- Used after adding new cameras

### Workflows and Sequencing

**Connection Flow:**
```
1. App Startup
   └─→ Load MQTT config from DB
       └─→ If enabled, connect to broker
           └─→ On success: Publish discovery configs
           └─→ On failure: Schedule reconnect (exponential backoff)

2. Event Created
   └─→ Event Processor signals new event
       └─→ MQTT Service checks connection
           └─→ If connected: Publish to camera topic
           └─→ If disconnected: Log warning (non-blocking)

3. Camera Added/Updated
   └─→ Publish discovery config for camera
       └─→ Home Assistant auto-discovers sensor

4. Camera Deleted
   └─→ Publish empty payload to discovery topic (removes sensor)
```

**Discovery Message Flow:**
```
On Connect:
  For each enabled camera:
    1. Publish sensor config to homeassistant/sensor/liveobject_{camera_id}_event/config
    2. Publish binary_sensor config to homeassistant/binary_sensor/liveobject_{camera_id}_activity/config
    3. Publish sensor config to homeassistant/sensor/liveobject_{camera_id}_status/config
```

## Non-Functional Requirements

### Performance

| Metric | Target | Measurement |
|--------|--------|-------------|
| MQTT publish latency | <100ms p95 | From event creation to publish complete |
| Connection time | <5 seconds | Initial connection to broker |
| Reconnect time | <30 seconds | After disconnection detection |
| Memory overhead | <50MB | MQTT client + message queue |

### Security

- Broker credentials encrypted at rest using Fernet (existing encryption system)
- Support for MQTT authentication (username/password)
- TLS/SSL support via `mqtts://` scheme (port 8883)
- No sensitive data (API keys, passwords) in MQTT payloads
- Thumbnail URLs require authentication to access

### Reliability/Availability

- Auto-reconnect with exponential backoff (1s, 2s, 4s, ... max 60s)
- Message queue for events during disconnection (limited to 100 messages)
- Graceful degradation: MQTT failure doesn't block event processing
- Connection state persisted for status reporting

### Observability

- Log MQTT connection events at INFO level
- Log publish failures at WARNING level
- Prometheus metrics:
  - `mqtt_connection_status` (gauge: 0=disconnected, 1=connected)
  - `mqtt_messages_published_total` (counter)
  - `mqtt_publish_errors_total` (counter)
  - `mqtt_reconnect_attempts_total` (counter)
- Health check endpoint includes MQTT status

## Dependencies and Integrations

### New Backend Dependencies

```
paho-mqtt>=2.0.0  # MQTT client library
```

### External Dependencies

| Dependency | Purpose | Version Constraint |
|------------|---------|-------------------|
| MQTT Broker | Message transport | Mosquitto 2.x recommended |
| Home Assistant | Automation platform | 2024.1+ for MQTT Discovery |

### Internal Dependencies

- `SettingsService`: Store and retrieve MQTT config
- `EventProcessor`: Hook for publish trigger
- `CameraService`: Camera list for discovery
- `EncryptionService`: Encrypt broker credentials

## Acceptance Criteria (Authoritative)

### Story P4-2.1: MQTT Client Implementation
| # | Criteria | Verification |
|---|----------|--------------|
| 1 | Paho MQTT client connects to configured broker | Unit test with mock broker |
| 2 | Auto-reconnect activates on connection loss | Integration test with broker restart |
| 3 | Event payloads serialized correctly to JSON | Unit test payload validation |
| 4 | QoS levels 0, 1, 2 supported | Config test with each QoS level |
| 5 | Connection status tracked and queryable | API test for status endpoint |

### Story P4-2.2: Home Assistant Discovery
| # | Criteria | Verification |
|---|----------|--------------|
| 1 | Discovery config published on connect | Integration test with HA |
| 2 | Sensor entity appears in Home Assistant | Manual test with HA instance |
| 3 | Device grouping shows all camera sensors together | HA UI verification |
| 4 | Sensor removal works when camera deleted | Delete camera, verify HA sensor gone |

### Story P4-2.3: Event Publishing
| # | Criteria | Verification |
|---|----------|--------------|
| 1 | Events published to camera-specific topic | Subscribe to topic, verify receipt |
| 2 | Payload includes all required fields | Schema validation test |
| 3 | Thumbnail URL accessible | Fetch URL from payload, verify image |
| 4 | QoS setting respected | Wireshark/broker log verification |
| 5 | Publishing doesn't block event processing | Latency measurement test |

### Story P4-2.4: Integration Settings UI
| # | Criteria | Verification |
|---|----------|--------------|
| 1 | MQTT tab appears in settings page | Visual inspection |
| 2 | Broker host/port/credentials configurable | Form submission test |
| 3 | Test connection button works | Test with valid/invalid brokers |
| 4 | Connection status displayed in real-time | UI shows connected/disconnected |
| 5 | Save triggers reconnect with new config | Change settings, verify reconnect |

### Story P4-2.5: Camera Status Sensors
| # | Criteria | Verification |
|---|----------|--------------|
| 1 | Online/offline status published | Disable camera, verify status change |
| 2 | Last event timestamp sensor updates | Create event, verify sensor update |
| 3 | Event count sensors (today/week) accurate | Create events, verify counts |
| 4 | Binary sensor triggers on recent activity | Create event, verify binary_sensor on |

## Traceability Mapping

| AC | Spec Section | Component | Test Approach |
|----|--------------|-----------|---------------|
| P4-2.1 AC1-5 | Services/MQTTService | mqtt_service.py | Unit + Integration |
| P4-2.2 AC1-4 | Workflows/Discovery | mqtt_service.py | Integration with HA |
| P4-2.3 AC1-5 | Data Models/Payload | event_processor.py | Unit + E2E |
| P4-2.4 AC1-5 | APIs/Config | integrations.py, MQTTSettings.tsx | API + E2E |
| P4-2.5 AC1-4 | Data Models/Status | mqtt_service.py | Integration |

## Risks, Assumptions, Open Questions

### Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| MQTT broker unavailable | Events not published to HA | Medium | Queue messages, graceful degradation |
| Home Assistant version incompatibility | Discovery fails | Low | Follow official MQTT Discovery spec |
| High event volume overwhelms broker | Message backlog | Low | QoS settings, rate limiting |
| Network latency spikes | Publish timeouts | Medium | Async publishing, timeouts |

### Assumptions

- User has access to an MQTT broker (Mosquitto, EMQX, or HA addon)
- Home Assistant is on the same network as the classifier
- MQTT Discovery is enabled in Home Assistant
- User understands basic MQTT concepts (topics, QoS)

### Open Questions

1. **Resolved:** Should we bundle Mosquitto? No - users provide their own broker
2. **Pending:** Support for MQTT 5.0 features (message expiry, shared subscriptions)?
3. **Pending:** Should we implement birth/will messages for connection monitoring?

## Test Strategy Summary

### Test Levels

| Level | Scope | Framework | Coverage Target |
|-------|-------|-----------|-----------------|
| Unit | MQTTService methods | pytest + unittest.mock | 80% |
| Integration | Broker connection, publish | pytest + paho-mqtt | Key flows |
| E2E | Settings UI → HA sensor | Playwright + HA instance | Happy paths |

### Key Test Scenarios

1. **Connection Tests:**
   - Connect with valid credentials
   - Connection refused (wrong host)
   - Auth failed (wrong credentials)
   - Reconnect after broker restart

2. **Publishing Tests:**
   - Publish event, verify payload structure
   - Publish with QoS 1, verify acknowledgment
   - Publish during disconnection, verify queue

3. **Discovery Tests:**
   - Verify discovery config structure
   - Sensor appears in HA after discovery
   - Sensor removed after camera deletion

4. **UI Tests:**
   - Form validation for required fields
   - Test connection success/failure feedback
   - Status indicator updates

### Edge Cases

- Broker disconnects during publish
- Very long camera names (truncation)
- Special characters in topic prefix
- Rapid event bursts (rate limiting)
- Configuration changes while publishing

---

## Change Log

| Date | Author | Change |
|------|--------|--------|
| 2025-12-10 | Claude Opus 4.5 | Initial tech spec generation |
