# Story P10-5.2: Document Mobile Authentication Flow

Status: done

## Story

As a **developer building mobile apps for ArgusAI**,
I want **authentication flows documented for mobile clients**,
So that **I can implement secure login, token management, and device registration following established patterns**.

## Acceptance Criteria

1. **AC-5.2.1:** Given I'm developing a mobile app, when I read the authentication documentation, then I understand how to authenticate users via JWT tokens

2. **AC-5.2.2:** Given a mobile app user session, when the JWT token expires, then documentation describes the token refresh mechanism

3. **AC-5.2.3:** Given a new mobile device, when the user logs in, then documentation covers device registration and pairing flow

4. **AC-5.2.4:** Given push notification requirements, when I implement mobile push, then documentation describes push notification token management

5. **AC-5.2.5:** Given security requirements, when I implement authentication, then documentation addresses biometric authentication integration

6. **AC-5.2.6:** Given the documentation is complete, when I review it, then it includes sequence diagrams for all authentication flows

7. **AC-5.2.7:** Given mobile-specific concerns, when I implement auth, then documentation addresses token storage best practices (Keychain/Keystore)

## Tasks / Subtasks

- [x] Task 1: Analyze Current Authentication Implementation (AC: 1, 2)
  - [x] Subtask 1.1: Document existing JWT flow from `backend/app/api/v1/auth.py`
  - [x] Subtask 1.2: Identify gaps between web auth and mobile requirements
  - [x] Subtask 1.3: Document current token expiration settings and configuration

- [x] Task 2: Create JWT Token Flow Documentation (AC: 1, 2, 7)
  - [x] Subtask 2.1: Document login endpoint for mobile (POST /api/v1/auth/login)
  - [x] Subtask 2.2: Describe token storage recommendations (iOS Keychain, Android Keystore)
  - [x] Subtask 2.3: Document Authorization header usage for mobile (Bearer token vs cookie)
  - [x] Subtask 2.4: Define token refresh strategy for mobile clients

- [x] Task 3: Document Device Registration Flow (AC: 3)
  - [x] Subtask 3.1: Design device registration model (device ID, platform, name)
  - [x] Subtask 3.2: Document device pairing flow for first-time setup
  - [x] Subtask 3.3: Describe device-to-user association
  - [x] Subtask 3.4: Document device management (list, rename, revoke)

- [x] Task 4: Document Push Notification Token Management (AC: 4)
  - [x] Subtask 4.1: Describe APNS token registration flow (iOS)
  - [x] Subtask 4.2: Describe FCM token registration flow (Android)
  - [x] Subtask 4.3: Document token refresh/expiration handling
  - [x] Subtask 4.4: Define push subscription endpoint requirements

- [x] Task 5: Document Biometric Authentication Integration (AC: 5)
  - [x] Subtask 5.1: Describe Face ID / Touch ID integration pattern
  - [x] Subtask 5.2: Document credential storage for biometric unlock
  - [x] Subtask 5.3: Address fallback to password authentication

- [x] Task 6: Create Sequence Diagrams (AC: 6)
  - [x] Subtask 6.1: Create login flow sequence diagram
  - [x] Subtask 6.2: Create token refresh sequence diagram
  - [x] Subtask 6.3: Create device registration sequence diagram
  - [x] Subtask 6.4: Create push token registration sequence diagram

- [x] Task 7: Compile and Review Documentation
  - [x] Subtask 7.1: Create docs/api/mobile-auth-flow.md
  - [x] Subtask 7.2: Add diagrams using Mermaid syntax
  - [x] Subtask 7.3: Cross-reference with OpenAPI spec (P10-5.1)
  - [x] Subtask 7.4: Review for completeness against all ACs

## Dev Notes

### Architecture Context

ArgusAI currently uses cookie-based JWT authentication for web clients, but also supports Bearer token via Authorization header (implemented in `get_current_user` at `backend/app/api/v1/auth.py:35`). Mobile clients will exclusively use the Bearer token approach.

