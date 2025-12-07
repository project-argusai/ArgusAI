# Story P3-4.2: Implement Video Upload to OpenAI

Status: done

## Story

As a **system**,
I want **to send video clips to OpenAI GPT-4o**,
So that **users get video-native analysis from OpenAI**.

## Acceptance Criteria

1. **AC1:** Given a video clip, when `video_native` mode is selected for OpenAI, then the system extracts frames at 1-4 fps, sends them as images to GPT-4o, and returns a description covering the video content.

2. **AC2:** Given video exceeds practical limits (too many frames), when video analysis is attempted, then system limits to reasonable frame count (e.g., max 10 frames for cost control) and processes successfully.

3. **AC3:** Given video has audio content, when analysis includes audio transcription (via Whisper), then the transcript is included in the prompt context for richer descriptions.

4. **AC4:** Given OpenAI is configured as a video-capable provider, when `video_native` mode is triggered, then OpenAI uses the frame-extraction pipeline (not direct video upload).

5. **AC5:** Given frame extraction and analysis completes, when response is received, then token usage is tracked accurately for multi-image request.

## Tasks / Subtasks

- [x] **Task 1: Research OpenAI video API capabilities** (AC: All)
  - [x] 1.1 Verify OpenAI GPT-4o video input format requirements
  - [x] 1.2 Confirm base64 encoding vs file upload approach
  - [x] 1.3 Document size limits, duration limits, and supported formats
  - [x] 1.4 Identify model requirements (gpt-4o vs gpt-4o-mini)

- [x] **Task 2: Update PROVIDER_CAPABILITIES for OpenAI** (AC: 4)
  - [x] 2.1 Set OpenAI `video: true` (supports video via frame extraction)
  - [x] 2.2 Set `video_method: "frame_extraction"` to distinguish from native upload
  - [x] 2.3 Set reasonable limits: `max_video_duration: 60`, `max_video_size_mb: 50`
  - [x] 2.4 Document that OpenAI uses frame extraction, not direct video upload

- [x] **Task 3: Implement OpenAI video analysis via frame extraction** (AC: 1, 2)
  - [x] 3.1 Add `describe_video()` method to OpenAIProvider class
  - [x] 3.2 Use existing FrameExtractor to extract frames at 1-4 fps
  - [x] 3.3 Limit frames to max 10 for cost control
  - [x] 3.4 Call existing `generate_multi_image_description()` with extracted frames
  - [x] 3.5 Return AIResult with video-specific metadata

- [x] **Task 4: Add optional audio transcription support** (AC: 3)
  - [x] 4.1 Check if video has audio track
  - [x] 4.2 If audio present, extract and transcribe via Whisper API
  - [x] 4.3 Include transcript in prompt context
  - [x] 4.4 Make audio transcription optional (include_audio parameter)

- [x] **Task 5: Update _try_video_native_analysis() for OpenAI** (AC: 4)
  - [x] 5.1 Check if provider uses `video_method: "frame_extraction"`
  - [x] 5.2 Route OpenAI to frame-extraction pipeline via _try_video_frame_extraction()
  - [x] 5.3 Route Gemini to native video upload (P3-4.3)
  - [x] 5.4 Update logging to reflect video method used

- [x] **Task 6: Add token/cost tracking for video requests** (AC: 5)
  - [x] 6.1 Track token usage from multi-image response
  - [x] 6.2 Calculate cost using COST_RATES for openai
  - [x] 6.3 Log analysis mode as "video_native (frame_extraction)"

- [x] **Task 7: Write tests** (AC: All)
  - [x] 7.1 Test OpenAIProvider.describe_video() extracts frames and calls multi-image
  - [x] 7.2 Test frame limit enforcement (max 10 frames)
  - [x] 7.3 Test audio transcription integration (optional)
  - [x] 7.4 Test _try_video_native_analysis() routes correctly for OpenAI
  - [x] 7.5 Test PROVIDER_CAPABILITIES reflects frame_extraction method

## Dev Notes

### Updated Research Finding (2025-12-07)

**OpenAI GPT-4o CAN process video via the API - but through frame extraction, not native upload.**

The key insight from comprehensive research:
- GPT-4o was introduced as a multimodal model supporting text, image, audio, AND video
- However, **you cannot upload a raw video file (MP4)** to the API directly
- The **official recommended approach**: extract still frames (1-4 fps) + optionally extract audio (via Whisper), then send frames as images + transcript as text
- This approach enables: scene descriptions, summarization, Q&A about video content

### Official Sources

