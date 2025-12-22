# ArgusAI Phase 9 - Product Requirements Document
## AI Accuracy, Stability & Developer Experience

**Author:** Brent
**Date:** 2025-12-22
**Version:** 1.0
**Phase:** 9

---

## Executive Summary

Phase 9 focuses on three strategic pillars: **stability and bug fixes** to address accumulated issues, **AI accuracy improvements** through enhanced context and feedback loops, and **developer experience** through automated pipelines and documentation. This phase consolidates the platform by fixing critical bugs while laying groundwork for intelligent, self-improving AI analysis.

### What Makes This Special

**Self-Improving AI System** - Phase 9 introduces feedback loops, manual entity corrections, and contextual prompts that make the AI smarter over time. User corrections train better entity recognition. Camera context and time-of-day awareness produce more relevant descriptions.

**Frame Capture Intelligence** - Fixing timing issues and adding adaptive frame sampling ensures the AI analyzes the right moments, not empty frames before or after the action.

**Automated Development Pipeline** - n8n integration creates a 24/7 development capability with AI-assisted coding, testing, and refinement coordinated through BMAD workflows.

---

## Project Classification

**Technical Type:** Web Application + AI/ML + Smart Home Integration
**Domain:** Home Security / Smart Home (General - Low Complexity)
**Complexity:** Medium-High

**Phase 9 Classification:**
- **Primary Focus:** Bug Fixes & Stability (P1/P2 bugs)
- **Secondary Focus:** AI Accuracy & Context (prompts, feedback, entities)
- **Tertiary Focus:** Developer Experience (automation, documentation)

---

## Success Criteria

### Stability Success
- **All P1 bugs resolved** - CI pipeline green, no blocking issues
- **All P2 bugs resolved** - Push notifications reliable, filter settings persist, re-analyse works
- **Zero regression** - Existing functionality continues working

### AI Accuracy Success
- **Frame timing fixed** - Captured frames show actual activity that triggered events
- **Context-aware descriptions** - AI knows camera name and time of day
- **Entity separation working** - Different vehicles create distinct entities
- **Feedback loop functional** - User corrections stored and influence future analysis

### Developer Experience Success
- **n8n pipeline operational** - Automated story creation through deployment
- **README reflects reality** - Documentation matches current features
- **GitHub Pages live** - Public documentation site deployed

---

## Product Scope

### Phase 9 MVP - Core Deliverables

**Epic P9-1: Critical Bug Fixes** (Priority: P1)
- Fix GitHub Actions CI tests failing (BUG-010)
- Fix push notifications only working once (BUG-007)
- Fix Protect camera filter settings not persisting (BUG-008)
- Fix re-analyse function returning error (BUG-005)
- Fix AI-assisted prompt refinement not functional (BUG-009)
- Fix vehicle entities not separating by make/model (BUG-011)

**Epic P9-2: Frame Capture & Video Analysis** (Priority: P2)
- Fix frame capture timing optimization (IMP-011)
- Implement adaptive frame sampling (FF-020)
- Add configurable frame count for analysis (IMP-007)
- Store & display all analysis frames (IMP-006)
- Add configurable frame sampling strategy (FF-021)

**Epic P9-3: AI Context & Accuracy** (Priority: P2)
- Add camera context and time of day to AI prompt (IMP-012)
- Implement package delivery false positive adjustment (IMP-013)
- Add summary feedback and custom prompt (IMP-014)
- Fix and complete AI-assisted prompt refinement (FF-023)

**Epic P9-4: Entity Management** (Priority: P2)
- Fix vehicle entity separation by make/model (BUG-011)
- Implement manual entity event assignment (IMP-015)
- Research local MCP server for enhanced AI context (IMP-016)

**Epic P9-5: Infrastructure & DevOps** (Priority: P2)
- Configure SSL/HTTPS support (IMP-009)
- Implement n8n automated development pipeline (FF-027)
- Fix and maintain GitHub Actions CI (BUG-010)

**Epic P9-6: Documentation & UX Polish** (Priority: P3)
- Refactor README.md (IMP-017)
- Create GitHub Pages project site (FF-026)
- Fix events page button positioning (IMP-010)
- Hide MQTT form when disabled (IMP-008)
- Complete accessibility enhancements (IMP-004)
- Camera list optimizations (IMP-005)
- Test connection before save (FF-011)

### Deferred to Future Phases

