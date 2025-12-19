# Story P7-2.3: Add Package Delivery to HomeKit

Status: code-review

## Story

As a **homeowner using ArgusAI with HomeKit**,
I want **the HomeKit package sensor to trigger when a package delivery is detected with carrier information logged**,
so that **I can create HomeKit automations for package deliveries and debug carrier detection issues**.

## Acceptance Criteria

1. Existing package sensor triggered on delivery detection (when delivery_carrier is set on event)
2. Carrier info logged for debugging when HomeKit package sensor is triggered
3. Separate sensors per carrier option available via configuration (optional enhancement)
4. Delivery detection logged with carrier context

## Tasks / Subtasks

- [x] Task 1: Update HomeKit Package Trigger to Include Carrier (AC: 1, 2, 4)
  - [x] 1.1 Modify `trigger_package()` method signature to accept optional `delivery_carrier` parameter
  - [x] 1.2 Update `_trigger_homekit_package()` in event_processor.py to pass carrier from event
  - [x] 1.3 Add carrier to HomeKit package trigger logging (diagnostic_category: event)
  - [x] 1.4 Write unit tests for carrier in package trigger logging

- [x] Task 2: Add Per-Carrier Sensor Configuration (AC: 3)
  - [x] 2.1 Add `HOMEKIT_PER_CARRIER_SENSORS` environment variable (default: false)
  - [x] 2.2 Add `per_carrier_sensors` to HomekitConfig dataclass
  - [x] 2.3 Update homekit_service.py start() to create per-carrier sensors when enabled
  - [x] 2.4 Add `_carrier_sensors` dict mapping carrier -> sensor for per-carrier mode
  - [x] 2.5 Add `_trigger_carrier_sensor()` method for triggering specific carrier sensor
  - [x] 2.6 Update trigger_package() to call carrier-specific sensor when per-carrier mode enabled

- [x] Task 3: Add Per-Carrier Sensor Accessories (AC: 3)
  - [x] 3.1 Reuse existing `CameraPackageSensor` with carrier-specific names (no new class needed)
  - [x] 3.2 Add carrier-specific naming (e.g., "Front Door FedEx Package")
  - [x] 3.3 Added `_create_carrier_sensors()` method to create sensors per carrier
  - [x] 3.4 Write unit tests for carrier sensor creation

- [x] Task 4: Integration Testing (AC: 1, 2, 4)
  - [x] 4.1 Test package delivery triggers HomeKit package sensor when carrier is set
  - [x] 4.2 Test carrier info appears in HomeKit logs
  - [x] 4.3 Test per-carrier sensor mode creates separate sensors
  - [x] 4.4 Test per-carrier sensor triggers correct carrier sensor

## Dev Notes

### Architecture Constraints

- HomeKit package sensor already exists at `homekit_service.py:trigger_package()` [Source: backend/app/services/homekit_service.py:1427-1464]
- Carrier extracted from AI description and stored in `event.delivery_carrier` [Source: backend/app/services/carrier_extractor.py]
- Package detection triggers HomeKit via `event_processor.py:_trigger_homekit_package()` [Source: backend/app/services/event_processor.py:1684-1732]
- HomeKit configuration via environment variables [Source: backend/app/config/homekit.py]

### Existing Components to Modify

**Backend:**
- `backend/app/services/homekit_service.py` - Update `trigger_package()` with carrier parameter, add per-carrier sensor logic
- `backend/app/services/event_processor.py` - Pass carrier to `_trigger_homekit_package()`
- `backend/app/config/homekit.py` - Add `per_carrier_sensors` config option

**New Components:**
- Per-carrier sensor classes (if needed) - likely can reuse existing `CameraPackageSensor` with different name

### Current Implementation

The current `trigger_package()` method at line 1427 in homekit_service.py:

```python
def trigger_package(self, camera_id: str, event_id: Optional[int] = None) -> bool:
    """
    Trigger package detection for a camera (Story P5-1.6 AC3).
    Sets motion_detected = True and starts auto-reset timer.
    Package sensor has a longer timeout (60s) since packages persist.
    """
```

