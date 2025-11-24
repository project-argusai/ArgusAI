# Motion Detection Validation Workflow

**Project:** Live Object AI Classifier
**Last Updated:** 2025-11-16
**Story:** F2.1-4 - Validation and Documentation
**Version:** 1.0

---

## Overview

This document provides a comprehensive, step-by-step procedure for validating the motion detection system in the Live Object AI Classifier. This workflow ensures consistent testing methodology and repeatable results for current and future validation efforts.

**Purpose:**
- Validate motion detection accuracy and reliability
- Measure system performance and quality metrics
- Document camera hardware compatibility
- Establish baseline quality standards before Epic F3 (AI Description Generation)

**Audience:**
- QA Engineers
- Developers
- System Administrators
- Future team members validating new features

---

## Prerequisites

### Required Hardware

- [ ] **USB Camera** (at least one)
  - Recommended: Built-in webcam or USB webcam
  - Check [tested-hardware.md](./tested-hardware.md) for compatible models

- [ ] **RTSP Network Camera** (at least one)
  - Recommended: IP security camera with RTSP support
  - Check [tested-hardware.md](./tested-hardware.md) for compatible models

- [ ] **Computer for Testing**
  - macOS (M1/Intel) or Linux (Ubuntu 22.04+)
  - Minimum 4GB RAM, 2-core CPU
  - Python 3.11+ installed
  - Node.js 18+ installed

### Required Software

- [ ] **Project Repository Cloned**
  ```bash
  git clone [repository-url]
  cd live-object-ai-classifier
  ```

- [ ] **Backend Dependencies Installed**
  ```bash
  cd backend
  python -m venv venv
  source venv/bin/activate  # On Windows: venv\Scripts\activate
  pip install -r requirements.txt
  ```

- [ ] **Frontend Dependencies Installed**
  ```bash
  cd frontend
  npm install
  ```

- [ ] **Database Setup Complete**
  ```bash
  cd backend
  alembic upgrade head
  ```

### Required Test Data

- [ ] **Sample Footage** in `/samples/` folder
  - Minimum 10 "true positive" clips (people/motion)
  - Minimum 10 "true negative" clips (false triggers: trees, rain, shadows)
  - If insufficient footage, obtain additional test videos

- [ ] **Validation Tracking Document**
  - Use [validation-tracking.md](./validation-tracking.md) template
  - Create copy for current validation session

---

## Validation Workflow

### Phase 1: Environment Setup

#### Step 1.1: Start Backend Server

```bash
cd backend
source venv/bin/activate  # On Windows: venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```

**Verify:**
- Server starts successfully
- Navigate to http://localhost:8000/docs
- API documentation loads (FastAPI Swagger UI)

#### Step 1.2: Start Frontend Server

```bash
cd frontend
npm run dev
```

**Verify:**
- Server starts successfully (usually port 3000)
- Navigate to http://localhost:3000
- Application loads

#### Step 1.3: Prepare Clean Database

```bash
cd backend
# Optional: Reset database for clean test
# WARNING: This deletes all existing data!
rm instance/app.db  # Or your database file
alembic upgrade head
```

**Verify:**
- Database is empty (no cameras, no motion events)
- Fresh start for accurate testing

#### Step 1.4: Inventory Sample Footage

1. Navigate to `/samples/` folder
2. Review all video files
3. Categorize each video:
   - **True Positive (TP):** Contains person/vehicle motion that SHOULD trigger detection
   - **True Negative (TN):** Contains non-relevant motion that should NOT trigger detection
4. Document in validation tracking spreadsheet

**Expected Categories:**
- TP: People walking, entering frame, vehicles moving
- TN: Trees swaying, rain, shadows, car headlights, gradual lighting changes

**Action if Insufficient:**
- Create GitHub issue requesting additional test footage
- Specify what scenarios are missing (e.g., "Need 10 TN clips with rain/shadows")

---

### Phase 2: Sample Footage Validation

This phase tests all three motion detection algorithms against pre-recorded footage to measure accuracy.

#### Step 2.1: Configure Test Camera for Footage Playback

**Note:** You'll need to use a camera pointed at a screen playing the sample footage, OR configure the system to accept video files directly (if supported).