| Item | Reason |
|------|--------|
| FF-015 | Audio capture - requires significant new infrastructure |
| FF-017 | Export motion events CSV - low priority utility |
| FF-019 | Download & store full motion video - storage implications need design |
| FF-022 | Query-adaptive frame selection - requires embedding infrastructure |
| FF-024 | Native Apple device apps - major new platform effort |
| FF-025 | Cloud relay for remote access - dependency on FF-024 |

---

## Functional Requirements

### Bug Fixes (Epic P9-1)

**FR1:** GitHub Actions CI pipeline passes all tests on every PR
**FR2:** Push notifications work reliably for all events, not just the first
**FR3:** Protect camera filter settings persist after page refresh and server restart
**FR4:** Re-analyse function successfully re-processes event descriptions
**FR5:** AI-assisted prompt refinement submits to AI provider and displays results
**FR6:** AI-assisted prompt refinement modal shows which AI model is being used
**FR7:** AI-assisted prompt refinement has save/replace button to apply refined prompt

### Frame Capture & Video Analysis (Epic P9-2)

**FR8:** Frame capture timing is optimized to capture actual motion activity
**FR9:** System can extract frames using adaptive sampling based on motion/changes
**FR10:** Users can configure number of frames for AI analysis (5, 10, 15, 20)
**FR11:** All frames used for AI analysis are stored and retrievable
**FR12:** Event cards show clickable thumbnails that open frame gallery
**FR13:** Frame gallery displays all analyzed frames with navigation
**FR14:** Users can choose frame sampling strategy (uniform, adaptive, hybrid)
**FR15:** Adaptive sampling prioritizes high-activity frames over static frames

### AI Context & Accuracy (Epic P9-3)

**FR16:** AI prompt includes camera name for contextual descriptions
**FR17:** AI prompt includes time of day/date for temporal context
**FR18:** System attempts to read timestamp/camera name from frame overlay
**FR19:** System falls back to database metadata if overlay not readable
**FR20:** Users can mark package detections as false positives
**FR21:** Package false positive feedback is stored for prompt refinement
**FR22:** Users can provide thumbs up/down feedback on daily summaries
**FR23:** Users can customize summary generation prompt in Settings
**FR24:** Summary feedback data appears in AI Accuracy statistics

### Entity Management (Epic P9-4)

**FR25:** Vehicle entities are separated by make/model/color
**FR26:** Each unique vehicle creates a distinct entity with its own event history
**FR27:** Entity detail page shows list of all linked events
**FR28:** Users can remove events from entities (unlink misattributed events)
**FR29:** Users can add events to existing entities from event cards
**FR30:** Users can move events between entities
**FR31:** Users can merge duplicate entities
**FR32:** Manual entity adjustments are stored to improve future matching

### Infrastructure & DevOps (Epic P9-5)

**FR33:** System supports SSL/HTTPS connections
**FR34:** Let's Encrypt/Certbot integration available in install script
**FR35:** Self-signed certificate generation available as option
**FR36:** n8n instance can be deployed alongside ArgusAI
**FR37:** n8n workflows integrate with Claude Code CLI
**FR38:** n8n workflows execute BMAD method workflows
**FR39:** n8n provides dashboard for pipeline monitoring
**FR40:** n8n implements approval gates for human review

### Documentation & UX Polish (Epic P9-6)

**FR41:** README.md reflects all implemented phases and features
**FR42:** README includes current installation instructions
**FR43:** GitHub Pages site has landing page with project overview
**FR44:** GitHub Pages site has documentation section
**FR45:** GitHub Pages deploys automatically on push to main
**FR46:** Events page buttons don't overlap with header controls
**FR47:** MQTT form fields hidden when integration is disabled
**FR48:** Skip to content link available for keyboard users
**FR49:** Camera list uses React.memo for performance
**FR50:** Test connection endpoint validates camera before save

---

## Non-Functional Requirements

### Performance

**NFR1:** Adaptive frame sampling reduces frames by 50-90% while preserving key events
**NFR2:** Frame gallery loads within 500ms for events with up to 20 frames
**NFR3:** Entity search returns results within 200ms
**NFR4:** n8n workflows complete story creation within 5 minutes
**NFR5:** GitHub Pages site loads within 2 seconds

### Security

**NFR6:** SSL/TLS 1.2+ required for HTTPS connections
**NFR7:** Let's Encrypt certificates auto-renew before expiration
**NFR8:** Self-signed certificates use 2048-bit RSA minimum
**NFR9:** n8n credentials stored securely, not in version control

