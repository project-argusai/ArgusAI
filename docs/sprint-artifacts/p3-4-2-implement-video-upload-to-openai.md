# Story P3-4.2: Implement Video Upload to OpenAI

Status: done

## Story

As a **system**,
I want **to send video clips to OpenAI GPT-4o**,
So that **users get video-native analysis from OpenAI**.

## Acceptance Criteria

1. **AC1:** ~~Given a video clip under 20MB and 60 seconds, when `AIService.describe_video(video_path, prompt)` is called for OpenAI, then video is uploaded using OpenAI's video API, and vision request references the uploaded video, and description is returned.~~ **NOT APPLICABLE** - Research confirmed OpenAI does not support native video upload.

2. **AC2:** ~~Given video exceeds OpenAI limits (>20MB or >60s), when video analysis is attempted, then returns None with error "Video exceeds OpenAI limits", and triggers fallback to multi_frame.~~ **NOT APPLICABLE** - OpenAI will always use multi_frame analysis.

3. **AC3:** ~~Given video format is not supported, when analysis is attempted, then system converts to supported format (MP4/H.264), and retries with converted file.~~ **NOT APPLICABLE** - No video upload means no format conversion needed.

4. **AC4:** ~~Given video upload succeeds, when analysis completes, then uploaded file is cleaned up from temporary storage.~~ **NOT APPLICABLE** - No video upload to clean up.

## Tasks / Subtasks

- [x] **Task 1: Research OpenAI video API capabilities** (AC: All)
  - [x] 1.1 Verify OpenAI GPT-4o video input format requirements - **FINDING: No native video support**
  - [x] 1.2 Confirm base64 encoding vs file upload approach - **FINDING: Frame extraction only**
  - [x] 1.3 Document size limits, duration limits, and supported formats - **N/A**
  - [x] 1.4 Identify model requirements (gpt-4o vs gpt-4o-mini) - **Both support frame-based analysis**

- [x] **Task 2: Update PROVIDER_CAPABILITIES** (Replacement for original Task 2)
  - [x] 2.1 Set OpenAI video: false in PROVIDER_CAPABILITIES
  - [x] 2.2 Set max_video_duration: 0
  - [x] 2.3 Set max_video_size_mb: 0
  - [x] 2.4 Set supported_formats: []

- [x] **Task 3: Update fallback chain comments** (Replacement for original Task 3)
  - [x] 3.1 Update _try_video_native_analysis() comments to document OpenAI limitation
  - [x] 3.2 Document that only Gemini supports native video upload

- [N/A] **Task 4: Implement describe_video() method for OpenAI** - Not needed, OpenAI doesn't support video

- [N/A] **Task 5: Integrate with fallback chain** - Automatic - OpenAI will use multi_frame mode

- [N/A] **Task 6: Track usage for video requests** - N/A for OpenAI

- [x] **Task 7: Update tests for capability detection**
  - [x] 7.1 Update test_provider_capabilities_openai_supports_video -> test_provider_capabilities_openai_no_video
  - [x] 7.2 Update test_get_provider_capabilities_openai assertions
  - [x] 7.3 Update test_supports_video_openai to assert False
  - [x] 7.4 Update test_get_video_capable_providers_all_configured to exclude OpenAI
  - [x] 7.5 Update test_get_max_video_duration_openai to assert 0

## Dev Notes

### Critical Research Finding

**OpenAI GPT-4o does NOT support native video file upload via API.**

Sources:
- [OpenAI Community Discussion](https://community.openai.com/t/does-gpt-4o-api-natively-support-video-input-like-gemini-1-5/784779)
- [OpenAI Cookbook - GPT with Vision for Video Understanding](https://cookbook.openai.com/examples/gpt_with_vision_for_video_understanding)
- [Introduction to GPT-4o](https://cookbook.openai.com/examples/gpt4o/introduction_to_gpt4o)

Key findings:
1. OpenAI only supports sending images (frames extracted from video)
2. There is no `video_url` content type in the OpenAI API
3. The recommended approach is to extract frames using OpenCV and send as base64 images
4. This is exactly what our existing `multi_frame` analysis mode does (P3-2.x)
5. **Only Gemini supports native video file upload**

### Architecture Impact

Since OpenAI doesn't support native video upload:
- `video_native` analysis mode will only work with Gemini (P3-4.3)
- OpenAI video analysis should use `multi_frame` mode (already implemented in P3-2.x)
- The fallback chain correctly handles this: video_native skips non-video providers

### Updated PROVIDER_CAPABILITIES

```python
"openai": {
    "video": False,  # P3-4.2: OpenAI does NOT support native video upload
    "max_video_duration": 0,
    "max_video_size_mb": 0,
    "supported_formats": [],
    "max_images": 10,
}
```

### References

- [Source: docs/epics-phase3.md#Story-P3-4.2]
- [Source: backend/app/services/ai_service.py:82-101]
- [Source: backend/app/services/protect_event_handler.py:1093-1098]

## Dev Agent Record

### Context Reference

- `docs/sprint-artifacts/p3-4-2-implement-video-upload-to-openai.context.xml`

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

N/A

### Completion Notes List

1. **Research Phase**: Extensive web search and documentation review confirmed OpenAI GPT-4o does NOT support native video file upload via API. The only supported approach is frame extraction + image analysis.

2. **Capability Update**: Updated `PROVIDER_CAPABILITIES` in `ai_service.py` to set OpenAI `video: false` with appropriate documentation comments citing the OpenAI community discussion.

3. **Fallback Chain**: Updated comments in `protect_event_handler.py` `_try_video_native_analysis()` to document that OpenAI doesn't support video and only Gemini does.

4. **Test Updates**: Updated 5 tests in `test_ai_service.py` to reflect OpenAI's lack of native video support:
   - `test_provider_capabilities_openai_no_video`
   - `test_get_provider_capabilities_openai`
   - `test_supports_video_openai`
   - `test_get_video_capable_providers_all_configured`
   - `test_get_max_video_duration_openai`

5. **All 23 capability tests pass** after updates.

### File List

- `backend/app/services/ai_service.py` - Updated PROVIDER_CAPABILITIES for OpenAI
- `backend/app/services/protect_event_handler.py` - Updated comments in _try_video_native_analysis()
- `backend/tests/test_services/test_ai_service.py` - Updated 5 capability tests

## Change Log

| Date | Version | Description |
|------|---------|-------------|
| 2025-12-07 | 1.0 | Story drafted from epics-phase3.md with context from P3-4.1 |
| 2025-12-07 | 2.0 | Research completed - OpenAI does NOT support native video upload. Updated PROVIDER_CAPABILITIES and tests. Story marked done. |