- [GPT-4o System Card (arXiv)](https://arxiv.org/abs/2410.21276) - Confirms video support in principle
- [OpenAI Community - File Upload](https://community.openai.com/t/why-file-upload-does-not-accept-mp4-files/863541) - Confirms MP4 not accepted for direct upload
- [OpenAI Cookbook - Introduction to GPT-4o](https://cookbook.openai.com/examples/gpt4o/introduction_to_gpt4o) - Shows frame extraction approach
- [Portkey Docs - GPT-4o Guide](https://portkey.ai/docs/guides/integrations/introduction-to-gpt-4o) - Documents frame + audio approach

### Key Findings Summary

| Aspect | Status |
|--------|--------|
| Native video file upload | ❌ Not supported |
| Frame extraction + images | ✅ Supported and recommended |
| Audio extraction + Whisper | ✅ Supported (optional enhancement) |
| Real-time video stream | ❌ Not supported via API |

### Architecture Impact

Since OpenAI supports video via frame extraction:

1. **PROVIDER_CAPABILITIES Update Required**:
   ```python
   "openai": {
       "video": True,  # Supports video via frame extraction
       "video_method": "frame_extraction",  # Not native upload
       "max_video_duration": 60,
       "max_video_size_mb": 20,
       "max_frames": 10,  # Cost control
       "supported_formats": ["mp4", "mov", "webm"],
       "max_images": 10,
   }
   ```

2. **Video Processing Flow for OpenAI**:
   ```
   Video Clip → FrameExtractor (1-4 fps) → Limit to 10 frames
                                         ↓
   Optional: Audio → Whisper API → Transcript
                                         ↓
   Frames + Transcript → generate_multi_image_description() → AIResult
   ```

3. **Distinction from Gemini**:
   - OpenAI: `video_method: "frame_extraction"` - uses existing multi-image pipeline
   - Gemini: `video_method: "native_upload"` - uploads video file directly (P3-4.3)

### Implementation Strategy

The good news: **We already have most of the infrastructure!**

- `FrameExtractor` service (P3-2.1) - extracts frames from clips
- `generate_multi_image_description()` (P3-2.3) - handles multi-image for all providers
- `MULTI_FRAME_SYSTEM_PROMPT` (P3-2.4) - temporal narrative prompts

### Reference Implementation (OpenAI Cookbook Pattern)

**Frame Extraction** (we use PyAV, but pattern is same):
```python
# Extract 1 frame/sec — adjust fps= for more detail
ffmpeg.input(VIDEO_PATH).filter('fps', fps=1).output(f"{FRAMES_DIR}/frame_%04d.jpg").run()
```

**Optional Audio Transcription via Whisper**:
```python
from openai import OpenAI
client = OpenAI()

# Extract audio from video
ffmpeg.input(VIDEO_PATH).output(AUDIO_PATH, acodec='pcm_s16le', ac=1, ar='16k').run()

# Transcribe with Whisper
audio_transcript = client.audio.transcriptions.create(
    model="gpt-4o-transcribe",  # or "whisper-1"
    file=open(AUDIO_PATH, "rb")
).text
```

**Send Frames + Transcript to GPT-4o**:
```python
import base64

def encode_image(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

# Encode up to first 10 frames
frame_files = sorted(os.listdir(FRAMES_DIR))[:10]
images = [encode_image(os.path.join(FRAMES_DIR, f)) for f in frame_files]

messages = [
    {"role": "system", "content": "You are a video analysis assistant."},
    {"role": "user", "content": [
        {"type": "text", "text": "Here are frames extracted from a video. Analyze what's happening."},
        {"type": "text", "text": f"Audio transcript: {audio_transcript if audio_transcript else 'No audio'}"},
    ]},
]

# Add images to the message
for img in images:
    messages[1]["content"].append({
        "type": "image_url",
        "image_url": {"url": f"data:image/jpeg;base64,{img}"}
    })

response = client.chat.completions.create(
    model="gpt-4o",
    messages=messages,
)
```

### Our Implementation (Adapting to Existing Infrastructure)

The `describe_video()` method for OpenAI will leverage existing services:

```python
async def describe_video(
    self,
    video_path: Path,
    camera_name: str,
    timestamp: str,
    detected_objects: List[str],
    include_audio: bool = False,
    custom_prompt: Optional[str] = None
) -> AIResult:
    """
    Analyze video using frame extraction + optional audio transcription.
    Uses existing FrameExtractor and generate_multi_image_description().
    """
    from app.services.frame_extractor import get_frame_extractor

    # 1. Extract frames using existing FrameExtractor (P3-2.1)
    frame_extractor = get_frame_extractor()
    frames = await frame_extractor.extract_frames(
        clip_path=video_path,
        frame_count=10,  # Max 10 frames for cost control
        strategy="evenly_spaced",
        filter_blur=True
    )

    if not frames:
        return AIResult(success=False, error="No frames extracted from video")

    # Convert frames to base64 (FrameExtractor returns numpy arrays)
    frames_base64 = [self._frame_to_base64(frame) for frame in frames]

    # 2. Optional: Transcribe audio via Whisper
    transcript = None
    if include_audio:
        transcript = await self._transcribe_audio(video_path)

    # 3. Build enhanced prompt with transcript context
    enhanced_prompt = custom_prompt or ""
    if transcript:
        enhanced_prompt = f"Audio transcript: {transcript}\n\n{enhanced_prompt}"

    # 4. Use existing multi-image method (P3-2.3)
    return await self.generate_multi_image_description(
        images_base64=frames_base64,
        camera_name=camera_name,
        timestamp=timestamp,
        detected_objects=detected_objects,
        custom_prompt=enhanced_prompt if enhanced_prompt else None
    )

async def _transcribe_audio(self, video_path: Path) -> Optional[str]:
    """Extract and transcribe audio from video using Whisper API."""
    import tempfile
    import av

    try:
        # Extract audio to temp file using PyAV
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
            # Use PyAV to extract audio (we already have av in requirements)
            container = av.open(str(video_path))
            audio_stream = next((s for s in container.streams if s.type == 'audio'), None)

            if not audio_stream:
                return None  # No audio track

            # Extract and save audio
            # ... (implementation details)

            # Transcribe with Whisper
            with open(temp_audio.name, "rb") as audio_file:
                transcript = await self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                )
            return transcript.text

    except Exception as e:
        logger.warning(f"Audio transcription failed: {e}")
        return None
```

### Files to Modify

1. `backend/app/services/ai_service.py`
   - Update PROVIDER_CAPABILITIES for OpenAI (video: true, video_method: frame_extraction)
   - Add `describe_video()` to OpenAIProvider class

2. `backend/app/services/protect_event_handler.py`
   - Update `_try_video_native_analysis()` to check `video_method`
   - Route frame_extraction providers to frame-based pipeline

3. `backend/tests/test_services/test_ai_service.py`
   - Update capability tests
   - Add describe_video() tests

### References

- [Source: docs/epics-phase3.md#Story-P3-4.2]
- [Source: backend/app/services/ai_service.py:82-123] - PROVIDER_CAPABILITIES
- [Source: backend/app/services/ai_service.py:776-945] - Provider classes
- [Source: backend/app/services/frame_extractor.py] - FrameExtractor service
- [Source: backend/app/services/protect_event_handler.py:1014-1114] - _try_video_native_analysis

## Dev Agent Record

### Context Reference

- `docs/sprint-artifacts/p3-4-2-implement-video-upload-to-openai.context.xml`

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

N/A

### Completion Notes List

1. **Initial Research (v2.0)**: Concluded OpenAI doesn't support video - marked story as N/A.

2. **Updated Research (v3.0)**: Found comprehensive documentation confirming OpenAI DOES support video via frame extraction approach. This aligns with our existing multi_frame infrastructure.

3. **Implementation Complete (v4.0)**: All tasks implemented and tested:
   - Updated PROVIDER_CAPABILITIES with video=True, video_method="frame_extraction"
   - Added describe_video() method to OpenAIProvider (lines 580-734)
   - Added _transcribe_audio() helper using PyAV + Whisper API (lines 736-837)
   - Updated _try_video_native_analysis() to route frame_extraction providers
   - Added _try_video_frame_extraction() method in protect_event_handler.py
   - Added get_provider_order() public method to AIService
   - All 115 tests pass including 18 new tests for P3-4.2

### File List

- `backend/app/services/ai_service.py` - PROVIDER_CAPABILITIES, describe_video(), _transcribe_audio(), get_provider_order()
- `backend/app/services/protect_event_handler.py` - _try_video_native_analysis(), _try_video_frame_extraction()
- `backend/tests/test_services/test_ai_service.py` - 18 new tests for P3-4.2 functionality

## Change Log

| Date | Version | Description |
|------|---------|-------------|
| 2025-12-07 | 1.0 | Story drafted from epics-phase3.md with context from P3-4.1 |
| 2025-12-07 | 2.0 | Research completed - Initially concluded OpenAI doesn't support video. Updated PROVIDER_CAPABILITIES to video: false. |
| 2025-12-07 | 3.0 | **REVISED** - New research confirms OpenAI CAN process video via frame extraction + optional audio. Story reopened with updated ACs and tasks. |
| 2025-12-07 | 3.1 | Added reference implementation code from OpenAI Cookbook pattern. Added detailed `describe_video()` and `_transcribe_audio()` implementation examples. |
| 2025-12-07 | 4.0 | **COMPLETE** - All tasks implemented. describe_video() with frame extraction, optional Whisper audio transcription, updated protect_event_handler routing, 115 tests passing including 18 new P3-4.2 tests. |
| 2025-12-07 | 5.0 | Senior Developer Review (AI) appended - APPROVED |

---

## Senior Developer Review (AI)

### Reviewer
Brent (AI-assisted)

### Date
2025-12-07

### Outcome
**APPROVE** ✅

All acceptance criteria verified with evidence. All completed tasks confirmed. Code quality is high with proper patterns, error handling, and comprehensive tests.

### Summary

Story P3-4.2 implements OpenAI video analysis via the frame extraction approach (as documented in OpenAI Cookbook). The implementation:

1. Updated PROVIDER_CAPABILITIES to mark OpenAI as video-capable via `video_method: "frame_extraction"`
2. Added `describe_video()` method to OpenAIProvider that extracts frames using existing FrameExtractor
3. Added optional Whisper audio transcription support with `_transcribe_audio()` helper
4. Updated protect_event_handler routing to direct frame_extraction providers correctly
5. All 115 AI service tests pass, including 18 new tests for P3-4.2

### Acceptance Criteria Coverage

| AC# | Description | Status | Evidence |
|-----|-------------|--------|----------|
| AC1 | Frame extraction at 1-4 fps, sends as images | ✅ IMPLEMENTED | `ai_service.py:580-734` |
| AC2 | Limits to max 10 frames for cost control | ✅ IMPLEMENTED | `ai_service.py:100-101, 636` |
| AC3 | Audio transcription via Whisper included in prompt | ✅ IMPLEMENTED | `ai_service.py:671-679, 736-837` |
| AC4 | OpenAI uses frame-extraction pipeline | ✅ IMPLEMENTED | `ai_service.py:97-98`, `protect_event_handler.py:1136-1144` |
| AC5 | Token usage tracked accurately | ✅ IMPLEMENTED | `ai_service.py:700-703` |

**Summary: 5 of 5 acceptance criteria fully implemented**

### Task Completion Validation

| Task | Status | Evidence |
|------|--------|----------|
| Task 1: Research OpenAI video API | ✅ VERIFIED | Story Dev Notes with 4 sources |
| Task 2: Update PROVIDER_CAPABILITIES | ✅ VERIFIED | `ai_service.py:95-105` |
| Task 3: Implement describe_video() | ✅ VERIFIED | `ai_service.py:580-734` |
| Task 4: Add audio transcription | ✅ VERIFIED | `ai_service.py:736-837` |
| Task 5: Update routing | ✅ VERIFIED | `protect_event_handler.py:1093-1175, 1177-1299` |
| Task 6: Token/cost tracking | ✅ VERIFIED | Inherited from multi-image, logged at 700-703 |
| Task 7: Write tests | ✅ VERIFIED | 18 new tests in `test_ai_service.py:2280-2723` |

**Summary: 28 of 28 completed tasks verified, 0 falsely marked**

### Test Coverage and Gaps

- ✅ 18 new tests added for P3-4.2
- ✅ All 115 AI service tests pass
- ✅ Tests cover: frame extraction, frame limits, audio transcription (with/without), error handling, token tracking
- ✅ Tests properly mock FrameExtractor and OpenAI client

### Architectural Alignment

- ✅ Follows existing provider pattern (AIProviderBase methods)
- ✅ Reuses FrameExtractor (P3-2.1) and generate_multi_image_description (P3-2.3)
- ✅ PROVIDER_CAPABILITIES structure extended with video_method field
- ✅ Routing logic in protect_event_handler correctly distinguishes frame_extraction vs native_upload

### Security Notes

- ✅ No security concerns identified
- ✅ Temp audio files cleaned up in finally block
- ✅ No user input directly used in file paths

### Best-Practices and References

- [OpenAI Cookbook - Introduction to GPT-4o](https://cookbook.openai.com/examples/gpt4o/introduction_to_gpt4o) - Frame extraction pattern followed
- [OpenAI Whisper API](https://platform.openai.com/docs/guides/speech-to-text) - Audio transcription implementation

### Action Items

**Code Changes Required:**
(None - all requirements met)

**Advisory Notes:**
- Note: Consider adding `include_audio` as a camera-level or system setting for future configurability
- Note: The deprecation warning for `datetime.utcnow()` should be addressed in a future tech debt story
