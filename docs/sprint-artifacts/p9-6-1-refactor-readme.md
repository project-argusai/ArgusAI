# Story P9-6.1: Refactor README.md

Status: done

## Story

As a **new user or contributor**,
I want **the README to accurately reflect current features through Phase 8**,
So that **I understand what ArgusAI can do and how to get started**.

## Acceptance Criteria

1. **Given** I view the README, **When** I read the feature list, **Then** it includes all features through Phase 8:
   - UniFi Protect integration
   - Multi-frame video analysis
   - Entity recognition
   - Daily summaries
   - Push notifications
   - MQTT/Home Assistant
   - HomeKit integration
   - Phase 8 features: Frame gallery, adaptive sampling, AI prompt refinement, video storage

2. **Given** I want to install ArgusAI, **When** I follow the installation section, **Then** instructions match the current install script

3. **Given** I want to install ArgusAI, **When** I check prerequisites, **Then** Python 3.11+ and Node 18+ are listed

4. **Given** I view the README, **When** I look for troubleshooting, **Then** common issues are documented

5. **Given** I view the README, **When** I check documentation links, **Then** all links work correctly

## Tasks / Subtasks

- [x] Task 1: Review and update "What's New" section (AC: 1)
  - [x] Add Phase 8 features: Frame gallery, adaptive sampling, AI prompt refinement, video storage toggle
  - [x] Ensure Phase 9 completed features are mentioned if applicable (SSL/HTTPS, frame extraction improvements)

- [x] Task 2: Update Features section to include Phase 8 capabilities (AC: 1)
  - [x] Add Frame Gallery (stored analysis frames with modal viewer)
  - [x] Add Adaptive Frame Sampling (motion-based, similarity filtering)
  - [x] Add AI-Assisted Prompt Refinement
  - [x] Add Full Motion Video Download toggle
  - [x] Add Summary Feedback and custom prompts
  - [x] Add Entity Event List and management features
  - [x] Add SSL/HTTPS support

- [x] Task 3: Update Roadmap section (AC: 1)
  - [x] Mark Phase 8 as complete with accurate feature list
  - [x] Add Phase 9 progress if applicable

- [x] Task 4: Verify and update installation instructions (AC: 2, 3)
  - [x] Confirm install script references are accurate
  - [x] Verify prerequisites list is current
  - [x] Test that documented commands work

- [x] Task 5: Add/update troubleshooting section (AC: 4)
  - [x] Document SSL/HTTPS configuration issues
  - [x] Document common camera connection issues
  - [x] Document AI provider configuration issues

- [x] Task 6: Verify all documentation links work (AC: 5)
  - [x] Check all internal links to docs/ folder
  - [x] Check all external links
  - [x] Add any missing documentation references

- [x] Task 7: Final review and polish
  - [x] Proofread for consistency
  - [x] Ensure formatting is clean and scannable
  - [x] Verify architecture diagram is still accurate

## Dev Notes

### Current README Analysis

The existing README is well-structured and already covers Phases 1-7. Key updates needed:
- "What's New" section shows Phase 7 - needs Phase 8 features
- Roadmap shows Phase 7 complete - needs Phase 8 status
- Features section needs Phase 8/9 additions (frame gallery, adaptive sampling, prompt refinement, SSL)

### Phase 8 Features to Add

From `docs/epics-phase8.md` and completed sprint-status items:
1. **P8-1: Bug Fixes** - Re-analyse function, installation script, push notifications (internal fixes, not README-worthy)
2. **P8-2: Video Analysis Enhancements**
   - Store all analysis frames during event processing
   - Display analysis frames gallery on event cards
   - Configurable frame count setting (5, 10, 15, 20 frames)
   - Adaptive frame sampling (motion-based, similarity filtering)
   - Frame sampling strategy selection in settings
3. **P8-3: AI & Settings Improvements**
   - Hide MQTT form when integration disabled (UX, not feature)
   - Full motion video download toggle
   - AI-assisted prompt refinement

### Phase 9 Completed Features to Add

From sprint-status.yaml completed items:
1. **P9-1: Bug Fixes** - CI tests, push notifications, filter settings, prompt refinement fixes
2. **P9-2: Frame Capture & Video Analysis**
   - Frame capture timing optimization
   - Similarity-based frame filtering
   - Motion scoring for frame selection
   - Frame gallery modal
   - Frame sampling strategy setting
3. **P9-3: AI Context & Accuracy**
   - Camera and time context in AI prompts
   - Frame overlay text extraction attempt
   - Package false positive feedback
   - Summary feedback buttons
   - Summary prompt customization
   - Summary feedback in AI accuracy stats
4. **P9-4: Entity Management**
   - Vehicle entity separation by make/model
   - Entity event list view
   - Event-entity unlinking
   - Event-entity assignment
   - Entity merge
   - Manual adjustments stored for future matching
5. **P9-5: Infrastructure (partial)**
   - SSL/HTTPS support added

### Project Structure Notes

- README.md is at project root
- Documentation in `/docs` folder with organized sections
- Architecture diagram in README should match current system

### References

- [Source: docs/epics-phase8.md] - Phase 8 epic breakdown
- [Source: docs/epics-phase9.md] - Phase 9 epic breakdown
- [Source: docs/sprint-artifacts/sprint-status.yaml] - Story completion status
- [Source: docs/architecture.md] - System architecture
- [Source: docs/backlog.md#IMP-017] - Backlog item for README refactor

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p9-6-1-refactor-readme.context.xml

### Agent Model Used

Claude Opus 4.5

### Debug Log References

### Completion Notes List

- Updated "What's New" section with Phase 8 and Phase 9 features
- Added new AI Analysis features: Frame Gallery, Adaptive Sampling, Configurable Frame Count, AI Prompt Refinement, Context-Aware Prompts
- Added new Monitoring features: Summary Feedback
- Added new Entity Management features: Event List, Assignment, Merge, Vehicle Separation, Package False Positive Feedback
- Added new Event Management features: Frame Gallery Modal, Stored Analysis Frames, Full Video Storage
- Added new Security & Infrastructure section with SSL/HTTPS support
- Updated Roadmap with Phase 8 complete and Phase 9 in progress
- Added comprehensive Troubleshooting section
- Updated Environment Variables with SSL configuration
- Updated Documentation section with Phase 8 and Phase 9 PRD/Epics
- Updated test count from 2,250+ to 3,100+
- Verified all documentation links work

### File List

- README.md (modified)

---

## Change Log

| Date | Change |
|------|--------|
| 2025-12-23 | Story drafted from backlog item IMP-017 and Epic P9-6 |
| 2025-12-23 | Story implementation complete - README refactored with Phase 8/9 features |
