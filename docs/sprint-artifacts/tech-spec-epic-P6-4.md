# Epic Technical Specification: Data Export Enhancements

Date: 2025-12-16
Author: Brent
Epic ID: P6-4
Status: Draft

---

## Overview

Epic P6-4 adds comprehensive data export functionality for motion events (backlog item FF-017). This enables users to export raw motion detection data to CSV format for external analysis, compliance reporting, or integration with third-party analytics tools.

The export feature provides filtering by date range and camera, uses streaming responses to handle large datasets efficiently, and includes a user-friendly UI for configuring and triggering exports.

## Objectives and Scope

### In Scope
- **Story P6-4.1**: Create CSV export API endpoint for motion events
- **Story P6-4.2**: Build frontend UI for triggering motion events export

### Out of Scope
- JSON export format (CSV only for MVP)
- Scheduled/automated exports (manual trigger only)
- Export of AI-analyzed Events (separate from MotionEvents)
- Export to cloud storage (local download only)
- Export of thumbnails/images (data only)

## System Architecture Alignment

### Components Referenced
- **Backend**: `backend/app/api/v1/events.py` - New export endpoint (or new router)
- **Backend**: `backend/app/models/motion_event.py` - Query for export data
- **Frontend**: `frontend/components/settings/MotionExport.tsx` - New component
- **Frontend**: `frontend/app/settings/page.tsx` - Integrate export UI

### Architecture Constraints
- Must use streaming response for large datasets (>10,000 rows)
- Export must not block other API requests
- Must handle timezone correctly (UTC storage, user timezone display)
- CSV must be valid and parseable by Excel/Google Sheets

## Detailed Design

### Services and Modules

| Module | Responsibility | Inputs | Outputs |
|--------|---------------|--------|---------|
| `events.py` or `export.py` | Handle export API request | Query params | StreamingResponse (CSV) |
| `export_service.py` | Generate CSV from database | Filters, format | CSV generator |
| `MotionExport.tsx` | UI for export configuration | User input | API call trigger |

### Data Models and Contracts

**MotionEvent Model (Existing):**
```python
class MotionEvent(Base):
    id: str
    camera_id: str
    timestamp: datetime
    confidence: float
    algorithm: str  # MOG2, KNN, frame_diff
    bounding_box: dict  # {x, y, width, height}
    zone_id: Optional[str]
    created_at: datetime
```

**Export Query Parameters:**
```python
class MotionExportParams(BaseModel):
    format: Literal["csv"] = "csv"
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    camera_id: Optional[str] = None
    timezone: str = "UTC"  # For timestamp formatting
```

**CSV Output Schema:**
| Column | Type | Description |
|--------|------|-------------|
| timestamp | ISO8601 | Event timestamp in requested timezone |
| camera_id | UUID | Camera identifier |
| camera_name | String | Human-readable camera name |
| confidence | Float | Detection confidence (0-100) |
| algorithm | String | MOG2, KNN, or frame_diff |
| x | Int | Bounding box X coordinate |
| y | Int | Bounding box Y coordinate |
| width | Int | Bounding box width |
| height | Int | Bounding box height |
| zone_id | String | Detection zone ID (nullable) |

### APIs and Interfaces

**New Endpoint: GET /api/v1/motion-events/export**

| Attribute | Value |
|-----------|-------|
| Method | GET |
| Path | `/api/v1/motion-events/export` |
| Auth | Required |
| Query Params | format, start_date, end_date, camera_id, timezone |
| Response | StreamingResponse (text/csv) |
| Headers | Content-Disposition: attachment; filename="motion-events-{start}-{end}.csv" |

**Request Example:**
```
GET /api/v1/motion-events/export?format=csv&start_date=2025-12-01&end_date=2025-12-16&camera_id=abc123&timezone=America/Los_Angeles
```

**Response Headers:**
```
Content-Type: text/csv; charset=utf-8
Content-Disposition: attachment; filename="motion-events-2025-12-01-2025-12-16.csv"
Transfer-Encoding: chunked
```

**Response Body (CSV):**
```csv
timestamp,camera_id,camera_name,confidence,algorithm,x,y,width,height,zone_id
2025-12-15T10:30:00-08:00,abc123,Front Door,85.5,MOG2,100,200,50,80,zone-1
2025-12-15T10:31:00-08:00,abc123,Front Door,72.3,MOG2,150,180,40,60,
```

### Workflows and Sequencing

**Export API Flow:**
```
GET /motion-events/export?params →
  Validate params →
  Build database query with filters →
  Create CSV generator (yield rows) →
  Return StreamingResponse →
    Database cursor iterates →
    Each row formatted to CSV →
    Streamed to client →
  Client saves file
```

**Export UI Flow:**
```
User navigates to Settings → Data Export section →
  User selects date range (DateRangePicker) →
  User optionally selects camera (CameraSelect) →
  User clicks "Export CSV" →
  Loading spinner shown →
    Frontend calls export endpoint →
    Browser handles file download →
  Success toast shown
```

## Non-Functional Requirements

### Performance

| Metric | Target | Measurement |
|--------|--------|-------------|
| Export 10,000 rows | < 5 seconds | End-to-end response time |
| Export 100,000 rows | < 30 seconds | End-to-end response time |
| Memory usage | < 50MB | Streaming prevents full load |
| Concurrent exports | 3 max | Rate limit per user |

### Security

| Requirement | Implementation |
|-------------|----------------|
| Authentication | Required - uses existing session/token |
| Authorization | User can only export their cameras |
| Data privacy | Export contains no credentials or PII |
| Rate limiting | Max 3 concurrent exports per user |