**Option A: Screen Playback Method**
1. Open sample video in media player (VLC, QuickTime, etc.)
2. Position USB camera to capture screen
3. Add camera to system via frontend UI
4. Verify frame capture shows video playback

**Option B: Direct File Input** (if implemented)
1. Use backend API to configure camera with file path
2. Verify system can read video file frames

#### Step 2.2: Test MOG2 Algorithm

**Configuration:**
- Algorithm: MOG2
- Sensitivity: Medium
- Cooldown: 30 seconds
- Detection Zones: None (full frame)
- Detection Schedule: Disabled (always active)

**True Positive Testing (Target: 10+ clips, >90% detection rate):**

For each TP video clip:
1. Start video playback
2. Observe motion detection system
3. Record in tracking sheet:
   - ☑ Motion detected? (Yes/No)
   - Confidence score
   - Latency (time from motion to detection)
   - Bounding box coordinates
   - Notes (any unusual behavior)

**Calculate:** True Positive Rate = (Detections / Total TP clips) × 100%
**Target:** >90%

**True Negative Testing (Target: 10+ clips, <20% false positive rate):**

For each TN video clip:
1. Start video playback
2. Observe motion detection system
3. Record in tracking sheet:
   - ☑ Motion detected? (Yes/No - should be No!)
   - If detected (false positive): Confidence score, trigger type
   - Notes

**Calculate:** False Positive Rate = (False detections / Total TN clips) × 100%
**Target:** <20%

**Algorithm-Specific Observations:**
- Document any MOG2-specific behaviors
- Note edge cases or unusual patterns
- Record average processing time

#### Step 2.3: Test KNN Algorithm

**Repeat Step 2.2 with KNN algorithm:**
- Change algorithm to KNN via frontend UI
- Keep all other settings identical
- Test same TP and TN video clips
- Record results in separate section of tracking sheet

**Comparison with MOG2:**
- Compare true positive rates
- Compare false positive rates
- Note differences in detection behavior
- Identify scenarios where KNN performs better/worse

#### Step 2.4: Test Frame Diff Algorithm

**Repeat Step 2.2 with Frame Diff algorithm:**
- Change algorithm to Frame Diff via frontend UI
- Keep all other settings identical
- Test same TP and TN video clips
- Record results in separate section of tracking sheet

**Comparison with MOG2 and KNN:**
- Compare all three algorithms
- Identify strengths/weaknesses of each
- Note processing speed differences

#### Step 2.5: Calculate Aggregate Metrics

Create summary table:

| Algorithm | True Positive Rate | False Positive Rate | Avg Processing Time | Pass/Fail |
|-----------|-------------------|---------------------|---------------------|-----------|
| MOG2 | ___% | ___% | ___ ms | ☐ Pass ☐ Fail |
| KNN | ___% | ___% | ___ ms | ☐ Pass ☐ Fail |
| Frame Diff | ___% | ___% | ___ ms | ☐ Pass ☐ Fail |

**Thresholds:**
- True Positive Rate: >90% = Pass
- False Positive Rate: <20% = Pass
- Processing Time: <100ms = Pass

**Determine Recommended Algorithm:**
- Best overall accuracy
- Acceptable performance
- Suitable for general use cases

---

### Phase 3: Live Camera Testing - USB

This phase validates motion detection with real-time camera feeds.

#### Step 3.1: Connect USB Camera

1. Plug in USB camera
2. Verify camera is detected by operating system
   - macOS: System Preferences → Camera
   - Linux: `ls /dev/video*`
   - Windows: Device Manager

#### Step 3.2: Add Camera to System