**Existing Authentication Flow:**
- Login: POST `/api/v1/auth/login` returns JWT token and sets cookie
- Token validation: JWT decoded via `backend/app/utils/jwt.py`
- Token expiration: Configurable via `JWT_EXPIRATION_HOURS` (default 24h)
- Rate limiting: 5 attempts per 15 minutes on login

**Mobile-Specific Considerations:**
1. Mobile apps should use Authorization header, not cookies
2. Token storage must use platform-secure storage (Keychain/Keystore)
3. Token refresh needed before expiration to maintain session
4. Device registration enables per-device token revocation
5. Push notification tokens need association with user devices

### Current Implementation References

From P10-5.1 OpenAPI work:
- OpenAPI spec: `docs/api/openapi-v1.yaml`
- Security schemes documented: JWT bearer and cookie auth
- All auth endpoints have enhanced descriptions

### Key Files to Reference

- `backend/app/api/v1/auth.py` - Current auth endpoints
- `backend/app/utils/jwt.py` - Token creation/validation
- `backend/app/schemas/auth.py` - Auth request/response schemas
- `backend/app/core/config.py` - JWT configuration settings

### Project Structure Notes

- Documentation will be added to `docs/api/`
- Sequence diagrams use Mermaid syntax for GitHub rendering
- Cross-reference to existing OpenAPI specification

### Learnings from Previous Story

**From Story P10-5-1 (Status: done)**

- **New Files Created**: OpenAPI spec at `docs/api/openapi-v1.yaml` and `docs/api/openapi-v1.json` - use these as reference for API structure
- **Security Schemes Added**: JWT bearer and cookie auth schemes documented in OpenAPI - mobile docs should align with these
- **Export Script**: `backend/scripts/export_openapi.py` can regenerate spec if auth endpoints change
- **Enhanced Endpoints**: Auth endpoints now have full OpenAPI descriptions in `backend/app/api/v1/auth.py`

[Source: docs/sprint-artifacts/P10-5-1-generate-openapi-specification.md#Dev-Agent-Record]

### References

- [Source: docs/PRD-phase10.md#FR44-FR51]
- [Source: docs/epics-phase10.md#Story-P10-5.2]
- [Source: docs/api/openapi-v1.yaml] - OpenAPI specification
- [FastAPI Security Documentation](https://fastapi.tiangolo.com/tutorial/security/)
- [Apple Keychain Services](https://developer.apple.com/documentation/security/keychain_services)
- [Android Keystore](https://developer.android.com/training/articles/keystore)

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/P10-5-2-document-mobile-authentication-flow.context.xml

### Agent Model Used

Claude Opus 4.5

### Debug Log References

- Analyzed existing auth implementation in `backend/app/api/v1/auth.py`
- Identified mobile-specific requirements: Bearer token vs cookie, Keychain storage, biometric integration
- Reviewed push notification flow in `backend/app/api/v1/push.py` for APNS/FCM integration patterns

### Completion Notes List

- Created comprehensive mobile authentication documentation at `docs/api/mobile-auth-flow.md`
- Documented JWT token authentication flow with Swift code examples
- Included token refresh strategy with proactive refresh pattern (refresh when < 1 hour remaining)
- Documented device registration flow with unique device ID generation using identifierForVendor
- Covered APNS push notification token management with Swift implementation
- Added biometric authentication (Face ID/Touch ID) integration with Keychain credential storage
- Included secure token storage best practices using iOS Keychain with appropriate accessibility levels
- Created 5 Mermaid sequence diagrams: login, token refresh, device registration, push registration, biometric auth
- Documented error handling patterns and retry strategies
- Added security best practices section covering token security, credential storage, and network security

### File List

**New Files:**
- docs/api/mobile-auth-flow.md - Comprehensive mobile authentication documentation with sequence diagrams

---

## Change Log

| Date | Change |
|------|--------|
| 2025-12-25 | Story drafted |
| 2025-12-25 | Story completed - all tasks done, documentation created |
