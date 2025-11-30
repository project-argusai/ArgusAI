# Live Object AI Classifier Phase 2 - Product Requirements Document

**Author:** Brent
**Date:** 2025-11-30
**Version:** 1.0

---

## Executive Summary

Phase 2 extends the Live Object AI Classifier from generic RTSP/USB camera support to native camera system integration, starting with UniFi Protect. This evolution leverages existing smart detection capabilities from camera ecosystems rather than reimplementing them, while expanding AI provider options with xAI Grok.

**The core promise:** Real-time, reliable AI-powered event descriptions by tapping directly into UniFi Protect's superior motion detection and smart classifications, eliminating the limitations of RTSP polling.

### What Makes This Special

**Native integration over generic** - Instead of treating all cameras the same through lowest-common-denominator RTSP streams, Phase 2 creates purpose-built connections that unlock:
- Real-time WebSocket events (no polling delays)
- Camera auto-discovery (no manual RTSP URL configuration)
- Smart detection filtering (Person/Vehicle/Package/Animal pre-classification)
- Doorbell-specific event handling

This transforms the system from "works with any camera" to "works *optimally* with your camera system."

---

## Project Classification

**Technical Type:** API/Backend + Web App (Hybrid)
**Domain:** Home Security / Consumer IoT
**Complexity:** Medium (unofficial API dependency, WebSocket management)

This is a feature enhancement to an existing MVP, not a greenfield project. The Phase 2 scope is focused:
1. UniFi Protect native integration (primary)
2. xAI Grok AI provider (secondary)

Both features extend the existing architecture rather than replacing it.

---

## Success Criteria

**Phase 2 succeeds when:**

1. **UniFi Protect cameras "just work"** - User connects controller once, cameras auto-discover, events flow without manual RTSP configuration
2. **Events are faster and more reliable** - WebSocket-driven events arrive in real-time vs RTSP polling delays; smart detection filtering reduces noise
3. **Coexistence works seamlessly** - Users can mix UniFi Protect and generic RTSP/USB cameras in the same system without conflicts
4. **xAI Grok produces quality descriptions** - Comparable to existing OpenAI/Claude/Gemini providers with successful fallback integration

**Measurable outcomes:**
- Camera discovery completes within 10 seconds of controller connection
- Event latency < 2 seconds from Protect detection to AI description
- Zero duplicate events between Protect and RTSP cameras
- Grok API successfully generates descriptions for 95%+ of requests

---

## Product Scope

### MVP - Phase 2 Core

**1. UniFi Protect Integration**
- Single controller connection (IP/hostname + encrypted credentials)
- Camera auto-discovery from controller
- Selectable cameras for AI analysis (enable/disable per camera)
- Per-camera event type filtering (Person/Vehicle/Package/Animal/All Motion)
- WebSocket real-time event listener with reconnection logic
- Snapshot retrieval via Protect API on event trigger
- Doorbell ring event notifications
- Multi-camera event correlation (time-window based)

**2. xAI Grok AI Provider**
- Grok as additional vision-capable AI provider
- Integration into existing fallback chain
- Configurable fallback position in AI provider settings

**3. Coexistence**
- UniFi Protect cameras operate alongside existing RTSP/USB cameras
- Unified event pipeline - all sources feed same event system
- Single dashboard view for all camera types

### Growth Features (Post-Phase 2)

- **Local LLM support** - Ollama/llama.cpp for offline, privacy-conscious operation
- **Multiple UniFi controllers** - Support for users with multiple sites
- **Mobile app** - Native iOS/Android with push notifications
- **Historical pattern analysis** - Activity trends and anomaly detection

### Vision (Future Phases)

- **Apple HomeKit integration** - Native iOS Home app and Siri support
- **Home Assistant integration** - Automation triggers based on AI detections
- **AI doorbell voice response** - Two-way audio with AI-generated visitor responses
- **Additional camera systems** - Reolink, Hikvision, Frigate native integrations

---

## Functional Requirements

### UniFi Protect Controller Management

- **FR1:** Users can add a UniFi Protect controller by providing hostname/IP and credentials
- **FR2:** System validates controller connection and authentication before saving
- **FR3:** System stores controller credentials encrypted using existing Fernet encryption
- **FR4:** Users can edit controller connection settings
- **FR5:** Users can remove a controller (with confirmation)
- **FR6:** Users can test controller connectivity from the UI
- **FR7:** System displays controller connection status (connected/disconnected/error)

### Camera Discovery & Selection

- **FR8:** System auto-discovers all cameras from connected UniFi Protect controller
- **FR9:** Users can view list of discovered cameras with names and types
- **FR10:** Users can enable or disable individual cameras for AI analysis
- **FR11:** Users can configure event type filters per camera (Person/Vehicle/Package/Animal/All Motion)
- **FR12:** System distinguishes camera types (standard camera vs doorbell)
- **FR13:** Camera enable/disable and filter settings persist across restarts

### Real-Time Event Processing

- **FR14:** System maintains WebSocket connection to UniFi Protect controller
- **FR15:** System automatically reconnects WebSocket on connection loss (exponential backoff)
- **FR16:** System receives real-time motion/smart detection events via WebSocket
- **FR17:** System filters events based on per-camera event type configuration
- **FR18:** System fetches snapshot from Protect API when event passes filters
- **FR19:** System submits snapshot to AI provider for description generation
- **FR20:** System stores event with AI description in existing event system

