# Story 2.1.4: Validation and Documentation

Status: ready-for-dev

## Story

As a **QA engineer and future developer**,
I want **comprehensive validation of the motion detection system with sample footage and live cameras, plus documentation of testing procedures and results**,
So that **motion detection reliability is proven before Epic F3, and the validation workflow is repeatable for future epics**.

## Acceptance Criteria

**AC #1: Sample Footage Validation - All Three Algorithms**
- Given sample footage exists in `/samples` folder
- When QA tests all 3 motion algorithms (MOG2, KNN, Frame Diff)
- Then each algorithm is tested with:
  - 10+ video clips showing person entering from different angles (true positives)
  - 10+ clips showing non-motion scenarios (trees, rain, shadows, lights) (true negatives)
- And true positive rate is measured and documented (target: >90%)
- And false positive rate is measured and documented (target: <20%)
- And results are captured in validation report with per-algorithm breakdown

**AC #2: Live Camera Testing - USB and RTSP**
- Given at least one USB camera and one RTSP camera are available
- When QA performs manual testing with live camera feeds
- Then both camera types are tested with:
  - Motion detection enabled (all 3 algorithms)
  - Detection zones configured
  - Detection schedules active
  - Various sensitivity levels (low, medium, high)
- And camera brand/model information is documented
- And any configuration issues or limitations are noted
- And live testing results confirm motion detection works end-to-end

**AC #3: Performance and Quality Validation**
- Given motion detection is running with live cameras
- When QA measures system performance and event quality
- Then the following metrics are documented:
  - Frame processing time (<100ms target from architecture)
  - Motion detection latency (<5ms target)
  - Frame quality for AI analysis (resolution, compression, clarity)
  - False trigger scenarios (lighting changes, camera shake, etc.)
- And any performance issues are noted with reproduction steps

**AC #4: Tested Hardware Documentation**
- Given QA has tested various camera hardware
- When validation is complete
- Then a "Tested Hardware" document is created containing:
  - Tested USB camera brands/models with compatibility notes
  - Tested RTSP camera brands/models with stream URLs and authentication notes
  - Known working configurations (resolution, frame rate, codec)
  - Known issues or limitations per camera model
- And document is saved to `docs/tested-hardware.md`

**AC #5: Validation Workflow Documentation**
- Given QA has completed manual validation process
- When workflow documentation is needed for future epics
- Then a "Validation Workflow" document is created containing:
  - Step-by-step validation procedure
  - How to use sample footage for testing
  - How to test with live cameras
  - How to measure true/false positive rates
  - Expected results and acceptance thresholds
  - Troubleshooting common issues
- And document is saved to `docs/validation-workflow.md`
- And workflow is repeatable by any team member

**AC #6: Integration with Frontend UI**
- Given frontend UI now exists for motion detection (from F2.1-1, F2.1-2, F2.1-3)
- When QA performs end-to-end testing
- Then all UI components are tested with live cameras:
  - Motion sensitivity controls
  - Algorithm selection
  - Detection zone drawing
  - Detection schedule configuration
- And any UI/UX issues are documented
- And integration issues between frontend and backend are identified

## Tasks / Subtasks