### Reliability

**NFR10:** Push notifications have 99%+ delivery rate
**NFR11:** Camera filter settings persist across all restart scenarios
**NFR12:** CI pipeline has <5% flaky test rate
**NFR13:** n8n workflows have retry logic for transient failures

### Accuracy

**NFR14:** Frame timing optimization captures activity in 90%+ of events
**NFR15:** Vehicle entity separation achieves 85%+ accuracy for distinct vehicles
**NFR16:** Package false positive feedback reduces false positives by 20% over time

---

## Implementation Planning

### Epic Breakdown

**Epic P9-1: Critical Bug Fixes** (8 stories)
| Story | Description | Backlog ID |
|-------|-------------|------------|
| P9-1.1 | Fix GitHub Actions CI tests | BUG-010 |
| P9-1.2 | Fix push notifications persistence | BUG-007 |
| P9-1.3 | Fix Protect camera filter settings | BUG-008 |
| P9-1.4 | Fix re-analyse function | BUG-005 |
| P9-1.5 | Fix prompt refinement API call | BUG-009 |
| P9-1.6 | Add save/replace button to prompt refinement | BUG-009 |
| P9-1.7 | Show AI model in prompt refinement modal | BUG-009 |
| P9-1.8 | Fix vehicle entity make/model separation | BUG-011 |

**Epic P9-2: Frame Capture & Video Analysis** (7 stories)
| Story | Description | Backlog ID |
|-------|-------------|------------|
| P9-2.1 | Investigate and fix frame capture timing | IMP-011 |
| P9-2.2 | Implement similarity-based frame filtering | FF-020 |
| P9-2.3 | Add motion scoring to frame selection | FF-020 |
| P9-2.4 | Add configurable frame count setting | IMP-007 |
| P9-2.5 | Store all analysis frames to filesystem | IMP-006 |
| P9-2.6 | Build frame gallery modal component | IMP-006 |
| P9-2.7 | Add frame sampling strategy setting | FF-021 |

**Epic P9-3: AI Context & Accuracy** (6 stories)
| Story | Description | Backlog ID |
|-------|-------------|------------|
| P9-3.1 | Add camera context to AI prompt | IMP-012 |
| P9-3.2 | Add time of day to AI prompt | IMP-012 |
| P9-3.3 | Implement package false positive feedback | IMP-013 |
| P9-3.4 | Add summary feedback buttons | IMP-014 |
| P9-3.5 | Add summary prompt customization | IMP-014 |
| P9-3.6 | Complete AI-assisted prompt refinement | FF-023 |

**Epic P9-4: Entity Management** (5 stories)
| Story | Description | Backlog ID |
|-------|-------------|------------|
| P9-4.1 | Improve vehicle entity extraction logic | BUG-011 |
| P9-4.2 | Build entity event list view | IMP-015 |
| P9-4.3 | Implement event-entity unlinking | IMP-015 |
| P9-4.4 | Implement event-entity assignment | IMP-015 |
| P9-4.5 | Research MCP server architecture | IMP-016 |

**Epic P9-5: Infrastructure & DevOps** (6 stories)
| Story | Description | Backlog ID |
|-------|-------------|------------|
| P9-5.1 | Add SSL/HTTPS support to backend | IMP-009 |
| P9-5.2 | Add Let's Encrypt to install script | IMP-009 |
| P9-5.3 | Deploy n8n instance | FF-027 |
| P9-5.4 | Create n8n Claude Code integration | FF-027 |
| P9-5.5 | Create n8n BMAD workflow integration | FF-027 |
| P9-5.6 | Build n8n monitoring dashboard | FF-027 |

**Epic P9-6: Documentation & UX Polish** (8 stories)
| Story | Description | Backlog ID |
|-------|-------------|------------|
| P9-6.1 | Refactor README.md | IMP-017 |
| P9-6.2 | Set up GitHub Pages infrastructure | FF-026 |
| P9-6.3 | Build GitHub Pages landing page | FF-026 |
| P9-6.4 | Create GitHub Pages documentation | FF-026 |
| P9-6.5 | Fix events page button positioning | IMP-010 |
| P9-6.6 | Hide MQTT form when disabled | IMP-008 |
| P9-6.7 | Add skip to content link | IMP-004 |
| P9-6.8 | Add camera list optimizations | IMP-005 |

