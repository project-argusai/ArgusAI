# Story P7-2.1: Add Carrier Detection to AI Analysis

Status: done

## Story

As a **homeowner using ArgusAI**,
I want **the AI to identify delivery carriers (FedEx, UPS, USPS, Amazon, DHL) when analyzing camera footage**,
so that **I know which carrier delivered my packages and can set up carrier-specific alerts**.

## Acceptance Criteria

1. AI prompt updated to identify FedEx, UPS, USPS, Amazon, DHL carriers
2. `delivery_carrier` field added to Event model (migration required)
3. Carrier extracted from AI description using pattern matching
4. Carrier stored in event record when detected
5. Carrier returned in event API responses (`delivery_carrier` and `delivery_carrier_display` fields)

## Tasks / Subtasks

- [x] Task 1: Update AI Prompt for Carrier Detection (AC: 1)
  - [x] 1.1 Enhance base prompt in `ai_service.py` to instruct AI to identify carriers
  - [x] 1.2 Add carrier identification prompt section with visual cues (colors, logos)
  - [x] 1.3 Ensure prompt works for all supported AI providers (OpenAI, Grok, Claude, Gemini)
  - [x] 1.4 Write unit test verifying prompt includes carrier detection instructions

- [x] Task 2: Add delivery_carrier Field to Event Model (AC: 2)
  - [x] 2.1 Add `delivery_carrier` nullable String(32) column to Event model
  - [x] 2.2 Create Alembic migration for the new column
  - [x] 2.3 Run and verify migration applies successfully
  - [x] 2.4 Write test to verify schema change

- [x] Task 3: Implement CarrierExtractor Service (AC: 3)
  - [x] 3.1 Create `carrier_extractor.py` in `backend/app/services/`
  - [x] 3.2 Define CARRIER_PATTERNS dict with regex patterns for each carrier
  - [x] 3.3 Implement `extract_carrier(description: str) -> Optional[str]` function
  - [x] 3.4 Return lowercase carrier name or None if not detected
  - [x] 3.5 Write comprehensive unit tests for pattern matching (10+ per carrier)

- [x] Task 4: Integrate Carrier Extraction into Event Pipeline (AC: 4)
  - [x] 4.1 Import CarrierExtractor in `event_processor.py`
  - [x] 4.2 Call `extract_carrier()` after AI description is generated
  - [x] 4.3 Set `event.delivery_carrier` when carrier is detected
  - [x] 4.4 Log carrier extraction success/failure for observability
  - [x] 4.5 Write integration test verifying carrier saved in event record

- [x] Task 5: Update Event Schemas and API Responses (AC: 5)
  - [x] 5.1 Add `delivery_carrier` field to `EventResponse` schema
  - [x] 5.2 Add `delivery_carrier_display` computed field (capitalized carrier name)
  - [x] 5.3 Add CARRIER_DISPLAY_NAMES mapping dict
  - [x] 5.4 Write API integration test verifying carrier in GET /api/v1/events response
  - [x] 5.5 Write API test for GET /api/v1/events/{id} with carrier field

## Dev Notes

### Architecture Constraints

