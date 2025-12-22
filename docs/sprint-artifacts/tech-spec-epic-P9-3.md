# Epic Technical Specification: AI Context & Accuracy

Date: 2025-12-22
Author: Brent
Epic ID: P9-3
Status: Draft

---

## Overview

Epic P9-3 enhances AI description accuracy by providing contextual information (camera name, time of day) in prompts and implementing feedback mechanisms for continuous improvement. This epic addresses the need for more relevant, context-aware descriptions and creates feedback loops that help the system learn from user corrections.

Key improvements include injecting camera and temporal context into AI prompts, attempting to extract metadata from video frame overlays, implementing package-specific false positive feedback, adding thumbs up/down to daily summaries, customizable summary prompts, and including summary accuracy in statistics.

## Objectives and Scope

**In Scope:**
- Add camera name and time of day to AI prompts (IMP-012)
- Attempt OCR extraction of timestamp/camera name from frame overlays (IMP-012)
- Implement package delivery false positive feedback (IMP-013)
- Add thumbs up/down feedback buttons to summaries (IMP-014)
- Add customizable summary prompt in Settings (IMP-014)
- Include summary feedback in AI Accuracy statistics (IMP-014)
- Complete AI-assisted prompt refinement functionality (FF-023)

**Out of Scope:**
- Local MCP server implementation (IMP-016) - separate epic
- Embedding-based similarity for feedback (future)
- Automated prompt adjustment based on feedback (future)
- Multi-language summary support

## System Architecture Alignment

This epic extends the AI service and feedback systems:

| Component | Files Affected | Changes |
|-----------|---------------|---------|
| AI Service | `backend/app/services/ai_service.py` | Add context to prompts |
| Prompt Builder | `backend/app/services/prompt_builder.py` | New service for context injection |
| OCR Service | `backend/app/services/ocr_service.py` | New service for overlay extraction |
| Feedback Model | `backend/app/models/feedback.py` | Add summary feedback, correction types |
| Summary Service | `backend/app/services/summary_service.py` | Add feedback integration |
| Settings Model | `backend/app/models/settings.py` | Add summary prompt setting |
| Feedback API | `backend/app/api/v1/feedback.py` | Add summary feedback endpoint |
| AI Accuracy UI | `frontend/components/settings/AIAccuracySettings.tsx` | Add summary stats |
| Summary Card | `frontend/components/dashboard/SummaryCard.tsx` | Add feedback buttons |
| Settings UI | `frontend/components/settings/AIModelSettings.tsx` | Add summary prompt |

### Context Flow Diagram

```
Event Processing:
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│   Event     │───>│ Context      │───>│  AI Prompt  │
│   Data      │    │ Builder      │    │  + Context  │
└─────────────┘    └──────────────┘    └─────────────┘
       │                  │
       │           ┌──────┴──────┐
       │           │             │
       ▼           ▼             ▼
  Camera Name   Time/Date    OCR Extract
  (from DB)     (from event) (from frame)

Feedback Loop:
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│   User      │───>│  Feedback    │───>│  Prompt     │
│   Feedback  │    │  Storage     │    │  Refinement │
└─────────────┘    └──────────────┘    └─────────────┘
```

---

## Detailed Design

### Services and Modules

| Service/Module | Responsibility | Inputs | Outputs |
|---------------|----------------|--------|---------|
| PromptBuilder | Construct AI prompts with context | Event, camera, settings | Formatted prompt |
| OCRService | Extract text from frame overlays | Frame image | Extracted text/metadata |
| FeedbackService | Store and retrieve feedback | User actions | Feedback records |
| SummaryService | Generate summaries with custom prompts | Events, prompt | Summary text |
| AIAccuracyService | Calculate accuracy statistics | Feedback data | Accuracy metrics |

### Data Models and Contracts

**Extended Feedback Model:**
```python
class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID, ForeignKey("events.id"), nullable=True)
    summary_id = Column(UUID, ForeignKey("summaries.id"), nullable=True)  # NEW
    rating = Column(String, nullable=False)  # "positive", "negative"
    correction_type = Column(String, nullable=True)  # NEW: "not_package", "wrong_person", etc.
    correction_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    event = relationship("Event", back_populates="feedback")
    summary = relationship("Summary", back_populates="feedback")  # NEW
```

**Extended Summary Model:**
```python
class Summary(Base):
    __tablename__ = "summaries"

    # Existing fields...

    # NEW: Feedback relationship
    feedback = relationship("Feedback", back_populates="summary", cascade="all, delete-orphan")
```