### Reliability/Availability

| Scenario | Behavior |
|----------|----------|
| No motion events in range | Return CSV with headers only |
| Invalid date range | Return 400 with validation error |
| Database timeout | Return 504 after 60 seconds |
| Client disconnects mid-stream | Stop generation gracefully |

### Observability

| Signal | Implementation |
|--------|----------------|
| Export requests | INFO log: user_id, date_range, camera_id, row_count |
| Export completion | INFO log: user_id, duration_ms, bytes_sent |
| Export errors | ERROR log: user_id, error message |

**Prometheus Metrics:**
- `motion_export_requests_total{status}`
- `motion_export_rows_total`
- `motion_export_duration_seconds` (histogram)

## Dependencies and Integrations

### Backend Dependencies (Existing)
| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | 0.115+ | StreamingResponse |
| sqlalchemy | 2.0+ | Database queries |
| csv (stdlib) | - | CSV formatting |

### Frontend Dependencies (Existing)
| Package | Version | Purpose |
|---------|---------|---------|
| react | 19.x | UI framework |
| date-fns | latest | Date formatting |
| shadcn/ui | latest | DateRangePicker, Select |

### Integration Points
| Integration | Type | Notes |
|-------------|------|-------|
| MotionEvent table | Internal | Query source for export |
| Camera table | Internal | Join for camera_name |
| Existing events export | Internal | Similar pattern (Events already have export) |

## Acceptance Criteria (Authoritative)

### Story P6-4.1: Motion Events CSV Export API
| AC# | Criterion |
|-----|-----------|
| AC1 | GET `/api/v1/motion-events/export?format=csv` endpoint created |
| AC2 | CSV includes columns: timestamp, camera_id, camera_name, confidence, algorithm, x, y, width, height, zone_id |
| AC3 | Date range filtering works (start_date, end_date query params) |
| AC4 | Camera filtering works (camera_id query param) |
| AC5 | Streaming response used for large datasets |
| AC6 | Filename includes date range in Content-Disposition header |
| AC7 | Empty result returns CSV with headers only |

### Story P6-4.2: Motion Events Export UI
| AC# | Criterion |
|-----|-----------|
| AC8 | Export button/section in Settings page |
| AC9 | Date range picker for filtering (start and end date) |
| AC10 | Camera selector dropdown for filtering (optional, "All Cameras" default) |
| AC11 | Click triggers file download |
| AC12 | Loading state shown during export |
| AC13 | Success toast shown after download completes |
| AC14 | Error toast shown if export fails |

## Traceability Mapping

| AC | Spec Section | Component/API | Test Approach |
|----|--------------|---------------|---------------|
| AC1 | APIs | `GET /motion-events/export` | Integration test: call endpoint |
| AC2 | Data Models | CSV output | Unit test: verify columns |
| AC3-AC4 | APIs | Query params | Integration test: filter verification |
| AC5 | NFR | StreamingResponse | Load test: 100k rows |
| AC6 | APIs | Content-Disposition | Integration test: verify header |
| AC7 | Reliability | Empty result | Integration test: empty date range |
| AC8-AC14 | Workflows | `MotionExport.tsx` | E2E test: Playwright |

## Risks, Assumptions, Open Questions

### Risks
| Risk | Impact | Mitigation |
|------|--------|------------|
| **R1**: Large exports may timeout | Medium | Use streaming; add progress indicator |
| **R2**: CSV may have encoding issues | Low | Use UTF-8 BOM for Excel compatibility |
| **R3**: Concurrent exports may overload DB | Medium | Rate limit to 3 concurrent per user |

### Assumptions
| Assumption | Validation |
|------------|------------|
| **A1**: MotionEvent table has bounding_box data | Verify schema; FF-017 implies it exists |
| **A2**: Users want CSV for Excel/Sheets | CSV is universal; JSON export deferred |
| **A3**: Streaming is sufficient for 100k+ rows | Test with realistic data volumes |

### Open Questions
| Question | Owner | Status |
|----------|-------|--------|
| **Q1**: Where to place Export UI? Settings vs dedicated page? | PM | Recommend: Settings > Data Export section |
| **Q2**: Should we add JSON export alongside CSV? | Dev Team | Deferred to future iteration |
| **Q3**: Should export include derived fields (e.g., time of day)? | PM | Recommend: No, keep raw data |

## Test Strategy Summary

### Test Levels

| Level | Framework | Coverage |
|-------|-----------|----------|
| Unit | pytest | CSV generation, date filtering |
| Integration | pytest + TestClient | Full export endpoint |
| Load | locust or k6 | 100k row export performance |
| E2E | Playwright | Export UI flow |

### Test Cases by Story

**P6-4.1 (Export API)**
- Export with no filters returns all motion events
- Export with date range filters correctly
- Export with camera_id filters correctly
- Export with combined filters works
- Empty result returns headers-only CSV
- CSV is valid and parseable
- Streaming works for large datasets (10k+ rows)
- Filename includes date range
- Timezone parameter affects timestamp format

**P6-4.2 (Export UI)**
- Export button visible in Settings
- Date range picker works
- Camera selector shows all cameras + "All" option
- Click triggers download
- Loading spinner during export
- Success toast on completion
- Error toast on failure
- Disabled state while loading

### Coverage Targets
- Backend: > 80% line coverage for export endpoint
- Frontend: > 70% coverage for MotionExport component
- Load test: Export 100k rows in < 30 seconds
