# Story P7-2.2: Create Package Delivery Alert Rule Type

Status: done

## Story

As a **homeowner using ArgusAI**,
I want **a dedicated "Package Delivery" alert rule type that can filter by carrier**,
so that **I receive targeted notifications when packages from specific carriers are delivered**.

## Acceptance Criteria

1. "Package Delivery" added to alert rule types (new `rule_type` field in conditions)
2. Support filtering by carrier (any, specific carrier, multiple carriers via `carriers` array)
3. Rule triggers when package detected (smart_detection_type='package') AND carrier identified (delivery_carrier is set)
4. Carrier name included in alert message (notification and webhook payload)
5. All notification channels supported (push notification via existing push service, webhook, MQTT)

## Tasks / Subtasks

- [x] Task 1: Add Package Delivery Rule Type to Backend Schema (AC: 1)
  - [x] 1.1 Add `rule_type` field to `AlertRuleConditions` schema with enum values: `any`, `package_delivery`
  - [x] 1.2 Add `carriers` field to conditions schema (Optional[List[str]])
  - [x] 1.3 Update backend `AlertRuleCreate`/`AlertRuleUpdate` schemas with new fields
  - [x] 1.4 Write schema validation tests

- [x] Task 2: Implement Package Delivery Rule Evaluation in Alert Engine (AC: 2, 3)
  - [x] 2.1 Add `_check_rule_type()` method to `AlertEngine` class
  - [x] 2.2 Implement package delivery check: smart_detection_type='package' AND delivery_carrier is set
  - [x] 2.3 Add `_check_carriers()` method for carrier filtering
  - [x] 2.4 Integrate new checks into `evaluate_rule()` method
  - [x] 2.5 Write unit tests for package delivery rule evaluation (various carrier combos)

- [x] Task 3: Include Carrier in Alert Messages (AC: 4)
  - [x] 3.1 Update `_execute_dashboard_notification()` to include carrier in message
  - [x] 3.2 Update webhook payload builder to include `delivery_carrier` field
  - [x] 3.3 Format notification message: "Package delivered by {carrier} at {camera}"
  - [x] 3.4 Write tests verifying carrier appears in notifications

- [x] Task 4: Update Frontend Alert Rule Types (AC: 1)
  - [x] 4.1 Add `rule_type` and `carriers` to `IAlertRuleConditions` TypeScript type
  - [x] 4.2 Add `RULE_TYPES` constant with 'any' and 'package_delivery' options
  - [x] 4.3 Add `CARRIERS` constant with fedex, ups, usps, amazon, dhl options

- [x] Task 5: Create Carrier Selector UI Component (AC: 2)
  - [x] 5.1 Create `CarrierSelector.tsx` component in `components/rules/`
  - [x] 5.2 Display carrier checkboxes with brand names (FedEx, UPS, USPS, Amazon, DHL)
  - [x] 5.3 Only show when rule_type is 'package_delivery'
  - [x] 5.4 Integrate into `RuleFormDialog.tsx`

- [x] Task 6: Add Rule Type Selector to Rule Form (AC: 1)
  - [x] 6.1 Create `RuleTypeSelector.tsx` component with radio/toggle options
  - [x] 6.2 Options: "Any Detection" (default) and "Package Delivery"
  - [x] 6.3 Add to top of conditions section in `RuleFormDialog.tsx`
  - [x] 6.4 Conditionally show ObjectTypeSelector (hidden for package_delivery)
  - [x] 6.5 Conditionally show CarrierSelector (shown only for package_delivery)

- [x] Task 7: Integration Testing (AC: 5)
  - [x] 7.1 Test package delivery rule triggers push notification with carrier
  - [x] 7.2 Test package delivery rule triggers webhook with carrier in payload
  - [x] 7.3 Test package delivery rule triggers MQTT with carrier in topic/payload
  - [x] 7.4 Test rule doesn't trigger for packages without carrier detection

## Dev Notes

### Architecture Constraints

- Alert rules use JSON `conditions` field for flexible condition storage [Source: backend/app/models/alert_rule.py:42-50]
- Rule evaluation uses AND logic between conditions [Source: backend/app/services/alert_engine.py:14]
- Carrier extraction from AI descriptions was implemented in P7-2.1 [Source: docs/sprint-artifacts/p7-2-1-add-carrier-detection-to-ai-analysis.md]
- Performance: carrier filtering must complete in <10ms (simple list membership check)

### Existing Components to Modify

**Backend:**
- `backend/app/schemas/alert_rule.py` - Add rule_type, carriers to conditions schema
- `backend/app/services/alert_engine.py` - Add package delivery rule evaluation
- `backend/app/services/push_notification_service.py` - Include carrier in message (if exists)
- `backend/app/services/mqtt_service.py` - Include carrier in payload (if exists)

**Frontend:**
- `frontend/types/alert-rule.ts` - Add rule_type, carriers to IAlertRuleConditions
- `frontend/components/rules/RuleFormDialog.tsx` - Add rule type and carrier selection
- `frontend/components/rules/ObjectTypeSelector.tsx` - Hide when rule_type='package_delivery'