**New Settings Keys:**
```python
PROMPT_SETTINGS = {
    # Existing
    "event_description_prompt": "Describe what you see...",

    # NEW
    "summary_prompt": """Generate a daily activity summary for {date}.
Summarize the {event_count} events detected across {camera_count} cameras.
Highlight any notable patterns or unusual activity.
Keep the summary concise (2-3 paragraphs).""",

    "include_camera_context": True,
    "include_time_context": True,
    "attempt_ocr_extraction": False,  # Opt-in due to CPU cost
}
```

**Context Data Structure:**
```python
@dataclass
class EventContext:
    camera_name: str
    camera_location: Optional[str]
    event_time: datetime
    time_of_day: str  # "morning", "afternoon", "evening", "night"
    date_formatted: str  # "December 22, 2025"
    ocr_timestamp: Optional[str]  # From frame overlay
    ocr_camera_name: Optional[str]  # From frame overlay
```

### APIs and Interfaces

**Feedback Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/feedback` | Submit event feedback (existing) |
| POST | `/api/v1/summaries/{id}/feedback` | Submit summary feedback (NEW) |
| GET | `/api/v1/feedback/stats` | Get feedback statistics (modified) |

**Summary Feedback Request:**
```json
{
  "rating": "negative",
  "correction_text": "Summary missed the package delivery"
}
```

**Feedback Stats Response (extended):**
```json
{
  "event_feedback": {
    "total": 150,
    "positive": 120,
    "negative": 30,
    "accuracy_percent": 80.0
  },
  "summary_feedback": {
    "total": 25,
    "positive": 20,
    "negative": 5,
    "accuracy_percent": 80.0
  },
  "correction_types": {
    "not_package": 8,
    "wrong_person": 3,
    "missed_event": 5
  }
}
```

**Settings Endpoints (extended):**

| Method | Path | Changes |
|--------|------|---------|
| GET | `/api/v1/system/settings` | Include summary_prompt |
| PUT | `/api/v1/system/settings` | Accept summary_prompt |

### Workflows and Sequencing

**Context-Enhanced AI Analysis:**

```
1. Event Received
   ├── Get camera info from database
   └── Get event timestamp

2. Build Context
   ├── Format camera name
   ├── Calculate time of day
   │   ├── 5am-12pm: "morning"
   │   ├── 12pm-5pm: "afternoon"
   │   ├── 5pm-9pm: "evening"
   │   └── 9pm-5am: "night"
   ├── Format date
   └── If OCR enabled:
       ├── Extract first frame
       ├── Run OCR on corners
       └── Parse timestamp/camera patterns

3. Construct Prompt
   ├── Base prompt from settings
   ├── Inject context:
   │   "This footage is from the {camera_name} camera.
   │    Captured at {time} on {date} ({time_of_day})."
   └── Add any OCR-extracted context

4. Send to AI
   └── Process response as normal
```

**Package False Positive Flow:**

```
1. User views package event
2. User clicks "Not a package" button
3. Frontend sends:
   POST /api/v1/feedback
   {
     "event_id": "...",
     "rating": "negative",
     "correction_type": "not_package"
   }
4. Backend stores feedback
5. Feedback available for prompt refinement
```

**Summary Feedback Flow:**

```
1. User views daily summary
2. User clicks thumbs up/down
3. If thumbs down, optional correction text modal
4. Frontend sends:
   POST /api/v1/summaries/{id}/feedback
   {
     "rating": "negative",
     "correction_text": "Missed the morning delivery"
   }
5. Backend stores feedback
6. Stats updated in AI Accuracy page
```

**OCR Extraction Algorithm:**

```python
def extract_overlay_text(frame: np.ndarray) -> Optional[dict]:
    """Extract timestamp/camera from frame overlay."""
    # Target regions (typical overlay positions)
    regions = [
        ("top_left", frame[0:50, 0:300]),
        ("top_right", frame[0:50, -300:]),
        ("bottom_left", frame[-50:, 0:300]),
        ("bottom_right", frame[-50:, -300:]),
    ]

    for region_name, region in regions:
        # Preprocess for OCR
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)

        # Run OCR
        text = pytesseract.image_to_string(thresh)

        # Parse for patterns
        timestamp = parse_timestamp(text)
        camera_name = parse_camera_name(text)

        if timestamp or camera_name:
            return {
                "region": region_name,
                "timestamp": timestamp,
                "camera_name": camera_name,
                "raw_text": text
            }

    return None

