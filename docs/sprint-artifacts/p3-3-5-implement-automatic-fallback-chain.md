# Story P3-3.5: Implement Automatic Fallback Chain

Status: done

## Story

As a **system**,
I want **automatic fallback when configured analysis mode fails**,
So that **events always get descriptions even if video analysis fails**.

## Acceptance Criteria

1. **AC1:** Given camera configured for `video_native`, when video analysis fails (provider error, format issue), then system automatically tries `multi_frame`, and if that fails, tries `single_frame`, and event.fallback_reason records why each step failed

2. **AC2:** Given camera configured for `multi_frame`, when clip download fails, then system falls back to `single_frame` using thumbnail, and event.fallback_reason = "clip_download_failed"

3. **AC3:** Given fallback chain exhausted (`single_frame` also fails), when AI is completely unavailable, then event description = "AI analysis unavailable", and event is saved without description, and alert logged for operator

4. **AC4:** Given successful fallback, when event is saved, then event.analysis_mode = actual mode used (not configured mode), and event.fallback_reason explains the fallback

## Tasks / Subtasks

- [x] **Task 1: Analyze existing event processing flow** (AC: All)
  - [x] 1.1 Review `event_processor.py` to understand current AI analysis flow
  - [x] 1.2 Review `protect_event_handler.py` to understand Protect event pipeline
  - [x] 1.3 Identify where camera's `analysis_mode` preference is read
  - [x] 1.4 Map current fallback behavior (if any) and identify gaps

- [x] **Task 2: Implement fallback chain logic in ProtectEventHandler** (AC: 1, 2, 4)
  - [x] 2.1 Create `_try_video_native_analysis()` method that attempts video native mode
  - [x] 2.2 Update `_try_multi_frame_analysis()` method to track failure in fallback chain
  - [x] 2.3 Update `_single_frame_analysis()` method to handle AI failure detection
  - [x] 2.4 Implement fallback chain orchestrator: `video_native` -> `multi_frame` -> `single_frame`
  - [x] 2.5 Track each failure reason in structured format (e.g., "video_native:provider_unsupported,multi_frame:clip_download_timeout")
  - [x] 2.6 Update event.analysis_mode with ACTUAL mode used after processing
  - [x] 2.7 Update event.fallback_reason with failure chain if fallback occurred

- [x] **Task 3: Handle complete fallback failure** (AC: 3)
  - [x] 3.1 Implement final catch-all handler when single_frame also fails
  - [x] 3.2 Set event.description = "AI analysis unavailable" on complete failure
  - [x] 3.3 Log error alert for operator with event_id and failure chain details
  - [x] 3.4 Ensure event is saved to database even without AI description via `_store_event_without_ai()`

- [x] **Task 4: Verify fallback-related fields exist in Event model** (AC: All)
  - [x] 4.1 Verify `analysis_mode` field exists (confirmed in P3-3.1)
  - [x] 4.2 Verify `fallback_reason` field exists (confirmed in P3-1.4)
  - [x] 4.3 Determined `configured_analysis_mode` not needed - fallback_reason tracks failures adequately
  - [x] 4.4 No migration needed - all fields exist

- [x] **Task 5: Update Protect event flow to use fallback chain** (AC: 1, 2, 4)
  - [x] 5.1 Modified `_submit_to_ai_pipeline()` in `protect_event_handler.py` to implement full chain
  - [x] 5.2 Integrated fallback chain into Protect event processing path
  - [x] 5.3 Non-Protect cameras (RTSP/USB) bypass fallback chain and go directly to single_frame

- [x] **Task 6: Write backend tests** (AC: All)
  - [x] 6.1 Test fallback from video_native -> multi_frame -> single_frame
  - [x] 6.2 Test fallback from multi_frame -> single_frame on no clip/frame extraction failure
  - [x] 6.3 Test complete failure scenario (all modes fail)
  - [x] 6.4 Test fallback_reason is correctly populated
  - [x] 6.5 Test analysis_mode reflects actual mode used
  - [x] 6.6 Test non-Protect cameras (RTSP/USB) default to single_frame regardless of config

## Dev Notes

### Architecture References

