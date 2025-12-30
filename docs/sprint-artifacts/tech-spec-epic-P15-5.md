# Epic Technical Specification: AI Visual Annotations

Date: 2025-12-30
Author: Brent
Epic ID: P15-5
Status: Draft

---

## Overview

Epic P15-5 adds visual annotations to AI-analyzed frames, drawing bounding boxes around detected objects with labels and confidence scores. This helps users understand exactly what the AI detected in each frame and provides visual feedback on detection accuracy. Annotations are color-coded by entity type and can be toggled on/off.

## Objectives and Scope

**In Scope:**
- AI response schema for bounding boxes (FR38)
- Backend service to draw annotations on frames (FR39, FR40, FR41, FR42)
- Store both original and annotated frames (FR44)
- Frontend toggle to show/hide annotations (FR43)
- Annotation legend component

**Out of Scope:**
- Real-time annotation during video streaming
- User-editable bounding boxes
- Training/feedback on bounding box accuracy
- 3D object detection or depth estimation
- Annotations for audio events

## System Architecture Alignment

This epic introduces AI response extensions and a new annotation service:

- **Bounding box schema** - Normalized coordinates (0-1) for resolution independence
- **FrameAnnotationService** - Pillow-based drawing service (ADR-P15-007)
- **Provider-specific support** - GPT-4o and Gemini have native bounding boxes
- **Graceful degradation** - Events without boxes still have descriptions