1. Navigate to frontend UI (http://localhost:3000)
2. Click "Add Camera" button
3. Fill in configuration:
   - Name: "USB Test Camera"
   - Type: USB
   - Device Index: 0 (or appropriate index)
   - Frame Rate: 5 FPS (start with low value)
   - Enabled: Yes
4. Save camera
5. Verify: Frame preview loads in UI

#### Step 3.3: Test Motion Detection - All Algorithms

**For each algorithm (MOG2, KNN, Frame Diff):**

1. **Configure Algorithm:**
   - Edit camera settings
   - Select algorithm
   - Sensitivity: Medium
   - Cooldown: 30 seconds
   - Save

2. **Perform Live Motion Test:**
   - Walk in front of camera
   - Observe motion event creation
   - Check database for event record
   - Verify thumbnail captured

3. **Record Results:**
   - ☑ Motion detected? (Yes/No)
   - Confidence score
   - Bounding box accuracy
   - Thumbnail quality
   - Processing latency

4. **Test Different Sensitivity Levels:**
   - Low: Fewer detections (reduce false positives)
   - Medium: Balanced (default)
   - High: More sensitive (catch all movement)

5. **Document:** Record all observations in tracking sheet

#### Step 3.4: Test Detection Zones

1. **Draw Detection Zone:**
   - Edit camera settings
   - Navigate to "Detection Zones" section
   - Click "Draw Custom Polygon"
   - Click to add 4-6 vertices defining a zone
   - Double-click to close polygon
   - Name zone: "Test Zone 1"
   - Save

2. **Verify Zone Filtering:**
   - Walk inside zone → Should trigger motion event
   - Walk outside zone → Should NOT trigger motion event
   - Record results in tracking sheet

3. **Test Zone Enable/Disable:**
   - Disable zone via toggle
   - Walk inside zone area → Should trigger (zone ignored)
   - Re-enable zone
   - Walk inside zone → Should trigger again

4. **Test Multiple Zones:**
   - Create 2-3 zones covering different areas
   - Test motion in each zone
   - Verify correct zone filtering

#### Step 3.5: Test Detection Schedules

1. **Configure Weekday Schedule (9am-5pm):**
   - Edit camera settings
   - Navigate to "Detection Schedule" section
   - Enable schedule
   - Start Time: 09:00
   - End Time: 17:00
   - Days: Monday, Tuesday, Wednesday, Thursday, Friday
   - Save

2. **Verify Schedule Activation:**
   - If current time is within 9am-5pm on weekday:
     - Expect: Motion detection active
     - Test: Walk in front of camera → Event created
   - If current time is outside 9am-5pm or weekend:
     - Expect: Motion detection inactive
     - Test: Walk in front of camera → No event created

3. **Test Overnight Schedule (10pm-6am):**
   - Edit schedule:
     - Start Time: 22:00
     - End Time: 06:00
   - Verify overnight crossing midnight is handled correctly
   - Test at different times (before 10pm, after 10pm, before 6am, after 6am)

4. **Verify Status Indicator:**
   - Check UI schedule status indicator
   - Should show: "Active Now" or "Inactive (Outside Schedule)"

#### Step 3.6: Measure Performance

1. **Frame Processing Time:**
   - Check backend logs for frame processing latency
   - Record min, max, average across 100+ frames
   - Target: <100ms P95

2. **Motion Detection Latency:**
   - Measure time from motion start to event creation
   - Target: <5ms

3. **CPU and Memory Usage:**
   - Monitor system resources during operation
   - Record CPU % and memory usage
   - Note if performance degrades over time

#### Step 3.7: Document Camera Details

Record in tracking sheet and [tested-hardware.md](./tested-hardware.md):
- Brand and model
- Chipset (if known)
- Tested resolution
- Tested frame rate
- Driver requirements
- Compatibility notes
- Known issues
- Recommended configuration

---

### Phase 4: Live Camera Testing - RTSP

This phase validates RTSP network camera integration.

#### Step 4.1: Connect RTSP Camera

1. **Ensure Camera is on Network:**
   - Connect via Ethernet or Wi-Fi
   - Determine camera IP address
   - Ping camera: `ping [camera_ip]`

2. **Access Camera Web Interface:**
   - Open browser: `http://[camera_ip]`
   - Login with credentials
   - Verify RTSP is enabled
   - Note RTSP URL format

3. **Test RTSP Stream with VLC:**
   ```bash
   vlc rtsp://[username]:[password]@[ip]:554/[stream_path]
   ```
   - Verify stream loads successfully
   - This confirms RTSP is working before testing with system

#### Step 4.2: Add RTSP Camera to System

1. Navigate to frontend UI
2. Click "Add Camera"
3. Fill in configuration:
   - Name: "RTSP Test Camera"
   - Type: RTSP
   - RTSP URL: `rtsp://[username]:[password]@[ip]:554/[stream_path]`
   - Username: [camera username]
   - Password: [camera password]
   - Frame Rate: 5 FPS
   - Enabled: Yes
4. Save camera
5. Verify: Frame preview loads in UI

**Troubleshooting if Connection Fails:**
- Verify RTSP URL format
- Check username/password
- Confirm camera RTSP is enabled
- Test with VLC again
- Check firewall rules

#### Step 4.3: Test Motion Detection - All Algorithms

**Repeat Step 3.3 (USB testing) with RTSP camera:**
- Test MOG2, KNN, Frame Diff algorithms
- Test different sensitivity levels
- Document results

**Additional RTSP-Specific Tests:**
- Stream quality assessment
- Network latency measurement
- Codec verification (H.264, H.265, MJPEG)

#### Step 4.4: Test Stream Stability

1. **Continuous Operation Test:**
   - Leave camera running for 1+ hours
   - Monitor for disconnections
   - Record disconnect events and times

2. **Network Interruption Test:**
   - Temporarily disconnect camera from network
   - Reconnect after 10-30 seconds
   - Verify system reconnects automatically
   - Record reconnection time

3. **Record Stability Metrics:**
   - Uptime percentage
   - Number of disconnections
   - Average reconnection time
   - Reconnection success rate

#### Step 4.5: Document Camera Details

Record in tracking sheet and [tested-hardware.md](./tested-hardware.md):
- Brand, model, firmware version
- RTSP URL format
- Authentication method
- Port number
- Codec and streaming settings
- Resolution and frame rate
- Stream stability results
- Known issues
- Recommended configuration

---

### Phase 5: End-to-End UI Integration Testing

This phase validates frontend UI components work correctly with live cameras.

#### Step 5.1: Test Motion Detection UI Components (F2.1-1)

1. **Sensitivity Selector:**
   - Edit camera → Change sensitivity: Low → Medium → High
   - Save and verify backend API call succeeds
   - Perform live motion test at each level
   - Confirm behavior changes (High = more sensitive, Low = less sensitive)

2. **Algorithm Selector:**
   - Edit camera → Change algorithm: MOG2 → KNN → Frame Diff
   - Save and verify backend API call succeeds
   - Perform live motion test with each algorithm
   - Confirm algorithm actually changes (different detection behavior)

3. **Cooldown Configuration:**
   - Edit camera → Set cooldown: 5s, 30s, 60s
   - Save
   - Trigger multiple motion events rapidly
   - Verify events are spaced by cooldown period in database

**Document UI/UX Issues:**
- Any bugs or unexpected behavior
- Confusing UI elements
- Missing validation
- Error messages unclear

#### Step 5.2: Test Detection Zone Drawing UI (F2.1-2)

1. **Polygon Drawing:**
   - Edit camera → Detection Zones → "Draw Custom Polygon"
   - Draw 3-vertex triangle → Verify polygon closes correctly
   - Draw 4-vertex rectangle → Verify polygon closes correctly
   - Draw 6+ vertex complex shape → Verify works
   - Double-click to close → Verify works

2. **Zone Management:**
   - Create 2-3 zones
   - Edit zone name → Save → Verify persists
   - Disable zone → Verify toggle works
   - Delete zone → Confirm dialog → Verify removed

3. **Zone Filtering:**
   - Create zone covering left half of camera view
   - Perform motion in left half → Should trigger
   - Perform motion in right half → Should NOT trigger
   - Verify zone filtering works correctly

**Document UI/UX Issues:**
- Zone drawing difficulties
- Polygon rendering issues
- Zone management bugs

#### Step 5.3: Test Detection Schedule Editor UI (F2.1-3)

1. **Time Range Configuration:**
   - Edit camera → Detection Schedule → Enable
   - Set Start Time: 09:00
   - Set End Time: 17:00
   - Save → Verify times persist to backend

2. **Day Selection:**
   - Select weekdays (Mon-Fri)
   - Save → Verify days persist to backend
   - Verify selected days highlighted in UI

3. **Schedule Activation:**
   - If within schedule window: Perform motion → Should trigger
   - If outside schedule window: Perform motion → Should NOT trigger
   - Verify schedule status indicator shows correct state

4. **Overnight Schedule:**
   - Set schedule: 22:00 - 06:00
   - Verify UI shows "(Overnight)" warning
   - Test at different times to confirm midnight crossing works

**Document UI/UX Issues:**
- Schedule configuration problems
- Status indicator inaccuracies
- Overnight schedule bugs

---

### Phase 6: Performance and Quality Validation

#### Step 6.1: Measure Frame Processing Performance

1. **Collect Metrics:**
   - Run camera with motion detection for 5+ minutes
   - Check backend logs for frame processing times
   - Calculate: Min, Max, Average, P95, P99

2. **Test Each Algorithm:**
   - MOG2 processing time
   - KNN processing time
   - Frame Diff processing time

3. **Verify Targets:**
   - Target: <100ms P95
   - Pass/Fail for each algorithm

#### Step 6.2: Assess Frame Quality for AI Analysis

1. **Check Captured Frames:**
   - View motion event thumbnails
   - Assess resolution (is it sufficient for AI?)
   - Check compression artifacts (is quality acceptable?)
   - Evaluate clarity (can objects be clearly identified?)

2. **Rate Quality:**
   - ☐ Excellent - Perfect for AI analysis
   - ☐ Good - Acceptable for AI analysis
   - ☐ Fair - May have issues with AI analysis
   - ☐ Poor - Not suitable for AI analysis

#### Step 6.3: Test Edge Cases

1. **Lighting Changes:**
   - Turn lights on/off rapidly
   - Record: False positives? How many?
   - Gradual lighting change (open/close blinds slowly)
   - Record: False positives?

2. **Camera Shake/Vibration:**
   - Gently shake camera or tap desk
   - Record: False positives?
   - System recovery time?

3. **Motion Patterns:**
   - Rapid movement (run in front of camera)
   - Slow movement (walk very slowly)
   - Multiple people moving simultaneously
   - Record detection accuracy for each

**Document:**
- Edge case scenarios tested
- System behavior for each
- False positive rates
- Recovery times

---

### Phase 7: Documentation Creation

#### Step 7.1: Complete Tested Hardware Documentation

1. Transfer camera details from tracking sheet to [tested-hardware.md](./tested-hardware.md)
2. Fill in all tested configurations
3. Document compatibility notes
4. Add performance metrics
5. Include recommendations

#### Step 7.2: Create Validation Report

1. Create [motion-detection-validation-report.md](./motion-detection-validation-report.md)
2. Compile results:
   - Algorithm comparison table
   - USB camera test results
   - RTSP camera test results
   - Performance metrics summary
   - Edge cases and limitations
3. Include recommendations:
   - Recommended algorithm for general use
   - Recommended sensitivity settings
   - Best practices for zone configuration
   - Best practices for schedule configuration
4. Add QA sign-off

#### Step 7.3: Review and Finalize

1. Review all documentation for completeness
2. Ensure all tracking sheet data is transferred to final reports
3. Verify all acceptance criteria are met
4. Get sign-off from QA lead or project manager

---

## Expected Results and Acceptance Thresholds

### Motion Detection Accuracy

| Metric | Target | Status |
|--------|--------|--------|
| True Positive Rate | >90% | ☐ Pass ☐ Fail |
| False Positive Rate | <20% | ☐ Pass ☐ Fail |

### Performance

| Metric | Target | Status |
|--------|--------|--------|
| Frame Processing Time (P95) | <100ms | ☐ Pass ☐ Fail |
| Motion Detection Latency | <5ms | ☐ Pass ☐ Fail |

### Quality

| Metric | Target | Status |
|--------|--------|--------|
| Frame Quality for AI Analysis | Good or Better | ☐ Pass ☐ Fail |
| Stream Stability (RTSP) | >99% uptime | ☐ Pass ☐ Fail |

---

## Troubleshooting Common Issues

### Issue: Backend won't start

**Symptoms:** `uvicorn` command fails or exits with error

**Solutions:**
1. Check Python virtual environment is activated
2. Verify dependencies installed: `pip install -r requirements.txt`
3. Check database exists: `alembic upgrade head`
4. Check port 8000 not already in use: `lsof -i :8000`

### Issue: Frontend won't start

**Symptoms:** `npm run dev` fails or exits with error

**Solutions:**
1. Verify Node.js installed: `node --version`
2. Install dependencies: `npm install`
3. Check port 3000 not already in use: `lsof -i :3000`
4. Clear cache: `rm -rf .next && npm run dev`

### Issue: USB camera not detected

**Symptoms:** Camera not showing in device list

**Solutions:**
1. Verify camera is plugged in
2. Try different USB port
3. Check system recognizes camera:
   - macOS: System Preferences → Camera
   - Linux: `ls /dev/video*`
4. Install camera drivers if needed
5. Restart computer

### Issue: RTSP stream won't connect

**Symptoms:** "Connection failed" error when adding RTSP camera

**Solutions:**
1. Verify RTSP URL format: `rtsp://user:pass@ip:port/path`
2. Test with VLC: `vlc rtsp://...`
3. Check camera RTSP settings (enabled?)
4. Ping camera IP: `ping [camera_ip]`
5. Check firewall rules
6. Verify username/password correct

### Issue: Motion detection not triggering

**Symptoms:** Motion visible in preview but no events created

**Solutions:**
1. Check motion detection enabled for camera
2. Verify detection schedule (if enabled) is active now
3. Check detection zones (if configured) cover motion area
4. Check cooldown period hasn't expired yet
5. Try different sensitivity level (increase to High)
6. Check backend logs for errors

### Issue: High CPU usage

**Symptoms:** System becomes slow during testing

**Solutions:**
1. Reduce camera frame rate (try 5 FPS)
2. Reduce camera resolution (try 640x480)
3. Use Frame Diff algorithm (fastest)
4. Disable unused cameras
5. Close other applications

---

## Success Criteria

This validation is considered **COMPLETE** when:

- [ ] All 9 tasks in story F2.1-4 are marked complete
- [ ] All 6 acceptance criteria are satisfied:
  - [ ] AC #1: Sample Footage Validation (all 3 algorithms tested, metrics documented)
  - [ ] AC #2: Live Camera Testing (USB + RTSP tested)
  - [ ] AC #3: Performance and Quality Validation (metrics meet targets)
  - [ ] AC #4: Tested Hardware Documentation (completed)
  - [ ] AC #5: Validation Workflow Documentation (this document)
  - [ ] AC #6: UI Integration Testing (all UI components tested)
- [ ] True Positive Rate >90% for at least one algorithm
- [ ] False Positive Rate <20% for at least one algorithm
- [ ] Frame processing time <100ms (P95)
- [ ] At least one USB camera fully tested and documented
- [ ] At least one RTSP camera fully tested and documented
- [ ] Final validation report completed and signed off

**If Criteria Not Met:**
- Document reasons why targets not achieved
- Identify blocking issues
- Create follow-up stories to address gaps
- Note limitations in validation report

---

## Tips for Future Validations

1. **Prepare Sample Footage in Advance:**
   - Collect diverse test scenarios before starting
   - Ensure good mix of TP and TN clips
   - Label files clearly (e.g., `TP-person-walking.mp4`, `TN-tree-wind.mp4`)

2. **Use Automation Where Possible:**
   - Consider scripts to run multiple footage tests automatically
   - Log all results to CSV for easy analysis
   - Automate performance metric collection

3. **Document Everything:**
   - Take screenshots of issues
   - Record exact steps to reproduce problems
   - Note software versions, camera models, settings

4. **Test Incrementally:**
   - Don't try to test everything at once
   - Complete one phase fully before moving to next
   - Easier to isolate issues this way

5. **Involve Stakeholders:**
   - Demo findings to team during validation
   - Get early feedback on results
   - Adjust testing approach if needed

---

## Document History

| Date | Author | Changes |
|------|--------|---------|
| 2025-11-16 | [Name] | Initial template created for F2.1-4 validation |
| | | |

---

**End of Document**