### Doorbell Integration

- **FR21:** System detects doorbell ring events from UniFi Protect
- **FR22:** System generates "doorbell ring" notification distinct from motion events
- **FR23:** Doorbell events trigger AI analysis of who is at the door

### Multi-Camera Correlation

- **FR24:** System detects when multiple cameras capture the same event (time-window based)
- **FR25:** System links correlated events together in the event record
- **FR26:** Dashboard displays correlated events as related

### xAI Grok AI Provider

- **FR27:** Users can add xAI Grok as an AI provider with API key
- **FR28:** System validates Grok API key on save
- **FR29:** Users can configure Grok's position in the AI provider fallback chain
- **FR30:** System can send images to Grok API for vision-based description
- **FR31:** Grok provider follows same interface as existing providers (OpenAI/Claude/Gemini)

### Coexistence & Unified Experience

- **FR32:** UniFi Protect cameras and RTSP/USB cameras can operate simultaneously
- **FR33:** All camera types feed events into the same unified event pipeline
- **FR34:** Dashboard displays events from all camera sources in single timeline
- **FR35:** Alert rules apply equally to events from any camera source
- **FR36:** Users can identify camera source type in event details

---

## Non-Functional Requirements

### Performance

- **NFR1:** Camera discovery completes within 10 seconds of controller connection
- **NFR2:** Event latency < 2 seconds from Protect detection to AI description stored
- **NFR3:** WebSocket reconnection attempts within 5 seconds of connection loss
- **NFR4:** Snapshot retrieval completes within 1 second

### Reliability

- **NFR5:** WebSocket connection maintains 99%+ uptime during normal operation
- **NFR6:** System recovers gracefully from controller disconnection without crashing
- **NFR7:** Failed AI provider requests fall back to next provider within 2 seconds
- **NFR8:** No event loss during brief WebSocket reconnection windows

### Security

- **NFR9:** Controller credentials encrypted at rest using Fernet encryption
- **NFR10:** API keys for xAI Grok stored encrypted (same as existing providers)
- **NFR11:** WebSocket connection uses HTTPS/WSS
- **NFR12:** No credentials logged in plain text

### Integration

- **NFR13:** UniFi Protect integration works with `uiprotect` library v4.x+
- **NFR14:** Compatible with UniFi OS 3.x+ controllers (UDM Pro, Cloud Key Gen2+)
- **NFR15:** xAI Grok integration uses official `xai-sdk` package
- **NFR16:** Existing RTSP/USB camera functionality unaffected by Phase 2 additions

---

## Implementation Planning

### Epic Breakdown Required

Requirements must be decomposed into epics and bite-sized stories.

**Suggested Epic Structure:**

| Epic | FRs Covered | Description |
|------|-------------|-------------|
| Epic 1: UniFi Protect Controller Integration | FR1-FR7, FR14-FR15 | Controller connection, authentication, WebSocket setup |
| Epic 2: Camera Discovery & Configuration | FR8-FR13 | Auto-discovery, selection UI, event type filtering |
| Epic 3: Real-Time Event Processing | FR16-FR20 | Event reception, filtering, snapshot retrieval, AI submission |
| Epic 4: Doorbell & Multi-Camera Features | FR21-FR26 | Doorbell events, multi-camera correlation |
| Epic 5: xAI Grok Provider | FR27-FR31 | New AI provider integration |
| Epic 6: Coexistence & Polish | FR32-FR36, NFRs | Unified experience, testing, documentation |

**Next Step:** Run `workflow create-epics-and-stories` to create the implementation breakdown.

---

## Risks & Assumptions

### Assumptions

- UniFi Protect API via `uiprotect` library is stable and functional
- User has "View Only" or higher access to Protect controller
- xAI Grok API provides vision capabilities comparable to other providers
- Single controller is sufficient for Phase 2 target users

### Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| UniFi firmware update breaks `uiprotect` library | High | Medium | Monitor library releases; community typically fixes within days |
| Grok API rate limits hit during high activity | Medium | Low | Request queuing; automatic fallback to other providers |
| WebSocket connection instability | Medium | Medium | Exponential backoff reconnection; event buffering during reconnect |
| Multi-camera correlation produces false positives | Low | Medium | Conservative time windows; user can disable feature |

---

## References

- Product Brief (Phase 2): `docs/product-brief-phase2-2025-11-30.md`
- Brainstorming Session: `docs/brainstorming-session-results-2025-11-30.md`
- Original MVP Product Brief: `docs/product-brief.md`
- Architecture: `docs/architecture.md`
- Technical References:
  - uiprotect library: https://github.com/uilibs/uiprotect
  - xAI API docs: https://docs.x.ai/docs/guides/image-understanding

---

## PRD Summary

| Metric | Value |
|--------|-------|
| Functional Requirements | 36 |
| Non-Functional Requirements | 16 |
| Suggested Epics | 6 |
| Primary Feature | UniFi Protect Integration |
| Secondary Feature | xAI Grok AI Provider |

**What makes this special:** Native integration over generic - purpose-built connections to UniFi Protect that unlock real-time WebSocket events, camera auto-discovery, and smart detection filtering that RTSP polling cannot provide.

---

_This PRD captures Phase 2 of Live Object AI Classifier - native integration over generic._

_Created through collaborative discovery between Brent and AI facilitator._
