# Story P4-2.5: Camera Status Sensors

Status: done

## Story

As a **Home Assistant user**,
I want **camera status sensors published to MQTT including online/offline status, last event timestamp, and event counts**,
so that **I can create automations based on camera health and activity levels, and monitor my security system status from Home Assistant**.

## Acceptance Criteria

| # | Criteria | Verification |
|---|----------|--------------|
| 1 | Online/offline status sensor published for each camera | Disable camera, verify status change in HA |
| 2 | Last event timestamp sensor updates when new events occur | Create event, verify sensor timestamp updates |
| 3 | Event count sensors (today, this week) show accurate counts | Create events, verify counts match database |
| 4 | Binary sensor triggers on recent activity (event in last 5 minutes) | Create event, verify binary_sensor turns ON |
| 5 | Discovery configs published for all new sensor types | HA auto-discovers new sensors |
| 6 | Status sensors use correct MQTT topic format: `{topic_prefix}/camera/{camera_id}/status` | Subscribe to topic, verify format |
| 7 | All sensors grouped under same device in Home Assistant | HA device view shows all sensors together |
| 8 | Sensors update within 5 seconds of state change | Timing verification test |
| 9 | Offline cameras show "unavailable" in Home Assistant | Stop camera, verify HA shows unavailable |
| 10 | Event count sensors reset at midnight (daily) and Monday (weekly) | Verify reset logic via unit tests |

## Tasks / Subtasks

- [x] **Task 1: Add camera status tracking to MQTTService** (AC: 1, 9)
  - [x] Create `CameraStatusPayload` schema in `schemas/mqtt.py`
  - [x] Add `publish_camera_status()` method to MQTTService
  - [x] Track camera online/offline state changes
  - [x] Publish status updates on camera state change
  - [x] Handle unavailable state for stopped cameras

- [x] **Task 2: Implement last event timestamp sensor** (AC: 2, 8)
  - [x] Add `publish_last_event_timestamp()` method
  - [x] Hook into event_processor to call on new events
  - [x] Include event_id and description snippet in payload
  - [x] Ensure <5s latency from event to MQTT publish

- [x] **Task 3: Implement event count sensors** (AC: 3, 10)
  - [x] Create `get_event_counts()` helper in CameraService
  - [x] Calculate today_count, week_count from database
  - [x] Add `publish_event_counts()` method to MQTTService
  - [x] Implement scheduled count updates (every 5 minutes)
  - [x] Handle count reset at midnight/Monday boundaries

- [x] **Task 4: Implement binary activity sensor** (AC: 4)
  - [x] Add `publish_activity_state()` method
  - [x] Set ON when event created in last 5 minutes
  - [x] Set OFF after 5-minute timeout (via scheduler)
  - [x] Use `binary_sensor` discovery type in HA

- [x] **Task 5: Create HA discovery configs for new sensors** (AC: 5, 6, 7)
  - [x] Add `publish_status_discovery()` for online/offline sensor
  - [x] Add `publish_timestamp_discovery()` for last_event sensor
  - [x] Add `publish_counts_discovery()` for count sensors
  - [x] Add `publish_activity_discovery()` for binary sensor
  - [x] Ensure all sensors use same `device` block for grouping

- [x] **Task 6: Integrate with existing camera lifecycle** (AC: 1, 9)
  - [x] Hook camera enable/disable to status publish
  - [x] Hook camera start/stop to status publish
  - [x] Hook camera connection errors to status publish
  - [x] Update discovery on camera add/delete

- [x] **Task 7: Write unit tests** (AC: all)
  - [x] Test status payload serialization
  - [x] Test count calculations (daily/weekly)
  - [x] Test count reset at midnight
  - [x] Test activity sensor timeout logic
  - [x] Test discovery config structure

- [x] **Task 8: Write integration tests** (AC: all)
  - [x] Test full flow: event → MQTT publish → payload validation
  - [x] Test camera status changes → MQTT updates
  - [x] Test with mock MQTT broker

## Dev Notes

### Architecture Alignment

This story extends the MQTT integration implemented in P4-2.1 through P4-2.4. The `MQTTService` already handles connection management and event publishing. This story adds camera status sensors as additional MQTT entities.

**Component Flow:**
```
Camera State Change → CameraService → MQTTService.publish_camera_status()
                                              ↓
                                    MQTT Topic: liveobject/camera/{id}/status

Event Created → EventProcessor → MQTTService.publish_last_event_timestamp()
                                              ↓
                                    MQTT Topic: liveobject/camera/{id}/last_event
```

### Key Implementation Details

**New MQTT Topics:**
- `{topic_prefix}/camera/{camera_id}/status` - Online/offline status
- `{topic_prefix}/camera/{camera_id}/last_event` - Last event timestamp
- `{topic_prefix}/camera/{camera_id}/counts` - Event counts (today/week)
- `{topic_prefix}/camera/{camera_id}/activity` - Binary activity state

**Status Payload Schema:**
```python
class CameraStatusPayload(BaseModel):
    camera_id: str
    camera_name: str
    status: Literal["online", "offline", "unavailable"]
    source_type: str  # "rtsp", "usb", "protect"
    last_updated: datetime
```

