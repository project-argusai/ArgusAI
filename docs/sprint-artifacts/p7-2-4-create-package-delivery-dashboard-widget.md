# Story P7-2.4: Create Package Delivery Dashboard Widget

## Story
**As a** homeowner,
**I want** a dashboard widget showing today's package deliveries,
**So that** I can quickly see all deliveries at a glance without navigating to the events page.

## Story Key
p7-2-4-create-package-delivery-dashboard-widget

## Status
DONE

## Dev Agent Record
### Context Reference
- docs/sprint-artifacts/p7-2-4-create-package-delivery-dashboard-widget.context.xml

### Implementation Summary
Implemented package delivery dashboard widget with:
- Backend: GET /api/v1/events/packages/today endpoint with carrier aggregation
- Frontend: PackageDeliveryWidget component with carrier badges, recent events, loading/error/empty states
- Tests: 3 API tests for package delivery endpoint
- Auto-refresh: 60-second interval using TanStack Query

## Epic
P7-2: Package Delivery Detection & Alerting

## Background
The previous stories in Epic P7-2 have implemented:
- P7-2.1: AI carrier detection (delivery_carrier field in Event model)
- P7-2.2: Package Delivery alert rule type
- P7-2.3: HomeKit sensors for package deliveries and carriers

This story adds a visual dashboard component that surfaces package delivery events prominently, providing users with quick visibility into recent package deliveries and carrier distribution.

## Acceptance Criteria

### AC1: Dashboard Widget Component
- [x] Create `PackageDeliveryWidget.tsx` component in `frontend/components/dashboard/`
- [x] Widget displays a summary card with total package count for today
- [x] Widget shows breakdown of packages by carrier (FedEx, UPS, USPS, Amazon, DHL, Unknown)
- [x] Each carrier entry shows carrier icon/badge and count

### AC2: Recent Deliveries List
- [x] Widget shows recent 5 package delivery events with timestamps
- [x] Each entry shows carrier badge, time (relative format like "2h ago"), and camera name
- [x] Clicking an entry navigates to the event detail page

### AC3: Empty State
- [x] When no deliveries today, show friendly empty state message
- [x] Empty state includes an icon and text: "No package deliveries detected today"

### AC4: Loading and Error States
- [x] Show skeleton loader while fetching data
- [x] Handle API errors gracefully with error message display
- [x] Auto-refresh every 60 seconds to catch new deliveries

### AC5: Integration with Dashboard
- [x] Add widget to main dashboard page (`frontend/app/page.tsx`)
- [x] Widget placed prominently in dashboard grid layout
- [x] Responsive design for mobile and desktop

### AC6: Backend API Endpoint
- [x] Create `GET /api/v1/events/packages/today` endpoint
- [x] Returns package events from today with carrier breakdown
- [x] Response includes: total_count, by_carrier (dict), recent_events (list)
- [x] Filter by smart_detection_type='package' OR objects_detected contains 'package'

### AC7: Frontend API Integration
- [x] Add `getPackageDeliveriesToday()` method to api-client.ts
- [x] Define TypeScript interface for package delivery summary response
- [x] Use TanStack Query for data fetching with 60-second refetch interval

## Technical Notes

### Carrier Display Mapping
Use existing CARRIER_DISPLAY_NAMES from backend schema:
- fedex → FedEx (blue badge)
- ups → UPS (brown badge)
- usps → USPS (red/white/blue badge)
- amazon → Amazon (orange badge)
- dhl → DHL (yellow badge)
- null/unknown → Unknown (gray badge)

### API Response Schema
```typescript
interface PackageDeliveriesTodayResponse {
  total_count: number;
  by_carrier: Record<string, number>;  // {"fedex": 2, "ups": 1, ...}
  recent_events: Array<{
    id: string;
    timestamp: string;
    delivery_carrier: string | null;
    delivery_carrier_display: string;
    camera_name: string;
    thumbnail_path: string | null;
  }>;
}
```

### Existing Infrastructure
- Event model has `delivery_carrier` field (Story P7-2.1)
- EventResponse schema has `delivery_carrier_display` computed field
- Dashboard uses `SummaryCard` pattern for stats display

## Tasks

### Backend Tasks
1. [x] Create `/api/v1/events/packages/today` endpoint in events.py
2. [x] Add query filtering for package events with carrier aggregation
3. [x] Return structured response with counts and recent events

### Frontend Tasks
4. [x] Create PackageDeliveryWidget component
5. [x] Add carrier badge component with color coding
6. [x] Create TypeScript interfaces for API response
7. [x] Add `getPackageDeliveriesToday()` to api-client.ts
8. [x] Integrate widget into dashboard page
9. [x] Implement loading/error/empty states
10. [x] Add auto-refresh with 60-second interval

## Dependencies
- Story P7-2.1 (carrier detection) - DONE
- Story P7-2.2 (alert rules) - DONE
- Story P7-2.3 (HomeKit sensors) - DONE

## Definition of Done
- [x] All acceptance criteria verified
- [x] Component renders correctly in dashboard
- [x] API endpoint returns accurate package counts
- [x] Loading, error, and empty states work correctly
- [x] Auto-refresh updates data every 60 seconds
- [x] Code follows existing patterns (SummaryCard, TanStack Query)
- [x] No TypeScript errors
- [x] Responsive design verified on mobile/desktop
