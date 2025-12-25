# Story P10-5.3: Design Cloud Relay Architecture

Status: done

## Story

As an **architect or developer building mobile apps for ArgusAI**,
I want **a documented cloud relay architecture for secure remote access**,
So that **mobile clients can access their ArgusAI instance without requiring port forwarding or exposing the local network**.

## Acceptance Criteria

1. **AC-5.3.1:** Given I read the architecture document, when I understand the relay design, then I know how NAT traversal is handled without requiring users to configure port forwarding

2. **AC-5.3.2:** Given the architecture document is complete, when I review the security model, then I understand end-to-end encryption requirements and how data is protected in transit

3. **AC-5.3.3:** Given the architecture document addresses device pairing, when I implement the mobile app, then I understand the device registration and authentication flow

4. **AC-5.3.4:** Given the architecture considers bandwidth, when I design mobile features, then I understand optimization strategies for thumbnails and video streaming

5. **AC-5.3.5:** Given multiple relay options exist, when I read the comparison, then I can make an informed decision about the implementation approach

6. **AC-5.3.6:** Given local network fallback is documented, when the mobile device is on the same network, then direct local access is preferred over cloud relay for better performance

## Tasks / Subtasks

- [x] Task 1: Research Cloud Relay Technologies (AC: 5)
  - [x] Subtask 1.1: Evaluate Cloudflare Tunnel approach (Zero Trust, Argo Tunnel)
  - [x] Subtask 1.2: Evaluate AWS IoT Core + API Gateway + WebSocket approach
  - [x] Subtask 1.3: Evaluate self-hosted relay server options (e.g., frp, ngrok-like)
  - [x] Subtask 1.4: Document pros/cons/cost of each approach

- [x] Task 2: Design Security Model (AC: 2, 3)
  - [x] Subtask 2.1: Define end-to-end encryption requirements (TLS 1.3, certificate pinning)
  - [x] Subtask 2.2: Design device pairing flow (QR code, PIN, or secure link)
  - [x] Subtask 2.3: Document relay authentication (how relay trusts both client and server)
  - [x] Subtask 2.4: Address session management and token refresh over relay

- [x] Task 3: Design NAT Traversal Approach (AC: 1)
  - [x] Subtask 3.1: Document outbound connection model (server initiates connection to relay)
  - [x] Subtask 3.2: Address firewall compatibility (ports 443/80 only)
  - [x] Subtask 3.3: Define connection resilience (reconnection, keepalive)
  - [x] Subtask 3.4: Consider STUN/TURN for peer-to-peer fallback

- [x] Task 4: Design Bandwidth Optimization (AC: 4)
  - [x] Subtask 4.1: Define thumbnail compression for mobile (WebP, quality settings)
  - [x] Subtask 4.2: Document adaptive video quality based on connection speed
  - [x] Subtask 4.3: Consider event data pagination for mobile (smaller payloads)
  - [x] Subtask 4.4: Address push notification vs polling tradeoffs

- [x] Task 5: Design Local Network Fallback (AC: 6)
  - [x] Subtask 5.1: Document mDNS/Bonjour discovery for local network detection
  - [x] Subtask 5.2: Design automatic switching between local and relay modes
  - [x] Subtask 5.3: Address split-horizon DNS considerations

- [x] Task 6: Create Architecture Document (AC: 1-6)
  - [x] Subtask 6.1: Create `docs/architecture/cloud-relay-architecture.md`
  - [x] Subtask 6.2: Include architecture diagrams (Mermaid)
  - [x] Subtask 6.3: Document recommended implementation approach
  - [x] Subtask 6.4: Include cost estimates for relay options
  - [x] Subtask 6.5: Cross-reference with mobile auth flow (P10-5.2)

## Dev Notes

### Architecture Context

This story is documentation/design work only - no implementation required. The goal is to produce a comprehensive architecture document that will guide future implementation of cloud relay functionality.

**Key Requirements from PRD-phase10.md:**
- FR48: Cloud relay architecture document defines secure tunnel approach
- FR49: Architecture addresses NAT traversal for remote access
- FR50: Architecture defines device pairing and authentication flow
- FR51: Architecture considers bandwidth optimization for thumbnails/video

**Existing Infrastructure:**
- Backend runs on user's local network (home server, Raspberry Pi, etc.)
- No guaranteed public IP or port forwarding capability
- Mobile devices need access when outside the home network
- Push notifications already work via APNS/FCM (server-to-device)
- The challenge is device-to-server (mobile app to ArgusAI backend)

