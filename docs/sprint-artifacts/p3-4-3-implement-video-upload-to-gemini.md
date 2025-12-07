# Story P3-4.3: Implement Video Upload to Gemini

Status: ready-for-dev

## Story

As a **system**,
I want **to send video clips to Google Gemini**,
So that **users get video-native analysis from Gemini for the highest quality event descriptions**.

## Acceptance Criteria

1. **AC1:** Given a video clip under Gemini's limits (20MB, 60s per PROVIDER_CAPABILITIES), when `AIService.describe_video()` is called for Gemini, then video is sent using Gemini's video API format, and description is returned.

2. **AC2:** Given video needs format conversion for Gemini, when original format unsupported, then converts to supported format (mp4/mov/webm) using PyAV, and retries with converted file.

3. **AC3:** Given Gemini video analysis completes, when response is received, then token usage is tracked, and cost estimate is calculated.

4. **AC4:** Given Gemini provider is configured with valid API key, when `describe_video()` is called with valid clip path, then method succeeds and returns AIResult with description.

5. **AC5:** Given video exceeds Gemini limits (>20MB or >60s), when video analysis is attempted, then returns AIResult with success=False, and error message indicates size/duration exceeded, and triggers fallback to multi_frame.

## Tasks / Subtasks

- [ ] **Task 1: Research Gemini Video API** (AC: All)
  - [ ] 1.1 Verify Gemini 1.5 Flash/Pro video input format requirements
  - [ ] 1.2 Confirm file upload vs inline base64 approach
  - [ ] 1.3 Document size limits, duration limits, and supported formats
  - [ ] 1.4 Identify model requirements (gemini-1.5-flash vs gemini-1.5-pro)

- [ ] **Task 2: Implement `describe_video()` method in GeminiProvider** (AC: 1, 4)
  - [ ] 2.1 Add `describe_video()` async method to GeminiProvider class
  - [ ] 2.2 Read video file and convert to Gemini-compatible format
  - [ ] 2.3 Use genai library to send video content with prompt
  - [ ] 2.4 Parse response and return AIResult

- [ ] **Task 3: Add video size/duration validation** (AC: 5)
  - [ ] 3.1 Implement `_validate_video_for_gemini()` helper method
  - [ ] 3.2 Check file size against max_video_size_mb from PROVIDER_CAPABILITIES
  - [ ] 3.3 Check duration against max_video_duration from PROVIDER_CAPABILITIES
  - [ ] 3.4 Return early with descriptive error if limits exceeded

- [ ] **Task 4: Implement video format conversion** (AC: 2)
  - [ ] 4.1 Add `_convert_video_format()` method using PyAV
  - [ ] 4.2 Support conversion to MP4/H.264 (most compatible)
  - [ ] 4.3 Preserve video quality during conversion
  - [ ] 4.4 Clean up converted file after use

- [ ] **Task 5: Add token/cost tracking for video requests** (AC: 3)
  - [ ] 5.1 Extract token usage from Gemini response (if available)
  - [ ] 5.2 Estimate tokens if not provided by API (video tokens differ from image)
  - [ ] 5.3 Calculate cost using COST_RATES for gemini

- [ ] **Task 6: Update `_try_video_native_analysis()` in protect_event_handler** (AC: All)
  - [ ] 6.1 Remove "video_upload_not_implemented" placeholder
  - [ ] 6.2 Call ai_service.describe_video() for Gemini
  - [ ] 6.3 Handle success/failure with proper fallback chain updates
  - [ ] 6.4 Track analysis_mode as "video_native" on success

- [ ] **Task 7: Add AIService orchestration for describe_video** (AC: All)
  - [ ] 7.1 Add `describe_video()` method to AIService class
  - [ ] 7.2 Route to video-capable providers only (currently only Gemini)
  - [ ] 7.3 Handle provider fallback for video analysis
  - [ ] 7.4 Track usage in AIUsage model

- [ ] **Task 8: Write tests** (AC: All)
  - [ ] 8.1 Unit test GeminiProvider.describe_video() with mocked genai
  - [ ] 8.2 Unit test video validation (size/duration limits)
  - [ ] 8.3 Unit test format conversion (if implemented)
  - [ ] 8.4 Unit test _try_video_native_analysis() with Gemini
  - [ ] 8.5 Integration test end-to-end video_native analysis

## Dev Notes

### Key Implementation Patterns from Previous Stories

