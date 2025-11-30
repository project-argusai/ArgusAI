# Product Brief: Live Object AI Classifier - Phase 2

**Date:** 2025-11-30
**Author:** Brent
**Context:** Software - Feature Enhancement (Post-MVP)

---

## Executive Summary

Phase 2 extends the Live Object AI Classifier beyond the generic RTSP/USB approach to native camera system integration, starting with UniFi Protect. This evolution leverages existing smart detection capabilities from camera ecosystems rather than reimplementing them, while expanding AI provider options for greater flexibility.

**Core Value Proposition:** Native integration over generic - purpose-built connections to camera systems that unlock real-time events, auto-discovery, and smart detection filtering.

---

## Core Vision

### Problem Statement

The current MVP relies on generic RTSP streaming with custom motion detection, which works but creates limitations when users have camera systems with built-in intelligence:

1. **Duplicated Effort** - Running custom motion detection (MOG2/KNN) when UniFi Protect already performs superior motion detection natively
2. **Slow Frame Rates** - Generic RTSP polling results in slower frame capture, causing smart detections (person/vehicle/package) to be hit-or-miss
3. **Manual Configuration** - Each camera requires manual RTSP URL configuration instead of auto-discovery from the controller
4. **Missing Native Events** - No access to UniFi Protect's real-time WebSocket events, smart detection classifications, or doorbell ring notifications

**Key Constraint:** The generic RTSP/USB approach must remain available for users with cameras that don't have backend systems (standalone IP cameras, webcams, etc.). Phase 2 adds native integrations as an *additional* option, not a replacement.

### Proposed Solution

**Native UniFi Protect Integration** as a new camera source type that coexists with generic RTSP/USB cameras.

**Configuration Flow:**
1. User adds UniFi Protect controller (IP/hostname + credentials)
2. System auto-discovers all cameras from controller
3. User selects which cameras to enable for AI analysis via checkboxes
4. Per-camera configuration of which event types to analyze

**Event Type Filtering (per camera):**
- Person detection
- Vehicle detection
- Package detection
- Animal detection
- All motion (fallback)

**Technical Approach:**
- WebSocket connection to Protect controller for real-time events
- Use Protect's native motion/smart detection as trigger (bypass custom motion detection)
- Fetch snapshots via Protect API when events occur
- Feed snapshots to AI providers for natural language description
- Store events in existing event system

**Coexistence Model:**
- UniFi Protect cameras and generic RTSP/USB cameras can operate simultaneously
- Each camera type uses its optimal detection method
- All events flow into the same unified event system and dashboard

---

## Target Users

### Primary Users

**UniFi Protect Power User**

- Already owns UniFi Protect equipment (UDM Pro, Cloud Key Gen2+, cameras)
- Wants to add AI-powered natural language descriptions to their existing surveillance system
- Technically comfortable - UniFi users tend to be prosumers who self-host and configure their own networks
- Likely already uses or is interested in home automation (Home Assistant, HomeKit)
- Values local control and privacy over cloud-dependent solutions
- Frustrated that UniFi's built-in smart detections (person/vehicle/package) don't provide rich context about *what's actually happening*

---

## Phase 2 Scope

### Core Features

**1. UniFi Protect Integration**
- Controller connection (IP/hostname + credentials)
- Camera auto-discovery from controller
- Selectable cameras for AI analysis (checkbox UI)
- Per-camera event type filtering (Person/Vehicle/Package/Animal/All Motion)
- WebSocket real-time event listener
- Snapshot retrieval via Protect API
- Doorbell ring notifications
- Multi-camera event correlation (same event seen by multiple cameras)

**2. xAI Grok AI Provider**
- Add Grok as additional vision-capable AI provider
- Integrate into existing fallback chain (OpenAI → Claude → Gemini → Grok)
- Configure fallback position in settings

### Out of Scope for Phase 2

- Local LLM support (Ollama, llama.cpp) - requires research on vision-capable local models
- Mobile app with push notifications - requires native app development
- Historical pattern analysis - requires ML pipeline for trend detection
- Apple HomeKit integration - requires certification process research
- Home Assistant integration - future smart home ecosystem play
- AI doorbell voice response - requires two-way audio integration

### Future Vision

**Phase 3 and Beyond:**
- **Local LLM Support** - Offline operation with privacy-conscious, zero-API-cost option
- **Mobile App** - Native iOS/Android with push notifications for real-time alerts
- **Historical Analysis** - Activity trends, pattern recognition, anomaly detection
- **Smart Home Integrations** - HomeKit, Home Assistant for automation triggers
- **AI Doorbell Response** - Two-way audio with AI-generated responses to visitors
- **Additional Camera Systems** - Reolink, Hikvision, Frigate integrations

---

## Technical Preferences

**UniFi Protect Integration:**
- `uiprotect` Python library (community-maintained) for API access
- WebSocket connection for real-time event streaming
- Protect API for snapshot retrieval

**xAI Grok Provider:**
- `xai-sdk` Python package
- Vision-capable models (grok-4 or grok-3)
- Token-based pricing (~256 tokens per 448x448 image tile)

**Architecture:**
- New camera source type alongside existing RTSP/USB
- Shared event pipeline - all camera types feed into same event system
- Controller credentials stored encrypted (existing Fernet encryption)

---

## Success Metrics

**UniFi Protect Integration:**
- Cameras auto-discovered from controller successfully
- Real-time events flowing via WebSocket
- Faster/more reliable detection compared to RTSP polling approach
- Event type filtering working (Person/Vehicle/Package/Animal)
- Doorbell ring events captured

**xAI Grok Provider:**
- Grok generating accurate natural language descriptions
- Successfully integrated into AI provider fallback chain
- Comparable quality to existing providers (OpenAI, Claude, Gemini)

---

## Risks and Assumptions

**Assumptions:**
- UniFi Protect API (via `uiprotect` library) is stable and functional
- User has "View Only" or higher access to Protect controller
- xAI Grok API provides vision capabilities comparable to other providers

**Risks:**

| Risk | Impact | Mitigation |
|------|--------|------------|
| UniFi API is unofficial - firmware updates could break integration | High | Monitor `uiprotect` library updates; community usually fixes quickly |
| Grok API rate limits | Medium | Implement request queuing; configure fallback to other providers |
| WebSocket connection stability | Medium | Implement reconnection logic with exponential backoff |
| Multi-camera correlation complexity | Low | Start simple (time-window based); iterate based on real usage |

---

## Supporting Materials

**Related Documents:**
- Brainstorming Session (2025-11-30): `docs/brainstorming-session-results-2025-11-30.md`
- Original Product Brief (MVP): `docs/product-brief.md`
- Architecture: `docs/architecture.md`

**Technical References:**
- uiprotect library: https://github.com/uilibs/uiprotect
- xAI API docs: https://docs.x.ai/docs/guides/image-understanding

---

_This Product Brief captures the vision and requirements for Live Object AI Classifier Phase 2._

_It was created through collaborative discovery and reflects the next evolution beyond the MVP._

_Next: PRD workflow to create detailed requirements from this brief._
