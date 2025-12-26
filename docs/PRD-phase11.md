# ArgusAI Phase 11 - Product Requirements Document

**Author:** Brent
**Date:** 2025-12-25
**Version:** 1.0
**Phase:** 11 - Mobile Platform & Remote Access

---

## Executive Summary

Phase 11 transforms ArgusAI from a local-only application into a **mobile-accessible, anywhere-connected platform**. Building on Phase 10's containerization and API foundation, this phase delivers secure remote access via Cloudflare Tunnel, native mobile push notifications (APNS/FCM), enhanced AI context through the MCP architecture, and continued platform polish.

### What Makes This Phase Special

This phase breaks ArgusAI free from local network constraints. Users will monitor their security cameras from anywhere - receiving rich push notifications on iPhone and Android, accessing their dashboard remotely without VPNs or port forwarding, and benefiting from an AI that learns and improves through accumulated context.

---

## Project Classification

**Technical Type:** Web Application + Backend API + Mobile Services
**Domain:** Home Security / Smart Home / IoT / Mobile
**Complexity:** High (multi-platform push, cloud relay, AI context system)

### Project Context

ArgusAI has completed 10 phases delivering:
- Full UniFi Protect integration with smart detection
- Multi-frame video analysis with AI descriptions
- Entity recognition (people, vehicles) with manual management
- Push notifications (Web Push) and PWA support
- MQTT/Home Assistant and HomeKit integration
- Docker/Kubernetes containerization
- API specification and mobile architecture design

Phase 11 implements the mobile infrastructure designed in Phase 10.

---

## Success Criteria

### Remote Access
- Users can access ArgusAI dashboard from outside local network via Cloudflare Tunnel
- Zero port forwarding or VPN required for remote access
- Connection established within 5 seconds of app launch

### Mobile Notifications
- Push notifications delivered to iOS devices via APNS
- Push notifications delivered to Android devices via FCM
- Notification delivery within 3 seconds of event detection
- Notifications include event thumbnails and rich metadata

### AI Context Enhancement
- MCP context provider improves AI description accuracy by 5-10%
- Feedback history influences AI prompts within same session
- Entity context included in AI analysis for known entities

### Platform Polish
- Camera list performs smoothly with 50+ cameras
- Query-adaptive frame selection reduces AI costs by 20%+

---

## Product Scope

### MVP - Core Deliverables

**Remote Access (Epic P11-1)**
1. Cloudflare Tunnel integration for secure remote access
2. Tunnel status monitoring and auto-reconnection
3. Settings UI for tunnel configuration
4. Documentation for tunnel setup

**Mobile Push Notifications (Epic P11-2)**
1. APNS provider implementation for iOS
2. FCM provider implementation for Android
3. Unified push dispatch service routing to all providers
4. Device registration and token management
5. Mobile push preferences (quiet hours, notification types)

**AI Context Enhancement (Epic P11-3)**
1. MCPContextProvider MVP with feedback and entity context
2. Camera and time pattern context integration
3. Integration with existing prompt service

### Growth Features (Post-MVP)

**Query-Adaptive Frame Selection (Epic P11-4)**
1. Frame embedding generation using CLIP model
2. Query-based frame scoring for re-analysis
3. Top-K frame selection for targeted queries

**Platform Polish (Epic P11-5)**
1. Camera list optimizations (React.memo, virtual scrolling)
2. Test connection before camera save
3. GitHub Pages project documentation site

### Vision (Future Phases)

- Full MCP protocol compliance with external client support
- Native iOS/Android applications
- Apple Watch complications
- Edge AI deployment

---

## Functional Requirements

### Remote Access Requirements (FR1-FR10)

**Cloudflare Tunnel Integration**
- FR1: System supports Cloudflare Tunnel for NAT traversal
- FR2: Tunnel configuration stored securely in system settings
- FR3: Tunnel auto-reconnects on network changes or failures
- FR4: Health endpoint reports tunnel connectivity status
- FR5: API endpoint `/api/v1/system/tunnel-status` returns tunnel state