- AI prompt enhancement must not significantly increase token usage [Source: docs/sprint-artifacts/tech-spec-epic-P7-2.md#NFRs]
- Carrier extraction must complete in <10ms (regex-based pattern matching) [Source: docs/sprint-artifacts/tech-spec-epic-P7-2.md#NFRs]
- Failed carrier extraction should NOT fail event processing (best-effort detection)
- Event model uses SQLAlchemy 2.0 with Alembic migrations [Source: CLAUDE.md]

### Existing Components to Modify

- `backend/app/services/ai_service.py` - Add carrier detection to prompts
- `backend/app/models/event.py` - Add delivery_carrier column
- `backend/app/schemas/event.py` - Add delivery_carrier to response schemas
- `backend/app/services/event_processor.py` - Integrate carrier extraction

### New Components to Create

- `backend/app/services/carrier_extractor.py` - Pattern matching service
- `backend/alembic/versions/xxxx_add_delivery_carrier_to_events.py` - Migration

### Carrier Detection Patterns

From tech spec [Source: docs/sprint-artifacts/tech-spec-epic-P7-2.md#Data-Models]:

```python
CARRIER_PATTERNS = {
    'fedex': [r'fedex', r'fed\s*ex', r'federal\s*express'],
    'ups': [r'\bups\b', r'united\s*parcel'],
    'usps': [r'usps', r'postal\s*service', r'mail\s*carrier', r'mailman'],
    'amazon': [r'amazon', r'prime'],
    'dhl': [r'\bdhl\b', r'dhl\s*express'],
}

CARRIER_DISPLAY_NAMES = {
    'fedex': 'FedEx',
    'ups': 'UPS',
    'usps': 'USPS',
    'amazon': 'Amazon',
    'dhl': 'DHL',
}
```

### AI Prompt Enhancement

From tech spec [Source: docs/sprint-artifacts/tech-spec-epic-P7-2.md#Workflows]:

```
If you see a delivery person or truck, identify the carrier:
- FedEx (purple/orange colors, FedEx logo)
- UPS (brown uniform, brown truck)
- USPS (blue uniform, postal logo, mail truck)
- Amazon (blue vest, Amazon logo, Amazon van)
- DHL (yellow/red colors, DHL logo)
Include the carrier name in your description.
```

### Testing Standards

- Backend: pytest with fixtures in `backend/tests/`
- Use existing test patterns from `backend/tests/test_services/`
- Mock AI responses with carrier mentions for integration tests
- Test carrier extraction with various description formats

### Project Structure Notes

- Services in `backend/app/services/`
- Models in `backend/app/models/`
- Schemas in `backend/app/schemas/`
- Migrations in `backend/alembic/versions/`
- Tests in `backend/tests/`

### Learnings from Previous Story

**From Story p7-1-4-add-homekit-connection-status-monitoring (Status: done)**

- **Schema Pattern**: Added new fields to response schemas (like `sensor_deliveries`, `camera_name`) - follow same pattern for `delivery_carrier`
- **Service Pattern**: Enhanced existing service with new functionality - follow for `event_processor.py`
- **Test Pattern**: Added dedicated test class for new feature (`TestPerSensorDeliveryTracking`) - create `TestCarrierExtraction`

[Source: docs/sprint-artifacts/p7-1-4-add-homekit-connection-status-monitoring.md#Dev-Agent-Record]

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P7-2.md] - Epic technical specification
- [Source: docs/epics-phase7.md#Story-P7-2.1] - Epic acceptance criteria
- [Source: docs/sprint-artifacts/p7-1-4-add-homekit-connection-status-monitoring.md] - Previous story patterns
- [Source: backend/app/services/ai_service.py] - Existing AI service
- [Source: backend/app/models/event.py] - Event model
- [Source: backend/app/schemas/event.py] - Event schemas
- [Source: backend/app/services/event_processor.py] - Event processing pipeline

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p7-2-1-add-carrier-detection-to-ai-analysis.context.xml

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

### Completion Notes List

- **AC1 Complete**: Updated AI prompts in both `user_prompt_template` (line 190-204) and `MULTI_FRAME_SYSTEM_PROMPT` (line 76-83) with carrier detection instructions
- **AC2 Complete**: Added `delivery_carrier` String(32) column to Event model with migration `050_add_delivery_carrier_to_events.py`
- **AC3 Complete**: Created `carrier_extractor.py` with compiled regex patterns for FedEx, UPS, USPS, Amazon, DHL - performance <10ms for 500 extractions
- **AC4 Complete**: Integrated carrier extraction in `event_processor.py` after AI description generation with error handling (best-effort detection)
- **AC5 Complete**: Added `delivery_carrier` and `delivery_carrier_display` fields to EventResponse schema with model_validator for display name computation; updated both `list_events` and `get_event` endpoints

### File List

**New Files:**
- backend/app/services/carrier_extractor.py
- backend/alembic/versions/050_add_delivery_carrier_to_events.py
- backend/tests/test_services/test_carrier_extractor.py

**Modified Files:**
- backend/app/services/ai_service.py (added carrier detection prompts)
- backend/app/models/event.py (added delivery_carrier column)
- backend/app/schemas/event.py (added delivery_carrier, delivery_carrier_display fields)
- backend/app/services/event_processor.py (integrated carrier extraction)
- backend/app/api/v1/events.py (added delivery_carrier to event_dict in list_events and get_event)
- backend/tests/test_api/test_events.py (added 8 delivery carrier API tests)

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2025-12-18 | Initial draft | SM Agent (YOLO workflow) |
| 2025-12-18 | Implementation complete - all ACs satisfied, 82 tests passing | Dev Agent (Claude Opus 4.5) |