### Backlog Items Addressed by Phase 9

| Backlog ID | Epic | Status After Phase 9 |
|------------|------|---------------------|
| BUG-005 | P9-1 | Done |
| BUG-007 | P9-1 | Done |
| BUG-008 | P9-1 | Done |
| BUG-009 | P9-1 | Done |
| BUG-010 | P9-1 | Done |
| BUG-011 | P9-1, P9-4 | Done |
| IMP-004 | P9-6 | Done |
| IMP-005 | P9-6 | Done |
| IMP-006 | P9-2 | Done |
| IMP-007 | P9-2 | Done |
| IMP-008 | P9-6 | Done |
| IMP-009 | P9-5 | Done |
| IMP-010 | P9-6 | Done |
| IMP-011 | P9-2 | Done |
| IMP-012 | P9-3 | Done |
| IMP-013 | P9-3 | Done |
| IMP-014 | P9-3 | Done |
| IMP-015 | P9-4 | Done |
| IMP-016 | P9-4 | Research Complete |
| IMP-017 | P9-6 | Done |
| FF-011 | P9-6 | Done |
| FF-020 | P9-2 | Done |
| FF-021 | P9-2 | Done |
| FF-023 | P9-3 | Done |
| FF-026 | P9-6 | Done |
| FF-027 | P9-5 | Done |

**Total: 26 backlog items addressed**

---

## Technical Considerations

### Adaptive Frame Sampling

**Implementation Approach:**
1. **Similarity Thresholding** - Use SSIM or histogram comparison to skip redundant frames
2. **Motion Scoring** - Calculate motion magnitude using optical flow
3. **Combined Scoring** - Prioritize frames with high motion AND low similarity to previous selected frame

```python
# Pseudocode for adaptive sampling
def select_key_frames(frames, target_count):
    scores = []
    for i, frame in enumerate(frames):
        motion_score = calculate_motion(frame, frames[i-1])
        similarity_score = calculate_similarity(frame, last_selected)
        combined = motion_score * (1 - similarity_score)
        scores.append((i, combined))

    # Select top N frames by score
    return sorted(scores, key=lambda x: x[1], reverse=True)[:target_count]
```

### Entity Make/Model Separation

**Current Issue:** All vehicles grouped together regardless of type
**Solution:** Enhance entity extraction to parse make/model/color from AI descriptions

```python
# Entity extraction enhancement
def extract_vehicle_entity(description):
    # Pattern: "color make model" (e.g., "white Toyota Camry")
    pattern = r'(white|black|red|blue|silver|gray|green)\s+(\w+)\s+(\w+)'
    match = re.search(pattern, description, re.IGNORECASE)
    if match:
        return {
            'type': 'vehicle',
            'color': match.group(1),
            'make': match.group(2),
            'model': match.group(3),
            'signature': f"{match.group(1)} {match.group(2)} {match.group(3)}".lower()
        }
```

### n8n Integration Architecture

```
GitHub Webhook → n8n
    ↓
Story Creation (BMAD workflow)
    ↓
Claude Code CLI (implementation)
    ↓
Test Execution
    ↓
Code Review (AI-assisted)
    ↓
PR Creation
    ↓
Approval Gate (human)
    ↓
Merge & Deploy
```

### SSL/HTTPS Options

1. **Let's Encrypt (Recommended)** - Free, auto-renewing, trusted certificates
2. **Self-Signed** - For development/internal use
3. **Nginx Proxy** - SSL termination at reverse proxy level

---

## References

- Product Brief: docs/product-brief.md
- Phase 5 PRD: docs/PRD-phase5.md
- Architecture: docs/architecture.md
- Backlog: docs/backlog.md

---

## Summary

**Phase 9 delivers:**
- Resolution of 6 critical/high-priority bugs
- Intelligent frame capture with adaptive sampling
- AI context awareness (camera, time, location)
- Complete entity management with manual corrections
- SSL/HTTPS for secure connections
- n8n automated development pipeline
- Updated documentation and GitHub Pages site
- UX polish and accessibility improvements

**Total Stories:** 40 across 6 epics
**Backlog Items Addressed:** 26
**New FRs:** 50
**New NFRs:** 16

---

_This PRD captures Phase 9 of ArgusAI - AI Accuracy, Stability & Developer Experience_

_Created through collaborative discovery between Brent and AI facilitator._