**Tunnel Management**
- FR6: Settings UI provides tunnel enable/disable toggle
- FR7: Settings UI accepts Cloudflare tunnel token securely
- FR8: Tunnel status indicator shows connection state in UI
- FR9: System logs tunnel connection events for troubleshooting
- FR10: Documentation covers cloudflared installation and setup

### Mobile Push Requirements (FR11-FR30)

**APNS Provider (iOS)**
- FR11: Backend connects to APNS using HTTP/2 protocol
- FR12: APNS authentication via p8 auth key file
- FR13: System configuration stores APNS credentials (key ID, team ID)
- FR14: Push payloads formatted for iOS notification format
- FR15: API endpoint registers iOS device push tokens
- FR16: System handles APNS error responses and token invalidation
- FR17: Notifications support image attachments (thumbnails)

**FCM Provider (Android)**
- FR18: Backend connects to FCM HTTP v1 API
- FR19: FCM authentication via service account JSON
- FR20: System configuration stores FCM credentials securely
- FR21: Push payloads formatted for Android notification format
- FR22: API endpoint registers Android device push tokens
- FR23: System handles FCM error responses and token refresh
- FR24: Notifications support data messages for background processing

**Unified Push Dispatch**
- FR25: PushDispatchService routes to Web Push, APNS, and FCM providers
- FR26: Dispatch queries device tokens by user and applies preferences
- FR27: Dispatch sends to all user devices in parallel
- FR28: Retry logic with exponential backoff for failed deliveries
- FR29: Delivery status tracked per device for monitoring
- FR30: Quiet hours respected across user timezones

### Device Management Requirements (FR31-FR38)

**Device Registration**
- FR31: Device model stores device_id, platform, name, user_id, push_token, last_seen
- FR32: API `POST /api/v1/devices` registers new device
- FR33: API `GET /api/v1/devices` lists user's registered devices
- FR34: API `DELETE /api/v1/devices/{id}` revokes device access
- FR35: Unique device pairing codes generated for initial setup

**Token Management**
- FR36: API `POST /api/v1/auth/refresh` refreshes expired tokens
- FR37: Sliding window expiration extends token by 24h on refresh
- FR38: All tokens invalidated on password change

### AI Context Requirements (FR39-FR48)

**MCPContextProvider MVP**
- FR39: MCPContextProvider gathers feedback history context
- FR40: Context includes recent feedback, camera accuracy, common corrections
- FR41: Context includes matched entity info and similar entities
- FR42: Provider integrates with context_prompt_service.py
- FR43: Parallel async queries complete within 50ms target
- FR44: Fail-open design ensures AI works even if context fails

**Extended Context**
- FR45: Camera context includes location hints and typical activity patterns
- FR46: Time-of-day patterns inform unusual activity detection
- FR47: Optional context caching with 60s TTL reduces latency
- FR48: Metrics track context gathering performance

### Query-Adaptive Requirements (FR49-FR55)

**Frame Selection**
- FR49: EmbeddingService encodes text queries
- FR50: FrameEmbedding model stores per-frame embeddings
- FR51: Frame embeddings generated during extraction
- FR52: API `POST /api/v1/events/{id}/smart-reanalyze?query=...` available
- FR53: Cosine similarity scores frames against query
- FR54: Top-K frames selected for targeted re-analysis
- FR55: Selection overhead under 60ms

### Platform Polish Requirements (FR56-FR62)

**Camera List Performance**
- FR56: CameraPreview component uses React.memo
- FR57: Camera list supports virtual scrolling for large lists
- FR58: React Query provides caching and deduplication

**Camera Setup**
- FR59: Test connection endpoint validates RTSP before save
- FR60: Connection test returns specific error messages
- FR61: UI shows test results before allowing save

**Documentation**
- FR62: GitHub Pages site provides user documentation
- FR63: Site includes installation guide, API reference, FAQ
- FR64: Site auto-deploys on push to main branch

---

## Non-Functional Requirements

### Performance

- NFR1: Tunnel connection established within 5 seconds
- NFR2: Push notification delivery within 3 seconds of event
- NFR3: MCP context queries complete within 50ms
- NFR4: Camera list renders 100 cameras without UI lag
- NFR5: Frame selection overhead under 60ms

### Security