This needs to be enhanced to:
1. Accept optional `delivery_carrier` parameter
2. Log carrier info when triggering
3. Optionally route to carrier-specific sensor

### Carrier Values

From carrier extractor [Source: backend/app/services/carrier_extractor.py]:
- `fedex` → "FedEx"
- `ups` → "UPS"
- `usps` → "USPS"
- `amazon` → "Amazon"
- `dhl` → "DHL"

### Per-Carrier Sensor Design (Optional Feature)

When `HOMEKIT_PER_CARRIER_SENSORS=true`:
- Create additional package sensors per carrier: `{Camera} FedEx Package`, `{Camera} UPS Package`, etc.
- Trigger carrier-specific sensor when carrier is detected
- Fall back to generic package sensor when carrier is unknown

This allows HomeKit automations like:
- "When FedEx package detected, announce 'FedEx delivery'"
- "When Amazon package detected, turn on porch light"

### Testing Standards

- Backend: pytest with fixtures in `backend/tests/`
- Use existing HomeKit test patterns from `test_homekit_service.py`
- Mock Event objects with delivery_carrier field
- Test both with and without per-carrier sensors enabled

### Project Structure Notes

- Services in `backend/app/services/`
- Config in `backend/app/config/`
- Tests in `backend/tests/test_services/`

### Learnings from Previous Story

**From Story p7-2-2-create-package-delivery-alert-rule-type (Status: done)**

- **Carrier Extractor Service**: Created at `backend/app/services/carrier_extractor.py` with `extract_carrier()` function - use `CARRIER_DISPLAY_NAMES` mapping for display names
- **Event Model Change**: `delivery_carrier` field added to Event model - use this field in HomeKit trigger
- **Alert Engine Pattern**: Used `getattr(event, 'delivery_carrier', None)` pattern for safe access - follow same pattern
- **Logging Pattern**: Used `extra={}` dict with diagnostic categories for structured logging

[Source: docs/sprint-artifacts/p7-2-2-create-package-delivery-alert-rule-type.md#Dev-Agent-Record]

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P7-2.md] - Epic technical specification
- [Source: docs/epics-phase7.md#Story-P7-2.3] - Epic acceptance criteria
- [Source: docs/sprint-artifacts/p7-2-2-create-package-delivery-alert-rule-type.md] - Previous story (carrier in alerts)
- [Source: backend/app/services/homekit_service.py] - HomeKit service
- [Source: backend/app/services/event_processor.py] - Event processor
- [Source: backend/app/config/homekit.py] - HomeKit configuration

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p7-2-3-add-package-delivery-to-homekit.context.xml

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

N/A

### Completion Notes List

1. Added `delivery_carrier` parameter to `trigger_package()` in homekit_service.py
2. Updated `_trigger_homekit_package()` in event_processor.py to pass carrier from event
3. Added carrier info to all HomeKit package trigger logging with `diagnostic_category: event`
4. Added `per_carrier_sensors` config option to HomekitConfig
5. Added `HOMEKIT_PER_CARRIER_SENSORS` environment variable (default: false)
6. Added `_carrier_sensors` and `_carrier_reset_tasks` dicts for per-carrier sensor tracking
7. Added `_trigger_carrier_sensor()` method for triggering carrier-specific sensors
8. Added `_create_carrier_sensors()` method to create sensors for all supported carriers
9. Added `_carrier_reset_coroutine()` for auto-reset of carrier sensors
10. Added `carrier_sensor_count` property to HomekitService
11. Updated startup logging to include carrier sensor count
12. Added 13 new unit tests for Story P7-2.3 functionality

### File List

- `backend/app/services/homekit_service.py` - Updated trigger_package(), added carrier sensor support
- `backend/app/services/event_processor.py` - Updated _trigger_homekit_package() to pass carrier
- `backend/app/config/homekit.py` - Added per_carrier_sensors config option
- `backend/tests/test_services/test_homekit_detection_sensors.py` - Added 13 new tests

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2025-12-19 | Initial draft | SM Agent (YOLO workflow) |
| 2025-12-19 | Implementation complete | Dev Agent (YOLO workflow) |
