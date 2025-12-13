# Story P4-6.2: HomeKit Motion Events

**Epic:** P4-6 Voice Assistant Integration (Growth)
**Status:** drafted
**Created:** 2025-12-12
**Story Key:** p4-6-2-homekit-motion-events

---

## User Story

**As a** HomeKit user with ArgusAI cameras configured
**I want** motion sensors to trigger when AI events are detected
**So that** I can create Apple Home automations (lights, notifications, recordings) based on real security events

---

## Background & Context

Story P4-6.1 established the HomeKit accessory server infrastructure with HAP-python, creating motion sensor accessories for each camera. This story completes the integration by wiring actual AI-detected events to trigger the motion sensors in HomeKit.

When an event is processed through the AI pipeline and generates a description, the HomeKit motion sensor for that camera should activate, allowing Apple Home automations to respond to security events.

---

## Acceptance Criteria

### AC1: Event-to-HomeKit Integration
- [ ] When an event is created (via event_processor.py), trigger the HomeKit motion sensor for the corresponding camera
- [ ] Motion sensor should set `motion_detected = True` in HomeKit
- [ ] HomeKit state update should occur within 1 second of event creation

### AC2: Motion Reset Timer
- [ ] Motion sensor resets to `motion_detected = False` after configurable timeout (default: 30 seconds)
- [ ] Timeout is configurable via environment variable `HOMEKIT_MOTION_RESET_SECONDS`
- [ ] If a new event occurs during timeout, the timer resets (extends the motion period)

### AC3: Rapid Event Handling
- [ ] Multiple events within the reset window maintain `motion_detected = True`
- [ ] Each new event resets the timeout, preventing premature reset
- [ ] System handles burst of events (e.g., 10 events in 5 seconds) without errors

### AC4: Camera-Event Mapping
- [ ] Events correctly map to their camera's HomeKit motion sensor
- [ ] Protect cameras (by MAC address) map to correct accessory
- [ ] RTSP/USB cameras (by camera_id) map to correct accessory
- [ ] Unmapped cameras (new camera added after HomeKit start) log warning but don't crash

### AC5: State Synchronization
- [ ] HomeKit motion state reflects actual event activity
- [ ] If HomeKit service restarts, motion sensors reset to `False`
- [ ] Long-running motion (continuous activity) eventually resets after max duration (5 minutes)

### AC6: Error Resilience
- [ ] Event processing continues if HomeKit service is unavailable
- [ ] Failed HomeKit updates logged but don't block event pipeline
- [ ] Service recovers gracefully after HomeKit reconnection

### AC7: Testing
- [ ] Unit tests for motion trigger logic
- [ ] Unit tests for reset timer behavior
- [ ] Integration test for event-to-HomeKit flow
- [ ] Test for rapid event handling

---

## Technical Implementation

### Task 1: Add Motion Trigger Method to HomeKit Service
**File:** `backend/app/services/homekit_service.py`
- Add `trigger_motion(camera_id: str | int, event_id: int | None = None)` method
- Lookup camera's motion sensor accessory
- Set `motion_detected = True` on the accessory
- Start/reset the motion reset timer
- Log the trigger with camera and event details

### Task 2: Implement Motion Reset Timer
**File:** `backend/app/services/homekit_service.py`
- Add asyncio timer for each camera's motion state
- On trigger: cancel existing timer, start new one
- On timeout: set `motion_detected = False`
- Add `HOMEKIT_MOTION_RESET_SECONDS` config (default: 30)
- Add max motion duration cap (5 minutes) to prevent stuck state

### Task 3: Update CameraMotionSensor Accessory
**File:** `backend/app/services/homekit_accessories.py`
- Ensure `motion_detected` property is properly settable
- Add method to programmatically trigger motion
- Implement proper HAP callback for state changes
- Handle characteristic value updates correctly

### Task 4: Integrate with Event Processor
**File:** `backend/app/services/event_processor.py`
- Import HomeKit service
- After event is saved to database, call `trigger_motion()`
- Make HomeKit call non-blocking (fire and forget)
- Handle case where HomeKit service is disabled/unavailable

### Task 5: Add Motion Reset Configuration
**File:** `backend/app/core/config.py`
- Add `HOMEKIT_MOTION_RESET_SECONDS: int = 30`
- Add `HOMEKIT_MAX_MOTION_DURATION: int = 300` (5 minutes)

**File:** `backend/app/config/homekit.py`
- Add `motion_reset_seconds` to HomekitConfig
- Add `max_motion_duration` to HomekitConfig

### Task 6: Add Camera ID Mapping
**File:** `backend/app/services/homekit_service.py`
- Create mapping from camera_id/mac_address to HomeKit accessory
- Handle Protect cameras (use MAC address)
- Handle RTSP/USB cameras (use camera_id)
- Add method `get_accessory_for_camera(camera: Camera)`

### Task 7: Write Unit Tests
**File:** `backend/tests/test_services/test_homekit_motion.py`
- Test `trigger_motion()` sets motion state
- Test reset timer behavior
- Test rapid event handling
- Test camera ID mapping
- Test error resilience (HomeKit unavailable)

### Task 8: Integration with Main Lifecycle
**File:** `backend/main.py`
- Ensure HomeKit service receives camera updates when cameras change
- On new camera added, create accessory if HomeKit running
- On camera removed, remove accessory

---

## Dependencies

- **Story P4-6.1** (HomeKit Accessory Server) - Must be complete (provides base infrastructure)
- **HAP-python** library must be installed
- **Event processor** service must be operational

---

## Out of Scope

- HomeKit notifications (handled by Apple Home based on automation)
- Voice query responses (Story P4-6.3)
- Custom HomeKit accessory categories beyond motion sensors
- HomeKit Secure Video integration

---

## Definition of Done

- [ ] All acceptance criteria verified
- [ ] Unit tests passing
- [ ] Integration tests passing
- [ ] No TypeScript/Python type errors
- [ ] Backend continues working if HomeKit disabled
- [ ] Motion triggers visible in Apple Home app (manual verification)
- [ ] Documentation updated (CLAUDE.md if needed)