Reference: [Phase 15 Architecture](../architecture/phase-15-additions.md#frameannotationservice-p15-52)

## Detailed Design

### Services and Modules

| Component | Responsibility | File |
|-----------|---------------|------|
| AIService | Request bounding boxes from capable providers | `backend/app/services/ai_service.py` |
| FrameAnnotationService | Draw boxes on frames | `backend/app/services/frame_annotation_service.py` |
| EventProcessor | Integrate annotation into event pipeline | `backend/app/services/event_processor.py` |
| Event Model | Store has_annotations flag + bounding_boxes JSON | `backend/app/models/event.py` |
| EventDetailModal | Toggle and display annotations | `frontend/components/events/EventDetailModal.tsx` |
| AnnotationLegend | Color legend component | `frontend/components/events/AnnotationLegend.tsx` |

### Data Models and Contracts

**Event Model Extension:**

```sql
-- Add to existing events table
ALTER TABLE events ADD COLUMN has_annotations BOOLEAN DEFAULT FALSE;
ALTER TABLE events ADD COLUMN bounding_boxes TEXT;  -- JSON array
```

**Bounding Box JSON Schema:**

```json
[
  {
    "x": 0.25,           // Normalized 0-1 (left edge from left)
    "y": 0.30,           // Normalized 0-1 (top edge from top)
    "width": 0.15,       // Normalized 0-1
    "height": 0.40,      // Normalized 0-1
    "entity_type": "person",
    "confidence": 0.92,
    "label": "Person walking toward door"
  }
]
```

**Pydantic Schema:**

```python
# backend/app/schemas/ai.py
class BoundingBox(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(ge=0, le=1)
    height: float = Field(ge=0, le=1)
    entity_type: Literal["person", "vehicle", "package", "animal", "other"]
    confidence: float = Field(ge=0, le=1)
    label: str

class AIAnalysisResponse(BaseModel):
    description: str
    confidence: float | None
    bounding_boxes: list[BoundingBox] | None  # None for providers without support
```

**API Response:**

```python
# Extended EventResponse
class EventResponse(BaseModel):
    # ... existing fields ...
    has_annotations: bool
    bounding_boxes: list[BoundingBox] | None
    thumbnail_path: str | None
    annotated_thumbnail_path: str | None  # New field
```

### APIs and Interfaces

**Extended Event API:**

| Method | Endpoint | Description | Response Fields |
|--------|----------|-------------|----------------|
| GET | `/api/v1/events/{id}` | Get event detail | +`has_annotations`, +`annotated_thumbnail_path` |
| GET | `/api/v1/events/{id}/frames` | Get event frames | Each frame has `annotated_path` |

**File Paths:**

```
data/thumbnails/{event_id}/
├── frame_0.jpg              # Original frame
├── frame_0_annotated.jpg    # Annotated frame (if has_annotations)
├── frame_1.jpg
├── frame_1_annotated.jpg
└── ...
```

### Workflows and Sequencing

**Annotation Pipeline Flow:**

```
AI Provider returns description
       │
       ▼
Check if bounding_boxes included
       │
       ├──► None: Skip annotation (has_annotations=false)
       │
       └──► Has boxes: Proceed with annotation
                 │
                 ▼
┌─────────────────────────────┐
│  FrameAnnotationService     │
│  - Load original frame      │
│  - Draw each bounding box   │
│  - Add labels with colors   │
│  - Save as _annotated.jpg   │
└─────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────┐
│  Event record updated:      │
│  - has_annotations = true   │
│  - bounding_boxes = JSON    │
└─────────────────────────────┘
```

**Provider Capability Matrix:**

| Provider | Bounding Box Support | Notes |
|----------|---------------------|-------|
| OpenAI GPT-4o | ✓ Native | Use vision API with bounding box prompt |
| Google Gemini | ✓ Native | Use object detection mode |
| Anthropic Claude | ✗ | Would require prompt engineering (unreliable) |
| xAI Grok | ✗ | No vision bounding box support |

**AI Prompt Extension (for capable providers):**

```
Describe what you see in this image, focusing on security-relevant activity.

Additionally, for each detected object (person, vehicle, package, animal), provide:
- Bounding box coordinates as normalized values (0-1) for x, y, width, height
- Entity type (person, vehicle, package, animal, other)
- Confidence score (0-1)
- Brief label

Format bounding boxes as JSON array in your response.
```

### Color Palette

| Entity Type | RGB | Hex | Visual |
|-------------|-----|-----|--------|
| person | (59, 130, 246) | #3B82F6 | Blue |
| vehicle | (34, 197, 94) | #22C55E | Green |
| package | (249, 115, 22) | #F97316 | Orange |
| animal | (168, 85, 247) | #A855F7 | Purple |
| other | (156, 163, 175) | #9CA3AF | Gray |

## Non-Functional Requirements

### Performance

| Metric | Target | Notes |
|--------|--------|-------|
| Bounding box drawing | < 50ms per frame | Pillow optimized |
| Storage overhead | ~30% increase | Annotated frames larger |
| Frame load time | < 200ms | Either version |

### Security

- Annotated frames stored in same protected directory
- No external URLs or paths exposed
- Bounding box data sanitized (validated floats only)

### Reliability/Availability

- Annotation failure doesn't block event creation
- Missing annotated frame falls back to original
- Async processing (doesn't block response)

### Observability

- Log: Annotation success/failure per event
- Log: Provider bounding box support status
- Metric: Annotation processing time
- Metric: Average bounding boxes per frame

## Dependencies and Integrations

| Dependency | Version | Purpose | Status |
|------------|---------|---------|--------|
| Pillow | ^10.0 | Drawing bounding boxes | Existing |
| ImageDraw | (part of Pillow) | Rectangle/text drawing | Existing |

No new dependencies required. Pillow already used for image processing.

## Acceptance Criteria (Authoritative)

1. **AC1:** GPT-4o and Gemini requests include bounding box prompt extension
2. **AC2:** AI response parser extracts bounding_boxes array when present
3. **AC3:** Claude and Grok return bounding_boxes=null (graceful degradation)
4. **AC4:** FrameAnnotationService draws 2px stroke rectangles in correct colors
5. **AC5:** Labels appear above each bounding box with entity type and confidence %
6. **AC6:** Labels have white background for readability on any image
7. **AC7:** Original frame preserved at standard path
8. **AC8:** Annotated frame saved with `_annotated` suffix
9. **AC9:** Event detail shows toggle button when has_annotations=true
10. **AC10:** Toggle switches between original and annotated frame display
11. **AC11:** Toggle hidden when has_annotations=false
12. **AC12:** Color legend component shows all entity type colors
13. **AC13:** Annotation preference persists during session (React state)

## Traceability Mapping

| AC | FR | Spec Section | Component | Test Idea |
|----|-----|--------------|-----------|-----------|
| AC1 | FR38 | AI Prompt | AIService | Verify prompt includes bbox request |
| AC2 | FR38 | Response Parsing | AIService | Parse response with boxes |
| AC3 | FR38 | Graceful Degradation | AIService | Claude response, verify null |
| AC4 | FR39, FR42 | Drawing | FrameAnnotationService | Draw box, verify color |
| AC5 | FR40, FR41 | Labels | FrameAnnotationService | Verify label format |
| AC6 | FR40 | Readability | FrameAnnotationService | Check white background |
| AC7 | FR44 | Storage | EventProcessor | Original file exists |
| AC8 | FR44 | Storage | FrameAnnotationService | Annotated file exists |
| AC9 | FR43 | Toggle UI | EventDetailModal | has_annotations=true shows toggle |
| AC10 | FR43 | Toggle UI | EventDetailModal | Click toggle, verify image swap |
| AC11 | FR43 | Toggle UI | EventDetailModal | has_annotations=false hides toggle |
| AC12 | FR42 | Legend | AnnotationLegend | All colors displayed |
| AC13 | FR43 | Session State | EventDetailModal | Toggle persists on modal reopen |

## Risks, Assumptions, Open Questions

**Risks:**
- **Risk:** Bounding box coordinates inaccurate from AI
  - *Mitigation:* Validate coordinates (0-1 range), log anomalies, user feedback loop (future)

- **Risk:** Large bounding boxes obscure important content
  - *Mitigation:* Use thin (2px) strokes, semi-transparent fill optional

**Assumptions:**
- Assumption: Pillow installed and working in production environment
- Assumption: File system has space for ~30% more thumbnail storage
- Assumption: AI providers return consistent coordinate format

**Open Questions:**
- Q: Should we support video annotation (not just frames)?
  - *Recommendation:* Future phase - focus on frame-by-frame first

- Q: Should users be able to edit/correct bounding boxes?
  - *Recommendation:* Future phase - adds significant complexity

## Test Strategy Summary

**Unit Tests:**
- FrameAnnotationService: draw_rectangle, draw_label, color selection
- BoundingBox schema validation (0-1 range enforcement)
- JSON parsing/serialization of bounding_boxes

**Integration Tests:**
- Full pipeline: AI response → annotation → storage
- Event API returns annotated_thumbnail_path
- Toggle state in event detail

**E2E Tests (Playwright):**
- View event with annotations, verify toggle visible
- Click toggle, verify image changes
- View legend, verify all colors present

**Manual Testing:**
- Visual inspection of annotation quality
- Readability of labels on various backgrounds
- Mobile display of annotated frames
- Performance with many bounding boxes (10+)

## Implementation Notes

**FrameAnnotationService Implementation:**

```python
from PIL import Image, ImageDraw, ImageFont

class FrameAnnotationService:
    COLORS = {
        "person": (59, 130, 246),    # Blue
        "vehicle": (34, 197, 94),    # Green
        "package": (249, 115, 22),   # Orange
        "animal": (168, 85, 247),    # Purple
        "other": (156, 163, 175),    # Gray
    }

    def annotate_frame(self, frame_path: str, bounding_boxes: list[dict]) -> str:
        """Draw bounding boxes on frame, return annotated path."""
        img = Image.open(frame_path)
        draw = ImageDraw.Draw(img)
        width, height = img.size

        for box in bounding_boxes:
            x1 = int(box["x"] * width)
            y1 = int(box["y"] * height)
            x2 = int((box["x"] + box["width"]) * width)
            y2 = int((box["y"] + box["height"]) * height)

            color = self.COLORS.get(box["entity_type"], self.COLORS["other"])

            # Draw rectangle
            draw.rectangle([x1, y1, x2, y2], outline=color, width=2)

            # Draw label
            label = f"{box['entity_type']} {int(box['confidence'] * 100)}%"
            self._draw_label(draw, label, x1, y1 - 20, color)

        annotated_path = frame_path.replace(".jpg", "_annotated.jpg")
        img.save(annotated_path, quality=90)
        return annotated_path

    def _draw_label(self, draw, text, x, y, color):
        """Draw label with white background."""
        bbox = draw.textbbox((x, y), text)
        draw.rectangle(
            [bbox[0] - 2, bbox[1] - 2, bbox[2] + 2, bbox[3] + 2],
            fill=(255, 255, 255)
        )
        draw.text((x, y), text, fill=color)
```