- NFR6: APNS/FCM credentials stored encrypted at rest
- NFR7: Tunnel tokens never logged or exposed in API
- NFR8: Device tokens validated before push delivery
- NFR9: Token refresh prevents replay attacks

### Reliability

- NFR10: Tunnel auto-reconnects within 30 seconds of disconnect
- NFR11: Push delivery retries up to 3 times with backoff
- NFR12: MCP context fails open - AI works without context
- NFR13: Device registration survives server restarts

### Scalability

- NFR14: Push dispatch handles 100 concurrent deliveries
- NFR15: Frame embedding storage scales to 100K frames
- NFR16: Virtual scrolling handles 1000+ cameras

---

## Implementation Planning

### Epic Breakdown

| Epic | Title | Stories | Priority |
|------|-------|---------|----------|
| P11-1 | Remote Access via Cloudflare Tunnel | 4 | P1 |
| P11-2 | Mobile Push Notifications | 6 | P1 |
| P11-3 | AI Context Enhancement (MCP) | 4 | P2 |
| P11-4 | Query-Adaptive Frame Selection | 3 | P3 |
| P11-5 | Platform Polish & Documentation | 4 | P3 |

**Total: 5 Epics, ~21 Stories**

### Epic Details

**P11-1: Remote Access via Cloudflare Tunnel**
- P11-1.1: Implement Cloudflare Tunnel integration
- P11-1.2: Add tunnel status monitoring and auto-reconnect
- P11-1.3: Create Settings UI for tunnel configuration
- P11-1.4: Document tunnel setup in user guide

**P11-2: Mobile Push Notifications**
- P11-2.1: Implement APNS provider for iOS push
- P11-2.2: Implement FCM provider for Android push
- P11-2.3: Create unified push dispatch service
- P11-2.4: Implement device registration and token management
- P11-2.5: Add mobile push preferences (quiet hours)
- P11-2.6: Support notification thumbnails/attachments

**P11-3: AI Context Enhancement (MCP)**
- P11-3.1: Implement MCPContextProvider MVP with feedback context
- P11-3.2: Add entity match context to provider
- P11-3.3: Integrate camera and time pattern context
- P11-3.4: Add context caching and performance metrics

**P11-4: Query-Adaptive Frame Selection**
- P11-4.1: Add text encoding to EmbeddingService
- P11-4.2: Implement frame embedding storage and generation
- P11-4.3: Create smart-reanalyze endpoint with query matching

**P11-5: Platform Polish & Documentation**
- P11-5.1: Optimize camera list with React.memo and virtual scrolling
- P11-5.2: Add test connection before camera save
- P11-5.3: Create GitHub Pages documentation site
- P11-5.4: Add export motion events to CSV

---

## Backlog Item Mapping

| Phase 11 Epic | Backlog Items |
|---------------|---------------|
| P11-1 | IMP-029 (Cloud Relay), FF-025 |
| P11-2 | IMP-030 (APNS), IMP-031 (FCM), IMP-032 (Dispatch), IMP-027, IMP-028 |
| P11-3 | IMP-016, IMP-024, IMP-025 |
| P11-4 | FF-022, IMP-033, IMP-034 |
| P11-5 | IMP-005, FF-011, FF-017, FF-026 |

---

## References

- Product Brief: docs/product-brief.md
- Phase 10 PRD: docs/PRD-phase10.md
- Backlog: docs/backlog.md
- Mobile Auth Flow: docs/api/mobile-auth-flow.md
- Cloud Relay Architecture: docs/architecture/cloud-relay-architecture.md
- Mobile Push Architecture: docs/api/mobile-push-architecture.md
- MCP Server Research: docs/research/mcp-server-research.md
- Query-Adaptive Research: docs/research/query-adaptive-frames-research.md

---

## Next Steps

1. **Epic & Story Breakdown** - Run: `workflow create-epics-and-stories`
2. **Architecture Update** - Run: `workflow create-architecture` (for push/tunnel additions)
3. **Sprint Planning** - Run: `workflow sprint-planning`

---

_This PRD captures Phase 11 of ArgusAI - breaking free from local network constraints to deliver mobile-accessible, anywhere-connected security monitoring with AI that learns from every interaction._

_Created through BMAD workflow by Brent and AI facilitator._