### New Components to Create

- `frontend/components/rules/RuleTypeSelector.tsx` - Rule type toggle component
- `frontend/components/rules/CarrierSelector.tsx` - Carrier checkbox component

### Rule Type Design

From tech spec [Source: docs/sprint-artifacts/tech-spec-epic-P7-2.md#Data-Models]:

```python
class AlertRuleConditions(BaseModel):
    rule_type: str = "any"  # 'any' or 'package_delivery'
    carriers: Optional[List[str]] = None  # For package_delivery: ['fedex', 'ups', 'amazon']
    # ... existing fields
```

### Carrier Values

From carrier extractor [Source: backend/app/services/carrier_extractor.py]:
- `fedex` → "FedEx"
- `ups` → "UPS"
- `usps` → "USPS"
- `amazon` → "Amazon"
- `dhl` → "DHL"

### Alert Message Format

For package delivery alerts:
- Dashboard notification: "Package delivered by {carrier_display} at {camera_name}"
- Webhook payload: includes `delivery_carrier` and `delivery_carrier_display` fields
- MQTT topic: `argusai/events/package_delivery` (or existing topic with carrier in payload)

### Testing Standards

- Backend: pytest with fixtures in `backend/tests/`
- Frontend: Vitest + React Testing Library
- Use existing test patterns from alert engine tests
- Mock Event objects with delivery_carrier field for testing

### Project Structure Notes

- Services in `backend/app/services/`
- Schemas in `backend/app/schemas/`
- Frontend components in `frontend/components/rules/`
- Types in `frontend/types/`

### Learnings from Previous Story

**From Story p7-2-1-add-carrier-detection-to-ai-analysis (Status: done)**

- **Carrier Extractor Service**: Created at `backend/app/services/carrier_extractor.py` with `extract_carrier()` function - reuse CARRIER_DISPLAY_NAMES mapping
- **Event Model Change**: Added `delivery_carrier` field to Event model - use this field for rule matching
- **Schema Pattern**: Added `delivery_carrier` and `delivery_carrier_display` to EventResponse - follow same pattern for alert payloads
- **Pattern Matching**: Used compiled regex patterns - carrier filter should use simple `in` list check for performance

[Source: docs/sprint-artifacts/p7-2-1-add-carrier-detection-to-ai-analysis.md#Dev-Agent-Record]

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P7-2.md] - Epic technical specification
- [Source: docs/epics-phase7.md#Story-P7-2.2] - Epic acceptance criteria
- [Source: docs/sprint-artifacts/p7-2-1-add-carrier-detection-to-ai-analysis.md] - Previous story (carrier extraction)
- [Source: backend/app/services/alert_engine.py] - Alert rule engine
- [Source: backend/app/schemas/alert_rule.py] - Alert rule schemas
- [Source: frontend/components/rules/RuleFormDialog.tsx] - Rule form dialog
- [Source: frontend/types/alert-rule.ts] - Alert rule TypeScript types

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p7-2-2-create-package-delivery-alert-rule-type.context.xml

### Agent Model Used

Claude Opus 4.5

### Debug Log References

- All 20 package delivery tests passed
- Frontend lint passed with pre-existing warnings only
- Existing alert engine tests (13) continue to pass

### Completion Notes List

1. Added `rule_type` (enum: any, package_delivery) and `carriers` (list of valid carriers) to AlertRuleConditions schema
2. Implemented `_check_rule_type()` and `_check_delivery_carriers()` methods in AlertEngine
3. Updated webhook, push notification, and MQTT services to include carrier in payloads
4. Added TypeScript types, RULE_TYPES, and CARRIERS constants to frontend
5. Created RuleTypeSelector and CarrierSelector components
6. Updated RuleFormDialog with conditional rendering based on rule type
7. Created comprehensive test suite with 20 tests covering all acceptance criteria

### File List

**Backend (Modified):**
- backend/app/schemas/alert_rule.py - Added rule_type and carriers fields with validators
- backend/app/services/alert_engine.py - Added package delivery rule evaluation
- backend/app/services/webhook_service.py - Added carrier to webhook payload
- backend/app/services/push_notification_service.py - Added carrier to push notifications
- backend/app/services/mqtt_service.py - Added carrier to MQTT payload

**Backend (Created):**
- backend/tests/test_services/test_alert_engine_package_delivery.py - 20 tests for package delivery rules

**Frontend (Modified):**
- frontend/types/alert-rule.ts - Added rule_type, carriers, RULE_TYPES, CARRIERS
- frontend/components/rules/RuleFormDialog.tsx - Integrated new selectors

**Frontend (Created):**
- frontend/components/rules/RuleTypeSelector.tsx - Rule type radio selector
- frontend/components/rules/CarrierSelector.tsx - Carrier checkbox selector

**Documentation (Modified):**
- docs/sprint-artifacts/p7-2-2-create-package-delivery-alert-rule-type.md - Story file

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2025-12-19 | Initial draft | SM Agent (YOLO workflow) |
| 2025-12-19 | Implementation complete - all 7 tasks done | Dev Agent (Claude Opus 4.5) |