### Key Design Considerations

1. **Zero Configuration Goal:** Users should not need to configure routers or open ports
2. **Privacy First:** User data should never be stored on relay servers
3. **Cost Awareness:** Solution should be free or very low cost for personal use
4. **Reliability:** Relay connection should auto-reconnect and handle network changes
5. **Performance:** Local access should be preferred when on same network

### Relay Technology Options

**Option A: Cloudflare Tunnel (Recommended for simplicity)**
- Pros: Free tier available, no server to manage, excellent security, automatic TLS
- Cons: Depends on Cloudflare infrastructure, requires cloudflared daemon

**Option B: AWS IoT + API Gateway**
- Pros: Enterprise-grade, scalable, pay-per-use
- Cons: Complex setup, requires AWS account, ongoing costs

**Option C: Self-Hosted Relay (frp, rathole, bore)**
- Pros: Full control, no third-party dependency, open source
- Cons: Requires VPS with public IP, user must manage infrastructure

### Project Structure Notes

- Architecture document: `docs/architecture/cloud-relay-architecture.md`
- Should include Mermaid diagrams for visual representation
- Cross-references to `docs/api/mobile-auth-flow.md` (created in P10-5.2)

### Learnings from Previous Story

**From Story P10-5-2 (Status: done)**

- **New Documentation Created**: Mobile auth flow documented at `docs/api/mobile-auth-flow.md` - use as reference for device authentication patterns
- **JWT Token Flow**: Mobile clients use Bearer token authentication, not cookies
- **Device Registration**: Device pairing flow already designed with unique device ID using identifierForVendor
- **Push Token Management**: APNS/FCM registration documented - can reuse patterns for relay connection
- **Biometric Auth**: Face ID/Touch ID patterns established for local credential storage
- **Sequence Diagrams**: Use Mermaid syntax (same as P10-5.2) for consistency

[Source: docs/sprint-artifacts/p10-5-2-document-mobile-authentication-flow.md#Dev-Agent-Record]

### References

- [Source: docs/PRD-phase10.md#FR48-FR51]
- [Source: docs/epics-phase10.md#Story-P10-5.3]
- [Source: docs/api/mobile-auth-flow.md] - Mobile authentication flow
- [Source: docs/api/openapi-v1.yaml] - OpenAPI specification
- [Cloudflare Tunnel Documentation](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
- [AWS IoT Core](https://docs.aws.amazon.com/iot/)
- [frp - Fast Reverse Proxy](https://github.com/fatedier/frp)

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p10-5-3-design-cloud-relay-architecture.context.xml

### Agent Model Used

Claude Opus 4.5

### Debug Log References

- Analyzed existing mobile auth documentation from P10-5.2 for device pairing patterns
- Researched Cloudflare Tunnel, AWS IoT, and self-hosted relay options
- Designed NAT traversal architecture using outbound-only connections
- Created comprehensive architecture document with Mermaid diagrams

### Completion Notes List

- Created comprehensive cloud relay architecture documentation at `docs/architecture/cloud-relay-architecture.md`
- Documented three relay technology options with detailed pros/cons/cost analysis:
  - Cloudflare Tunnel (recommended for personal use - free tier)
  - AWS IoT + API Gateway (enterprise alternative)
  - Self-hosted relay with frp/rathole (privacy-focused alternative)
- Designed security model with TLS 1.3, certificate pinning recommendations, and JWT authentication flow over relay
- Created device pairing flow with QR code/PIN code approach, including sequence diagrams
- Documented NAT traversal using outbound-only connection model that works on any ISP including CGNAT
- Added bandwidth optimization strategies: WebP thumbnails, adaptive video quality, pagination
- Designed local network fallback using mDNS/Bonjour discovery with automatic mode switching
- Included 6 Mermaid diagrams: high-level architecture, data flow, device pairing, connection lifecycle, mDNS discovery, AWS alternative
- Added implementation roadmap with 4 phases for future development
- Included detailed cost analysis for all relay options
- Cross-referenced with mobile-auth-flow.md from P10-5.2

### File List

**New Files:**
- docs/architecture/cloud-relay-architecture.md - Comprehensive cloud relay architecture documentation

---

## Change Log

| Date | Change |
|------|--------|
| 2025-12-25 | Story drafted |
| 2025-12-25 | Story completed - all tasks done, architecture document created |