def parse_timestamp(text: str) -> Optional[str]:
    """Extract timestamp from OCR text."""
    patterns = [
        r'\d{2}[/:]\d{2}[/:]\d{2}',  # HH:MM:SS or HH/MM/SS
        r'\d{4}[/-]\d{2}[/-]\d{2}',  # YYYY-MM-DD
        r'\d{2}[/-]\d{2}[/-]\d{4}',  # MM-DD-YYYY
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group()
    return None
```

---

## Non-Functional Requirements

### Performance

| Metric | Target | Measurement |
|--------|--------|-------------|
| Context building | <50ms | Time to construct context |
| OCR extraction | <500ms per frame | Optional, CPU-intensive |
| Feedback submission | <200ms | API response time |
| Stats calculation | <500ms | Dashboard load time |

### Storage

| Item | Size | Notes |
|------|------|-------|
| Feedback record | ~500 bytes | Minimal storage |
| Summary feedback | ~500 bytes | Same as event feedback |
| No new large assets | - | Text only |

### Reliability

- Context building must not block event processing on failure
- OCR failure should fall back to database metadata gracefully
- Feedback storage failure should not affect user experience
- Summary generation should work with or without custom prompt

### Observability

- Log context injection details for debugging
- Log OCR attempts and success/failure rate
- Track feedback submission rates
- Monitor prompt refinement usage

---

## Dependencies and Integrations

### Backend Dependencies

```
# NEW dependency for OCR
pytesseract>=0.3.10  # Python wrapper for Tesseract OCR

# System dependency (must be installed separately)
# tesseract-ocr  # apt-get install tesseract-ocr
```

### Frontend Dependencies

```json
{
  "dependencies": {
    // No new dependencies - using existing shadcn/ui components
  }
}
```

### Internal Dependencies

| Dependency | Version | Purpose |
|------------|---------|---------|
| AIService | P3 | Send prompts to AI |
| FeedbackService | P4 | Store feedback |
| SummaryService | P4 | Generate summaries |
| SettingsService | P1 | Store prompts |

---

## Acceptance Criteria (Authoritative)

### P9-3.1: Add Camera and Time Context to AI Prompt

**AC-3.1.1:** Given event from "Front Door" camera, when AI analyzes, then prompt includes "from the Front Door camera"
**AC-3.1.2:** Given event at 7:15 AM, when AI analyzes, then prompt includes time and "morning"
**AC-3.1.3:** Given event on Dec 22, 2025, when AI analyzes, then prompt includes formatted date
**AC-3.1.4:** Given context enabled in settings, when event processed, then context injected
**AC-3.1.5:** Given context disabled in settings, when event processed, then no context injected
**AC-3.1.6:** Given AI description, when reading, then context may be naturally incorporated

### P9-3.2: Attempt Frame Overlay Text Extraction

**AC-3.2.1:** Given OCR enabled in settings, when frame has visible timestamp, then timestamp extracted
**AC-3.2.2:** Given OCR enabled, when frame has camera name overlay, then name extracted
**AC-3.2.3:** Given OCR extraction succeeds, when building context, then OCR data supplements DB data
**AC-3.2.4:** Given OCR extraction fails, when building context, then fallback to DB metadata only
**AC-3.2.5:** Given OCR disabled in settings, when processing event, then OCR not attempted
**AC-3.2.6:** Given tesseract not installed, when OCR attempted, then graceful error with warning

### P9-3.3: Implement Package False Positive Feedback

**AC-3.3.1:** Given event with smart_detection_type="package", when viewing card, then "Not a package" button visible
**AC-3.3.2:** Given non-package event, when viewing card, then "Not a package" button not visible
**AC-3.3.3:** Given I click "Not a package", when submitted, then feedback stored with correction_type="not_package"
**AC-3.3.4:** Given I click "Not a package", when submitted, then toast confirms "Feedback recorded"
**AC-3.3.5:** Given I click "Not a package", when viewing button again, then shows "Marked as not a package"
**AC-3.3.6:** Given multiple "not_package" feedbacks exist, when prompt refinement runs, then examples included

### P9-3.4: Add Summary Feedback Buttons

**AC-3.4.1:** Given daily summary card, when viewing, then thumbs up/down buttons visible
**AC-3.4.2:** Given I click thumbs up, when submitted, then positive feedback stored
**AC-3.4.3:** Given I click thumbs up, when viewing, then button shows selected state
**AC-3.4.4:** Given I click thumbs down, when clicked, then optional correction text modal appears
**AC-3.4.5:** Given I submit thumbs down with text, when stored, then correction_text saved
**AC-3.4.6:** Given I submit feedback, when complete, then brief toast "Thanks for the feedback!"

### P9-3.5: Add Summary Prompt Customization

**AC-3.5.1:** Given Settings > AI Models, when viewing, then "Summary Prompt" textarea visible
**AC-3.5.2:** Given summary prompt field, when viewing, then default prompt pre-filled
**AC-3.5.3:** Given I edit summary prompt, when I save, then new prompt persisted
**AC-3.5.4:** Given custom prompt saved, when summary generated, then custom prompt used
**AC-3.5.5:** Given I click "Reset to Default", when confirmed, then prompt reverts to default
**AC-3.5.6:** Given prompt with variables, when summary generates, then {date}, {event_count}, {camera_count} replaced

### P9-3.6: Include Summary Feedback in AI Accuracy Stats

**AC-3.6.1:** Given Settings > AI Accuracy, when viewing, then "Summary Accuracy" section visible
**AC-3.6.2:** Given summary feedback exists, when viewing stats, then total/positive/negative counts shown
**AC-3.6.3:** Given summary feedback exists, when viewing stats, then accuracy percentage calculated
**AC-3.6.4:** Given no summary feedback, when viewing stats, then "No feedback collected" message shown
**AC-3.6.5:** Given feedback over time, when viewing trends, then summary accuracy included in chart

---

## Traceability Mapping

| AC | Spec Section | Component(s) | Test Idea |
|----|--------------|--------------|-----------|
| AC-3.1.1-6 | Prompt Builder | prompt_builder.py, ai_service.py | Unit test prompt construction |
| AC-3.2.1-6 | OCR Service | ocr_service.py | Unit test with sample frames |
| AC-3.3.1-6 | Feedback UI | EventCard.tsx, feedback.py | Component + integration test |
| AC-3.4.1-6 | Summary Feedback | SummaryCard.tsx, feedback.py | Component + integration test |
| AC-3.5.1-6 | Settings UI | AIModelSettings.tsx, settings.py | Component + integration test |
| AC-3.6.1-5 | Accuracy Stats | AIAccuracySettings.tsx, feedback.py | Integration test |

---

## Risks, Assumptions, Open Questions

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| OCR accuracy varies by camera | High | Medium | Make OCR opt-in, always fall back to DB |
| Tesseract not installed on all systems | Medium | Medium | Graceful degradation, clear error message |
| Feedback data insufficient for refinement | Medium | Low | Require minimum samples before using |
| Custom prompts break AI responses | Low | Medium | Validate prompt format, preview option |

### Assumptions

- Camera names in database are meaningful (not "Camera 1")
- Event timestamps are accurate
- Users will provide meaningful feedback
- AI providers handle contextual prompts well

### Open Questions

- **Q1:** Should OCR be enabled by default?
  - **A:** No, opt-in due to CPU cost and tesseract dependency

- **Q2:** Minimum feedback samples before using in refinement?
  - **A:** 5 samples of same correction type

- **Q3:** Should we show AI the context or just use it internally?
  - **A:** Include in prompt - AI can incorporate naturally

- **Q4:** Summary prompt character limit?
  - **A:** 2000 characters max

---

## Test Strategy Summary

### Test Levels

| Level | Scope | Tools | Coverage |
|-------|-------|-------|----------|
| Unit | Context building, OCR | pytest | Core logic |
| Integration | Feedback API, Stats | pytest | Endpoints |
| Component | UI elements | vitest, RTL | Buttons, modals |
| E2E | Full feedback flow | Manual | User journeys |

### Test Cases by Story

**P9-3.1 (Context):**
- Unit: Time of day calculation
- Unit: Prompt construction with context
- Integration: Context appears in AI request

**P9-3.2 (OCR):**
- Unit: Timestamp regex patterns
- Unit: Camera name parsing
- Integration: OCR with sample images
- Error: Missing tesseract handling

**P9-3.3 (Package Feedback):**
- Component: Button visibility logic
- Component: Button state changes
- Integration: Feedback stored correctly

**P9-3.4 (Summary Feedback):**
- Component: Buttons render
- Component: Modal for negative feedback
- Integration: Feedback stored with summary_id

**P9-3.5 (Summary Prompt):**
- Component: Textarea renders
- Component: Reset button works
- Integration: Custom prompt used

**P9-3.6 (Stats):**
- Integration: Stats calculation
- Component: Stats display
- Integration: Chart includes summary data

### Test Data

- Sample frames with various overlay formats
- Frames without overlays
- Package events for feedback testing
- Summaries for feedback testing
- Various custom prompt formats

---

_Generated by BMAD Epic Tech Context Workflow_
_Date: 2025-12-22_
_For: Brent_