- **Fallback Chain Pattern**: video_native -> multi_frame -> single_frame -> no description
- **Event Model Fields**: analysis_mode, fallback_reason (String, nullable)
- **Service Integration**: EventProcessor, ProtectEventHandler, ClipService, FrameExtractor, AIService
- [Source: docs/epics-phase3.md#Story-P3-3.5]
- [Source: docs/architecture.md#Event-Processing-Pipeline]

### Project Structure Notes

- Primary implementation: `backend/app/services/event_processor.py`
- Protect integration: `backend/app/services/protect_event_handler.py`
- Clip service: `backend/app/services/clip_service.py`
- Frame extractor: `backend/app/services/frame_extractor.py`
- AI service: `backend/app/services/ai_service.py`
- Event model: `backend/app/models/event.py`
- Event schema: `backend/app/schemas/event.py`

### Learnings from Previous Story

**From Story P3-3.4 (Status: done)**

- **AnalysisModeBadge Component Created**: `frontend/components/events/AnalysisModeBadge.tsx` - displays SF/MF/VN badges with fallback indicator support
- **Fallback Display Ready**: Frontend already supports showing fallback_reason in tooltip when present
- **Frontend Type Updated**: `IEvent` interface has `analysis_mode`, `frame_count_used`, `fallback_reason` fields
- **Backend Fields Exist**: Event model has `analysis_mode` (String, nullable), `frame_count_used` (Integer, nullable), `fallback_reason` (String, nullable) [Source: backend/app/models/event.py:63-66]
- **Console Logging Note**: Consider removing console.log statements from EventCard.tsx (lines 104, 107) - advisory from review

**Backend Support Already Exists (from prior stories):**
- ClipService for downloading Protect video clips [P3-1.1 - P3-1.4]
- FrameExtractor for extracting frames from clips [P3-2.1, P3-2.2]
- AIService.describe_images() for multi-image analysis [P3-2.3]
- Multi-frame prompts [P3-2.4]
- Multi-frame integration in pipeline [P3-2.6]
- Camera.analysis_mode field [P3-3.1]

[Source: docs/sprint-artifacts/p3-3-4-display-analysis-mode-on-event-cards.md#Dev-Agent-Record]

### Technical Notes from Epic

- Fallback chain: video_native -> multi_frame -> single_frame -> no description
- Track each failure reason in comma-separated fallback_reason
- Example: "video_native:provider_unsupported,multi_frame:clip_download_timeout"
- Implement in EventProcessor
- Non-Protect cameras (RTSP/USB) should effectively ignore video_native and multi_frame since no clips available

### Key Implementation Considerations

1. **Video Native**: Currently no providers fully support video_native in Phase 3 MVP scope (Epic P3-4 is Growth scope), so video_native should immediately fall back to multi_frame
2. **Multi-Frame**: Requires ClipService to download clip and FrameExtractor to extract frames
3. **Single Frame**: Uses existing thumbnail/snapshot-based analysis
4. **Non-Protect Cameras**: RTSP/USB cameras have no clips, so should always use single_frame regardless of configured mode

### References

- [Source: docs/epics-phase3.md#Story-P3-3.5]
- [Source: docs/architecture.md#Event-Processing-Pipeline]
- [Source: backend/app/services/event_processor.py]
- [Source: backend/app/services/protect_event_handler.py]
- [Source: backend/app/services/clip_service.py]
- [Source: backend/app/services/frame_extractor.py]
- [Source: backend/app/services/ai_service.py]
- [Source: backend/app/models/event.py]
- [Source: docs/sprint-artifacts/p3-3-4-display-analysis-mode-on-event-cards.md]

## Dev Agent Record

### Context Reference

- `docs/sprint-artifacts/p3-3-5-implement-automatic-fallback-chain.context.xml`

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

N/A - No debug issues encountered.

### Completion Notes List

1. **Implementation Location Changed**: Implemented in `ProtectEventHandler` instead of `EventProcessor` because that's where multi-frame analysis logic already exists. RTSP/USB cameras go through different paths and don't need fallback chain (no clips available).

2. **Video Native Always Fails**: Since video native providers aren't supported in Phase 3 MVP, `_try_video_native_analysis()` always returns None with reason "provider_unsupported". Epic P3-4 (Growth) will implement actual video upload.

3. **Non-Protect Camera Optimization**: RTSP/USB cameras bypass the fallback chain entirely and go directly to single_frame analysis, since they have no clip source.

4. **New Method Added**: `_store_event_without_ai()` method created to handle AC3 (complete failure scenario) - saves event with description="AI analysis unavailable" and description_retry_needed=True.

5. **Fallback Chain Tracking**: Using `_fallback_chain` list to accumulate failures, then joining with commas for `fallback_reason` field.

6. **All 12 Tests Pass**: Test coverage includes all AC requirements and edge cases.

### File List

**Modified:**
- `backend/app/services/protect_event_handler.py` - Refactored `_submit_to_ai_pipeline()` with full fallback chain, added `_try_video_native_analysis()`, `_store_event_without_ai()`, updated `_try_multi_frame_analysis()` and `_single_frame_analysis()` for chain tracking

**Added:**
- `backend/tests/test_services/test_fallback_chain.py` - 12 tests covering all acceptance criteria

## Change Log

| Date | Version | Description |
|------|---------|-------------|
| 2025-12-06 | 1.0 | Story drafted from epics-phase3.md |
| 2025-12-06 | 2.0 | Story implementation complete - all ACs satisfied, 12 tests passing |