**Counts Payload Schema:**
```python
class CameraCountsPayload(BaseModel):
    camera_id: str
    camera_name: str
    events_today: int
    events_this_week: int
    last_updated: datetime
```

**Activity Payload Schema:**
```python
class CameraActivityPayload(BaseModel):
    camera_id: str
    state: Literal["ON", "OFF"]
    last_event_at: Optional[datetime]
```

**Discovery Config for Binary Sensor:**
```json
{
  "name": "Front Door Activity",
  "unique_id": "liveobject_camera_uuid_activity",
  "state_topic": "liveobject/camera/uuid/activity",
  "value_template": "{{ value_json.state }}",
  "payload_on": "ON",
  "payload_off": "OFF",
  "device_class": "motion",
  "device": {
    "identifiers": ["liveobject_camera_uuid"],
    "name": "Front Door Camera",
    "manufacturer": "Live Object AI",
    "model": "AI Classifier"
  }
}
```

### Project Structure Notes

**Files to create:**
- `backend/app/schemas/mqtt.py` - Payload schemas (if not already present)

**Files to modify:**
- `backend/app/services/mqtt_service.py` - Add status sensor methods
- `backend/app/services/event_processor.py` - Hook for last_event publish
- `backend/app/services/camera_service.py` - Hook for status changes
- `backend/app/services/protect_service.py` - Hook for Protect camera status

### Learnings from Previous Story

**From Story P4-2.4 (Integration Settings UI) (Status: done)**

- **MQTTService Singleton**: Available via `get_mqtt_service()` dependency
- **Existing Discovery Method**: `publish_discovery()` method exists for event sensors
- **Topic Format**: Uses `{topic_prefix}/camera/{camera_id}/event` pattern
- **Device Block**: All sensors grouped under same device identifiers
- **Connection Check**: Always check `is_connected` before publishing

**Reusable Patterns:**
- Use `MQTTSettings.tsx` component for any UI additions
- Follow existing `publish()` method signature in MQTTService
- Discovery configs follow Home Assistant MQTT Discovery spec
- Use `retain=True` for status messages

**Files Created in Previous Stories:**
- `backend/app/services/mqtt_service.py` (P4-2.1)
- `backend/app/api/v1/integrations.py` (P4-2.1)
- `backend/app/models/mqtt_config.py` (P4-2.1)
- `frontend/components/settings/MQTTSettings.tsx` (P4-2.4)

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-p4-2.md#Story-P4-2.5-Camera-Status-Sensors]
- [Source: docs/epics-phase4.md#Story-P4-2.5-Camera-Status-Sensors]
- [Source: docs/architecture.md#Phase-4-Additions - MQTT Publishing Flow]
- [Source: docs/PRD-phase4.md#FR18 - Camera online/offline status]
- [Home Assistant MQTT Discovery Documentation](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery)

## Dev Agent Record

### Context Reference

- [p4-2-5-camera-status-sensors.context.xml](./p4-2-5-camera-status-sensors.context.xml)

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

N/A - No debug logs required for this implementation

### Completion Notes List

1. **MQTT Payload Schemas Created**: Added `CameraStatusPayload`, `CameraCountsPayload`, `CameraActivityPayload`, and `LastEventPayload` schemas in `backend/app/schemas/mqtt.py`

2. **Status Sensor Methods Added**: Extended `MQTTService` with `publish_camera_status()`, `publish_last_event_timestamp()`, `publish_event_counts()`, and `publish_activity_state()` methods

3. **Discovery Configs Extended**: Added discovery config generators for all 6 sensor types (event, status, last_event, events_today, events_week, activity) in `MQTTDiscoveryService`. All sensors share the same device block for HA grouping.

4. **Status Service Created**: New `mqtt_status_service.py` handles event count calculations, activity timeout tracking, and scheduled updates

5. **Camera Lifecycle Integration**: Updated `camera_service.py` `_update_status()` and `stop_camera()` methods to publish MQTT status updates on camera state changes

6. **Event Processor Integration**: Added Step 8 in `event_processor.py` to publish last_event, activity state, and event counts after each event is processed

7. **Startup Initialization**: Added `initialize_status_sensors()` call in `main.py` to publish initial camera statuses and set up scheduled tasks (count updates every 5 minutes, activity timeout checks every 1 minute)

8. **Test Coverage**: 28 unit tests + 12 integration tests = 40 total tests passing

### File List

**New Files:**
- `backend/app/schemas/mqtt.py` - MQTT payload schemas
- `backend/app/services/mqtt_status_service.py` - Status sensor service
- `backend/tests/test_services/test_mqtt_status_sensors.py` - Unit tests
- `backend/tests/test_integration/test_mqtt_status_integration.py` - Integration tests

**Modified Files:**
- `backend/app/services/mqtt_service.py` - Added status sensor methods
- `backend/app/services/mqtt_discovery_service.py` - Added discovery configs for new sensors
- `backend/app/services/camera_service.py` - Added MQTT status publish hooks
- `backend/app/services/event_processor.py` - Added status sensor publish on event
- `backend/main.py` - Added status sensor initialization

---

## Change Log

| Date | Author | Change |
|------|--------|--------|
| 2025-12-11 | Claude Opus 4.5 | Initial story draft |