**Task 1: Sample Footage Validation Setup** (AC: #1)
- [x] Inventory sample footage in `/samples` folder
- [ ] Categorize footage: true positives (people/motion) vs true negatives (false triggers) - **MANUAL: Review each video**
- [x] Create validation tracking spreadsheet or document
- [ ] Set up test environment (backend running, database clean state) - **MANUAL: Start backend/frontend**

**Task 2: Algorithm Testing with Sample Footage** (AC: #1, #3)
- [ ] Test MOG2 algorithm:
  - [ ] Run 10+ true positive clips, document detection rate
  - [ ] Run 10+ true negative clips, document false positive rate
  - [ ] Note algorithm-specific behaviors and edge cases
- [ ] Test KNN algorithm:
  - [ ] Run 10+ true positive clips, document detection rate
  - [ ] Run 10+ true negative clips, document false positive rate
  - [ ] Compare with MOG2 results
- [ ] Test Frame Diff algorithm:
  - [ ] Run 10+ true positive clips, document detection rate
  - [ ] Run 10+ true negative clips, document false positive rate
  - [ ] Compare with MOG2 and KNN results
- [ ] Calculate aggregate metrics:
  - [ ] True positive rate per algorithm (target >90%)
  - [ ] False positive rate per algorithm (target <20%)
  - [ ] Recommended algorithm based on results

**Task 3: Live Camera Testing - USB** (AC: #2, #3, #4)
- [ ] Test USB camera (brand/model: ___):
  - [ ] Verify camera detection and frame capture
  - [ ] Test motion detection with all 3 algorithms
  - [ ] Test detection zones (polygon drawing and filtering)
  - [ ] Test detection schedules (time-based activation)
  - [ ] Test sensitivity levels (low, medium, high)
  - [ ] Measure frame processing time
  - [ ] Document camera brand, model, resolution, frame rate
  - [ ] Note any compatibility issues or limitations

**Task 4: Live Camera Testing - RTSP** (AC: #2, #3, #4)
- [ ] Test RTSP camera (brand/model: ___):
  - [ ] Verify RTSP connection and authentication
  - [ ] Test motion detection with all 3 algorithms
  - [ ] Test detection zones
  - [ ] Test detection schedules
  - [ ] Test sensitivity levels
  - [ ] Measure frame processing time and latency
  - [ ] Document RTSP URL format, authentication, codec
  - [ ] Note any stream stability issues or reconnection behavior

**Task 5: End-to-End UI Integration Testing** (AC: #6)
- [ ] Test motion detection UI components (F2.1-1):
  - [ ] Verify sensitivity selector updates backend
  - [ ] Verify algorithm selector switches algorithms correctly
  - [ ] Verify cooldown configuration prevents rapid triggers
- [ ] Test detection zone drawing UI (F2.1-2):
  - [ ] Draw polygons on camera preview
  - [ ] Verify zones filter motion events correctly
  - [ ] Test zone enable/disable toggles
- [ ] Test detection schedule editor UI (F2.1-3):
  - [ ] Configure time ranges and day selections
  - [ ] Verify schedule activates/deactivates detection correctly
  - [ ] Test overnight schedules
  - [ ] Verify status indicator accuracy
- [ ] Document UI/UX issues or integration bugs

**Task 6: Performance and Quality Metrics** (AC: #3)
- [ ] Measure frame processing time across all algorithms
- [ ] Measure motion detection latency
- [ ] Assess frame quality for AI analysis (resolution, compression)
- [ ] Test edge cases:
  - [ ] Sudden lighting changes
  - [ ] Camera shake/vibration
  - [ ] Rapid movement vs slow movement
  - [ ] Multiple objects moving simultaneously
- [ ] Document performance baselines and edge case behavior

**Task 7: Create Tested Hardware Documentation** (AC: #4)
- [x] Create `docs/tested-hardware.md` document
- [ ] Document tested USB cameras: - **MANUAL: Fill in after testing**
  - [ ] Brand, model, chipset (if known)
  - [ ] Tested resolutions and frame rates
  - [ ] Driver requirements (if any)
  - [ ] Known issues or workarounds
- [ ] Document tested RTSP cameras: - **MANUAL: Fill in after testing**
  - [ ] Brand, model, firmware version
  - [ ] RTSP URL format and port
  - [ ] Authentication method
  - [ ] Codec and streaming settings
  - [ ] Known issues or limitations
- [ ] Add recommendations for compatible hardware - **MANUAL: Fill in after testing**

**Task 8: Create Validation Workflow Documentation** (AC: #5)
- [x] Create `docs/validation-workflow.md` document
- [x] Document validation procedure:
  - [x] Step-by-step sample footage testing
  - [x] Step-by-step live camera testing
  - [x] How to calculate true/false positive rates
  - [x] Expected results and acceptance thresholds
  - [x] Common troubleshooting steps
- [x] Include validation checklist template
- [x] Add references to tested hardware document
- [x] Review for completeness and clarity

**Task 9: Validation Report** (AC: #1, #2, #3)
- [x] Create `docs/motion-detection-validation-report.md`
- [ ] Compile results: - **MANUAL: Fill in after testing**
  - [ ] Algorithm comparison table (true positive rate, false positive rate)
  - [ ] USB camera test results
  - [ ] RTSP camera test results
  - [ ] Performance metrics summary
  - [ ] Edge cases and limitations
- [ ] Include recommendations: - **MANUAL: Fill in after testing**
  - [ ] Recommended algorithm for general use
  - [ ] Recommended sensitivity settings
  - [ ] Best practices for zone configuration
  - [ ] Best practices for schedule configuration
- [ ] Sign off with QA approval - **MANUAL: After all testing complete**

## Dev Notes

### Story Context

This story is **critical validation work** that was deferred from Epic F2. The Epic F2 Retrospective identified that motion detection was never validated with real cameras or sample footage, creating risk for Epic F3 (AI Description Generation) which depends on reliable motion events.

**Why This Matters:**
- Epic F3 will use motion events to trigger AI analysis (garbage in, garbage out)
- Frame quality and motion accuracy directly impact AI description quality
- Manual validation establishes baseline quality before building dependent features
- Validation workflow becomes standard process for future camera/detection features

### Dependencies

**Prerequisites (MUST be complete before starting):**
- ✅ F2.1-1: Motion Detection UI Components (done)
- ✅ F2.1-2: Detection Zone Drawing UI (done)
- ✅ F2.1-3: Detection Schedule Editor UI (done)
- ⚠️ Hardware: USB camera and RTSP camera must be available for testing
- ⚠️ Sample footage: `/samples` folder must contain test video clips

**Blocking:**
- Epic F3 (AI Description Generation) is **BLOCKED** until this validation story is complete

### Technical Approach

**This is a QA/validation story, not a coding story.** The work involves:
1. Manual testing with sample footage and live cameras
2. Measuring quantitative metrics (true/false positive rates, latency)
3. Documenting findings and creating repeatable workflows

**Expected Artifacts:**
- `docs/tested-hardware.md` - Hardware compatibility documentation
- `docs/validation-workflow.md` - Repeatable validation procedure
- `docs/motion-detection-validation-report.md` - Validation results and findings

**Tools/Setup:**
- Backend running (`uvicorn app.main:app --reload`)
- Frontend running (`npm run dev`)
- Database in clean state for testing
- Sample footage accessible
- USB and RTSP cameras connected and configured

### Sample Footage Location

**Expected Location:** `/samples/` folder in project root (to be confirmed during Task 1)

**Footage Categories Needed:**
- **True Positives:** People entering frame, walking, standing still, multiple people
- **True Negatives:** Trees swaying, rain, shadows, car headlights, lighting changes

If sample footage is missing or insufficient, create GitHub issue to obtain additional test videos.

### Algorithm Comparison (from Architecture)

**From architecture.md:**
- **MOG2:** Default, adaptive background subtraction, good general-purpose
- **KNN:** K-nearest neighbors, more sensitive to small movements
- **Frame Diff:** Simple frame differencing, fast but less accurate

Expected outcome: MOG2 likely performs best overall, but validation will confirm.

### Performance Targets (from Architecture)

- **Frame Processing:** <100ms per frame
- **Motion Detection:** <5ms per frame (MOG2)
- **End-to-End Latency:** <5 seconds from motion to AI description (Epic F3 target)

### Learnings from Previous Story (F2.1-3)

**From Story f2-1-3-detection-schedule-editor-ui (Status: done)**

**Critical Backend Fix Applied:**
- Backend `CameraUpdate` schema was missing `detection_zones` and `detection_schedule` fields
- Fixed in `backend/app/schemas/camera.py:93-156` with Pydantic serialization/deserialization validators
- **Impact for This Story:** Detection zones and schedules now persist correctly - can be used confidently during live testing

**Frontend Patterns Established:**
- React Hook Form + Zod validation pattern proven effective
- shadcn/ui components provide consistent UX (Card, Input, Button, Tooltip)
- Custom toggle switches follow established motion_enabled pattern
- Null-safe handling for optional configuration fields

**Files Modified in F2.1-3 (may need reference during testing):**
- `frontend/components/cameras/DetectionScheduleEditor.tsx` (352 lines)
- `frontend/types/camera.ts` - IDetectionSchedule interface
- `frontend/lib/validations/camera.ts` - detectionScheduleSchema
- `frontend/components/cameras/CameraForm.tsx` - Schedule integration
- `backend/app/schemas/camera.py` - CameraUpdate and CameraResponse schemas with validators

**Testing Focus for This Story:**
- Verify detection schedule activates/deactivates correctly during live testing
- Confirm overnight schedules work (e.g., 22:00 - 06:00 crossing midnight)
- Test zone filtering with detection schedule enabled
- Validate UI components work with real camera feeds (not just mock data)

[Source: docs/sprint-artifacts/f2-1-3-detection-schedule-editor-ui.md#Dev-Agent-Record]

### References

- [Epic F2 Retrospective](../epic-f2-retrospective.md) - Source of F2.1 story requirements
- [Architecture](../architecture.md) - Performance targets and algorithm details
- [Tech Spec Epic F2](./tech-spec-epic-f2.md) - Motion detection technical specification
- [Story F2.1-3](./f2-1-3-detection-schedule-editor-ui.md) - Previous story with backend schema fixes

## Dev Agent Record

### Context Reference

**Story Context XML:** [f2-1-4-validation-and-documentation.context.xml](./f2-1-4-validation-and-documentation.context.xml)

Generated: 2025-11-16 by story-context workflow

### Agent Model Used

**Model:** Claude Sonnet 4.5 (claude-sonnet-4-5-20250929)
**Date:** 2025-11-16

### Debug Log References

**Story Type:** QA/Validation Story (Manual Testing Required)

This story differs from typical implementation stories in that it requires manual testing with physical hardware (USB cameras, RTSP cameras) and sample footage. The dev agent has prepared all documentation templates and validation tracking structures, but the actual testing must be performed manually.

**Approach:**
1. Analyzed story type and identified manual testing requirements
2. Checked for sample footage availability (5 MP4 files found in `/samples/`)
3. Created comprehensive validation tracking document with tables for all test scenarios
4. Created three required documentation templates (tested-hardware.md, validation-workflow.md, validation-report.md)
5. Marked preparation tasks as complete, leaving manual execution tasks for QA engineer

**Decision:** Per user request (Option A), created all templates and tracking structures, marking them as "prepared - awaiting manual execution" rather than attempting to simulate test results.

### Completion Notes List

**2025-11-16 - Documentation Templates Created:**

✅ **Created: `docs/validation-tracking.md`** (comprehensive tracking spreadsheet)
- Sample footage inventory table (5 videos catalogued)
- Algorithm testing tables for MOG2, KNN, Frame Diff
- True positive/false positive tracking tables (10+ rows each)
- Live camera testing checklists (USB + RTSP)
- UI integration testing checklists
- Performance metrics tables
- Edge case testing section
- Ready for QA engineer to fill in during manual testing

✅ **Created: `docs/tested-hardware.md`** (hardware compatibility template)
- USB camera documentation template with full specifications table
- RTSP camera documentation template with connection details
- Configuration recommendations section
- Performance metrics tables
- Compatibility rating system
- Troubleshooting guides
- Summary tables for tested cameras
- Ready for QA engineer to document actual tested hardware

✅ **Created: `docs/validation-workflow.md`** (repeatable validation procedure)
- Complete 7-phase validation workflow
- Step-by-step instructions for sample footage testing
- Step-by-step instructions for live camera testing (USB + RTSP)
- UI integration testing procedures
- Performance measurement guidelines
- Expected results and acceptance thresholds
- Troubleshooting common issues
- Success criteria checklist
- Fully complete and ready for use

✅ **Created: `docs/motion-detection-validation-report.md`** (final report template)
- Executive summary section with key findings
- Algorithm comparison tables
- Sample footage validation results section
- Live camera testing results section
- Performance and quality metrics section
- UI integration testing results section
- Recommendations section
- Sign-off section with QA approval
- Ready for QA engineer to fill in actual test results

**Sample Footage Inventory:**
- Confirmed `/samples/` folder exists
- Found 5 MP4 video files:
  - 2x Back Door footage (~6-7 seconds each)
  - 3x Driveway footage (~9s, 2m27s, ~15s)
- Total footage: ~180 seconds
- Note: May need additional footage to reach 10+ TP and 10+ TN clips per algorithm
- Documented in validation-tracking.md for categorization by QA

**Tasks Remaining (Manual Execution Required):**
- Task 2: Algorithm Testing with Sample Footage (manual)
- Task 3: Live Camera Testing - USB (manual)
- Task 4: Live Camera Testing - RTSP (manual)
- Task 5: End-to-End UI Integration Testing (manual)
- Task 6: Performance and Quality Metrics (manual)
- Task 7: Fill in tested hardware documentation (manual)
- Task 9: Fill in validation report with results (manual)

**Next Steps for QA Engineer:**
1. Review validation-workflow.md for complete testing procedure
2. Use validation-tracking.md to record all test results
3. Execute manual testing phases 1-6 following the workflow
4. Transfer results to tested-hardware.md and validation-report.md
5. Sign off validation report when complete
6. Mark remaining tasks complete in this story file

### File List

**Files Created:**
- `docs/validation-tracking.md` - Comprehensive validation tracking spreadsheet with tables for all test scenarios
- `docs/tested-hardware.md` - Hardware compatibility documentation template (152 lines)
- `docs/validation-workflow.md` - Repeatable validation procedure with 7 phases (582 lines)
- `docs/motion-detection-validation-report.md` - Final validation report template (544 lines)

**Files Modified:**
- `docs/sprint-artifacts/f2-1-4-validation-and-documentation.md` - Updated task checkboxes and added completion notes
- `docs/sprint-artifacts/sprint-status.yaml` - Story status: ready-for-dev → in-progress

---

## Change Log

- 2025-11-16: Story drafted by SM agent (create-story workflow) from Epic F2.1 retrospective definition
- 2025-11-16: Story context XML generated by story-context workflow
- 2025-11-16: Documentation templates created by dev agent (dev-story workflow)
  - Created validation-tracking.md, tested-hardware.md, validation-workflow.md, validation-report.md
  - Inventoried sample footage (5 MP4 files in `/samples/`)
  - Marked preparation tasks complete, manual testing tasks ready for QA execution