**From P3-4.1 (Provider Capability Detection):**
- PROVIDER_CAPABILITIES dict at `ai_service.py:94-123` defines video support
- Gemini capabilities: `video: True, max_video_duration: 60, max_video_size_mb: 20, supported_formats: ["mp4", "mov", "webm"]`
- Use `ai_service.get_video_capable_providers()` to get list of video-capable providers
- Use `ai_service.supports_video(provider)` to check if specific provider supports video

**From P3-4.2 (OpenAI Research):**
- Only Gemini supports native video upload - OpenAI uses frame extraction
- Current `_try_video_native_analysis()` returns "video_upload_not_implemented"
- Fallback chain: video_native -> multi_frame -> single_frame
- Track each failure in `self._fallback_chain` list

**From P3-2.3/P3-2.6 (Multi-Image Implementation):**
- GeminiProvider.generate_multi_image_description() shows pattern for multi-part content
- Use `genai.GenerativeModel('gemini-1.5-flash')`
- Pass parts array with prompt + media to `generate_content_async()`
- Token estimation: `tokens_used = 150 + (len(images_base64) * 50)`

### Gemini Video API Approach

Based on google.generativeai library patterns:
```python
# Video as inline_data (similar to images)
video_bytes = Path(clip_path).read_bytes()
video_part = {"mime_type": "video/mp4", "data": video_bytes}

response = await self.model.generate_content_async(
    [prompt, video_part],
    generation_config=genai.types.GenerationConfig(
        max_output_tokens=500,
        temperature=0.4
    )
)
```

Alternatively, using File API for large videos:
```python
# Upload file first (for larger videos)
video_file = genai.upload_file(path=clip_path)
response = await self.model.generate_content_async([prompt, video_file])
```

### Video-Specific Prompt Considerations

For video analysis, prompt should emphasize temporal narrative:
- Reference MULTI_FRAME_SYSTEM_PROMPT pattern from P3-2.4
- Add video-specific context: "This is a video clip from a security camera"
- Request action-based descriptions

### Files to Modify

1. `backend/app/services/ai_service.py`
   - Add `describe_video()` to GeminiProvider class
   - Add `describe_video()` to AIService class for orchestration

2. `backend/app/services/protect_event_handler.py`
   - Update `_try_video_native_analysis()` to call actual Gemini video analysis

3. `backend/tests/test_services/test_ai_service.py`
   - Add video analysis tests

### Project Structure Notes

- Video processing uses PyAV (av library) - already in requirements
- ClipService downloads clips to `data/clips/{event_id}.mp4`
- Format conversion should use same library for consistency

### Error Handling

- Gemini quota exceeded: Return error, don't retry
- Network timeout: Retry once, then fallback
- Invalid video format: Try conversion, then fallback
- Empty/corrupt video: Return error immediately

### References

- [Source: docs/epics-phase3.md#Story-P3-4.3]
- [Source: backend/app/services/ai_service.py:116-123] - Gemini PROVIDER_CAPABILITIES
- [Source: backend/app/services/ai_service.py:776-945] - GeminiProvider class
- [Source: backend/app/services/protect_event_handler.py:1093-1114] - _try_video_native_analysis placeholder
- [Source: docs/sprint-artifacts/p3-4-2-implement-video-upload-to-openai.md] - OpenAI research findings

### Learnings from Previous Story

**From Story p3-4-2-implement-video-upload-to-openai (Status: done)**

- **Critical Finding**: Only Gemini supports native video file upload. OpenAI does NOT support video upload via API.
- **Capability Update**: PROVIDER_CAPABILITIES already correctly shows Gemini `video: true` with 60s/20MB limits
- **Fallback Placeholder**: Current code at protect_event_handler.py:1099-1100 sets `reason = "video_upload_not_implemented"` - this story will replace this with actual Gemini video analysis
- **Testing Pattern**: Tests in test_ai_service.py verify capability detection - extend for actual video analysis

[Source: docs/sprint-artifacts/p3-4-2-implement-video-upload-to-openai.md#Dev-Agent-Record]

## Dev Agent Record

### Context Reference

- `docs/sprint-artifacts/p3-4-3-implement-video-upload-to-gemini.context.xml`

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List

## Change Log

| Date | Version | Description |
|------|---------|-------------|
| 2025-12-07 | 1.0 | Story drafted from epics-phase3.md with context from P3-4.1 and P3-4.2 |
