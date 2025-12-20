# Epic Technical Specification: Native Apple Apps Foundation

Date: 2025-12-20
Author: Brent
Epic ID: P8-4
Status: Draft

---

## Overview

Epic P8-4 establishes the foundation for native Apple device applications and cloud relay infrastructure. This is a research and architecture epic that prepares ArgusAI for mobile expansion by evaluating technologies, designing secure remote access, documenting mobile APIs, and creating an iPhone prototype. This epic focuses on iPhone, iPad, Apple Watch, Apple TV, and macOS native applications.

The goal is to enable users to monitor their security cameras from anywhere using native Apple apps with a seamless, secure connection to their local ArgusAI instance.

## Objectives and Scope

### In Scope

- **P8-4.1**: Research and document technology options for Apple app development
- **P8-4.2**: Design cloud relay architecture for NAT traversal and remote access
- **P8-4.3**: Create comprehensive mobile API specification (OpenAPI/Swagger)
- **P8-4.4**: Build iPhone app prototype demonstrating core connectivity

### Out of Scope

- Production-ready apps (prototype only)
- Android app development
- App Store submission
- Full video streaming implementation
- Complex entity recognition in mobile app

## System Architecture Alignment

### Architecture Decisions (from architecture-phase8.md)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Mobile Auth | Device pairing codes (6-digit, 5-min expiry) | Secure, user-friendly, no passwords |
| Cloud Relay | Cloudflare Tunnel + Tailscale fallback | Free tier, easy setup, NAT traversal |
| Apple Apps | SwiftUI native (iOS 17+) | Best native experience, code sharing |

### Components Referenced

| Component | Location | Stories Affected |
|-----------|----------|------------------|
| Push Notification Service | `backend/app/services/push_notification_service.py` | P8-4.3, P8-4.4 |
| Events API | `backend/app/api/v1/events.py` | P8-4.3 |
| System Settings | `backend/app/api/v1/system.py` | P8-4.2 |

### New Components

| Component | Location | Purpose |
|-----------|----------|---------|
| Mobile Auth API | `backend/app/api/v1/mobile/auth.py` | Device pairing and token management |
| Mobile Events API | `backend/app/api/v1/mobile/events.py` | Mobile-optimized event queries |
| Mobile Push API | `backend/app/api/v1/mobile/push.py` | APNS token registration |
| MobileAuthService | `backend/app/services/mobile_auth_service.py` | Pairing code generation/verification |
| iOS App | `ios-app/ArgusAI/` | SwiftUI iPhone prototype |
| Research Document | `docs/research/apple-apps-technology.md` | Technology evaluation |
| Relay Design | `docs/architecture/cloud-relay-design.md` | Cloud relay architecture |

---

## Detailed Design

### Services and Modules

| Service/Module | Responsibility | Stories |
|----------------|----------------|---------|
| Research Document | Technology evaluation and recommendation | P8-4.1 |
| Cloud Relay Design | Remote access architecture | P8-4.2 |
| Mobile API Spec | OpenAPI contract for mobile | P8-4.3 |
| MobileAuthService | Pairing code and JWT tokens | P8-4.3, P8-4.4 |
| iOS Prototype | Demonstrate connectivity | P8-4.4 |

### Data Models and Contracts

#### New Model: DevicePairing

```python
# backend/app/models/device_pairing.py

class DevicePairing(Base):
    __tablename__ = "device_pairings"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    device_id = Column(String, nullable=False, unique=True, index=True)
    device_name = Column(String, nullable=False)  # "iPhone 15 Pro"
    device_type = Column(String, nullable=False)  # "iphone", "ipad", "watch", "appletv", "mac"
    apns_token = Column(String, nullable=True)  # Apple Push token
    refresh_token_hash = Column(String, nullable=True)  # Hashed refresh token
    last_seen_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
```

#### Temporary Model: PairingCode (In-Memory or Redis)

```python
# Not persisted to database - stored in memory/Redis with TTL

class PairingCode:
    code: str  # 6 digits
    created_at: datetime
    expires_at: datetime  # created_at + 5 minutes
    used: bool = False
```

#### Mobile API Schemas

```python
# backend/app/schemas/mobile.py

class PairingCodeRequest(BaseModel):
    pass  # No body needed

class PairingCodeResponse(BaseModel):
    pairing_code: str
    expires_at: datetime
    expires_in_seconds: int

class PairingVerifyRequest(BaseModel):
    pairing_code: str
    device_name: str
    device_id: str
    device_type: str = "iphone"

class PairingVerifyResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int  # seconds

class TokenRefreshRequest(BaseModel):
    refresh_token: str
    device_id: str

class TokenRefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int

class APNSRegisterRequest(BaseModel):
    apns_token: str
    device_id: str

class MobileEventResponse(BaseModel):
    id: UUID
    camera_name: str
    description: Optional[str]
    thumbnail_url: str
    created_at: datetime
    smart_detection_type: Optional[str]
```

### APIs and Interfaces

#### P8-4.3: Mobile Authentication Endpoints

**POST /api/v1/mobile/auth/pair**

Generate a 6-digit pairing code (call from web UI).

```
POST /api/v1/mobile/auth/pair

Request: None

Response (200):
{
  "pairing_code": "847291",
  "expires_at": "2025-12-20T12:05:00Z",
  "expires_in_seconds": 300
}
```

**POST /api/v1/mobile/auth/verify**

Verify pairing code and get tokens (call from iOS app).

```
POST /api/v1/mobile/auth/verify

Request:
{
  "pairing_code": "847291",
  "device_name": "iPhone 15 Pro",
  "device_id": "unique-device-uuid",
  "device_type": "iphone"
}

Response (200):
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "expires_in": 3600
}

Response (400 - expired):
{
  "detail": "Pairing code expired"
}

Response (400 - invalid):
{
  "detail": "Invalid pairing code"
}
```

**POST /api/v1/mobile/auth/refresh**

Refresh access token using refresh token.

```
POST /api/v1/mobile/auth/refresh

Request:
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "device_id": "unique-device-uuid"
}

Response (200):
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "expires_in": 3600
}

Response (401):
{
  "detail": "Invalid or expired refresh token"
}
```

#### P8-4.3: Mobile Events Endpoints

**GET /api/v1/mobile/events**

Get paginated events with mobile-optimized thumbnails.

```
GET /api/v1/mobile/events?page=1&limit=20

Headers:
Authorization: Bearer {access_token}

Response (200):
{
  "events": [
    {
      "id": "uuid",
      "camera_name": "Front Porch",
      "description": "Person approaching front door with package",
      "thumbnail_url": "/api/v1/mobile/events/{id}/thumbnail",
      "created_at": "2025-12-20T11:30:00Z",
      "smart_detection_type": "package"
    }
  ],
  "total": 156,
  "page": 1,
  "limit": 20,
  "has_next": true
}
```

**GET /api/v1/mobile/events/{event_id}**

Get single event detail.

```
GET /api/v1/mobile/events/{event_id}

Headers:
Authorization: Bearer {access_token}

Response (200):
{
  "id": "uuid",
  "camera_name": "Front Porch",
  "camera_id": "uuid",
  "description": "Person approaching front door with package",
  "thumbnail_url": "/api/v1/mobile/events/{id}/thumbnail",
  "created_at": "2025-12-20T11:30:00Z",
  "smart_detection_type": "package",
  "confidence_score": 0.92,
  "has_video": false
}
```

**GET /api/v1/mobile/events/{event_id}/thumbnail**

Get compressed thumbnail for mobile.

```
GET /api/v1/mobile/events/{event_id}/thumbnail

Headers:
Authorization: Bearer {access_token}

Response (200):
Content-Type: image/jpeg
Content-Length: 45000
[Binary JPEG data - max 50KB compressed]
```

**GET /api/v1/mobile/events/recent**

Get last N events for widgets/complications.

```
GET /api/v1/mobile/events/recent?limit=5

Headers:
Authorization: Bearer {access_token}

Response (200):
{
  "events": [
    {
      "id": "uuid",
      "camera_name": "Front Porch",
      "description": "Person...",
      "created_at": "2025-12-20T11:30:00Z"
    }
  ]
}
```

#### P8-4.3: Mobile Push Endpoints

**POST /api/v1/mobile/push/register**

Register APNS token for push notifications.

```
POST /api/v1/mobile/push/register

Headers:
Authorization: Bearer {access_token}

Request:
{
  "apns_token": "device-token-from-ios",
  "device_id": "unique-device-uuid"
}

Response (200):
{
  "registered": true
}
```

**DELETE /api/v1/mobile/push/unregister**

Unregister device from push notifications.

```
DELETE /api/v1/mobile/push/unregister

Headers:
Authorization: Bearer {access_token}

Request:
{
  "device_id": "unique-device-uuid"
}

Response (200):
{
  "unregistered": true
}
```

#### P8-4.3: Mobile Camera Endpoints

**GET /api/v1/mobile/cameras**

Get camera list with status.

```
GET /api/v1/mobile/cameras

Headers:
Authorization: Bearer {access_token}

Response (200):
{
  "cameras": [
    {
      "id": "uuid",
      "name": "Front Porch",
      "source_type": "protect",
      "is_online": true,
      "last_event_at": "2025-12-20T11:30:00Z"
    }
  ]
}
```

**GET /api/v1/mobile/cameras/{camera_id}/snapshot**

Get current camera snapshot (compressed for mobile).

```
GET /api/v1/mobile/cameras/{camera_id}/snapshot

Headers:
Authorization: Bearer {access_token}

Response (200):
Content-Type: image/jpeg
[Binary JPEG data - max 100KB compressed]
```

### Workflows and Sequencing

#### P8-4.1: Technology Research Workflow

```
Start Research
  → Evaluate SwiftUI vs React Native vs Flutter
    → Document pros/cons for each
    → Assess team skills and maintainability
    → Consider Apple platform requirements
  → Analyze per-platform considerations
    → iPhone: Push, widgets, background refresh
    → iPad: Split view, larger layouts
    → Watch: Complications, limited UI
    → TV: Focus navigation, remote control
    → macOS: Menu bar, notifications
  → Review API requirements
    → Authentication mechanisms
    → Real-time updates strategy
    → Image/video streaming approach
  → Document recommendation
    → Decision: SwiftUI (per architecture)
    → Rationale and trade-offs
  → Save to docs/research/apple-apps-technology.md
```

#### P8-4.2: Cloud Relay Design Workflow

```
Start Architecture Design
  → Define connection requirements
    → No port forwarding
    → NAT traversal
    → End-to-end encryption
  → Evaluate relay options
    → Cloudflare Tunnel (recommended)
    → Tailscale (advanced option)
    → AWS API Gateway
    → Self-hosted relay
  → Design authentication flow
    → Device pairing sequence
    → Token-based access
    → Certificate pinning
  → Document security considerations
    → Encryption approach
    → Rate limiting
    → Abuse prevention
  → Estimate costs per provider
  → Create sequence diagrams
  → Save to docs/architecture/cloud-relay-design.md
```

#### P8-4.3: Mobile API Specification Workflow

```
Start API Specification
  → Define authentication endpoints
    → /mobile/auth/pair
    → /mobile/auth/verify
    → /mobile/auth/refresh
  → Define mobile-optimized event endpoints
    → /mobile/events (paginated)
    → /mobile/events/{id}
    → /mobile/events/{id}/thumbnail
    → /mobile/events/recent
  → Define camera endpoints
    → /mobile/cameras
    → /mobile/cameras/{id}/snapshot
  → Define push registration endpoints
    → /mobile/push/register
    → /mobile/push/unregister
  → Document rate limits and quotas
  → Create OpenAPI/Swagger spec
  → Save to docs/api/mobile-api.yaml
```

#### P8-4.4: iPhone Prototype Workflow

```
Start Prototype Development
  → Create Xcode project
    → SwiftUI app structure
    → iOS 17 minimum target
  → Implement pairing flow
    → Code entry screen
    → Verification with backend
    → Keychain token storage
  → Build event list view
    → Fetch from /mobile/events
    → Display thumbnail + description
    → Pull-to-refresh
  → Build event detail view
    → Full description display
    → Larger thumbnail
  → Implement push notifications
    → Request permission
    → Register APNS token
    → Handle notification tap
  → Add local network discovery
    → Bonjour/mDNS lookup
    → Auto-connect when local
  → Test on physical device
  → Document findings and blockers
```

---

## Non-Functional Requirements

### Performance

| Requirement | Target | Measurement |
|-------------|--------|-------------|
| Pairing code generation | <100ms | API response time |
| Token verification | <200ms | API response time |
| Mobile event list load | <1 second | Including thumbnails |
| Compressed thumbnail size | <50KB | JPEG quality 60 |
| Push notification delivery | <5 seconds | From event to device |

### Security

- Pairing codes expire after 5 minutes
- Single-use pairing codes (deleted after verification)
- Access tokens expire after 1 hour
- Refresh tokens expire after 30 days
- Refresh tokens rotated on each use
- Tokens bound to device_id
- All traffic encrypted (TLS 1.3)
- iOS Keychain for credential storage
- Certificate pinning for API calls

### Reliability/Availability

- Local network fallback when cloud relay unavailable
- Graceful degradation if push notifications fail
- Automatic token refresh before expiry
- Retry logic for transient network errors

### Observability

| Metric | Type | Description |
|--------|------|-------------|
| `mobile_pairing_requests` | Counter | Pairing code requests |
| `mobile_pairing_success` | Counter | Successful pairings |
| `mobile_pairing_failed` | Counter | Failed pairings |
| `mobile_token_refresh` | Counter | Token refresh requests |
| `mobile_push_sent` | Counter | Push notifications sent |
| `mobile_api_requests` | Histogram | Request latency by endpoint |

---

## Dependencies and Integrations

### Backend Dependencies

```
# requirements.txt additions
PyJWT>=2.8.0                # JWT token generation
PyAPNs2>=0.8.0              # Apple Push Notification service
cryptography>=41.0.0        # Token signing (existing)
```

### Frontend Dependencies

```json
// package.json - no changes
// Pairing code generation UI uses existing components
```

### iOS Dependencies

```swift
// Swift Package Manager
// swift-collections (Apple)
// KeychainAccess (for simplified Keychain)
```

### External Integrations

| Integration | Purpose | Story |
|-------------|---------|-------|
| Apple Push Notification service (APNS) | iOS push notifications | P8-4.3, P8-4.4 |
| Cloudflare Tunnel | Remote access relay | P8-4.2 |
| Tailscale (optional) | VPN-based access | P8-4.2 |

---

## Acceptance Criteria (Authoritative)

### P8-4.1: Research Native Apple App Technologies

| AC# | Acceptance Criteria |
|-----|---------------------|
| AC1.1 | Given research complete, when document reviewed, then SwiftUI vs React Native vs Flutter comparison included |
| AC1.2 | Given research complete, when document reviewed, then per-platform considerations documented (iPhone, iPad, Watch, TV, macOS) |
| AC1.3 | Given research complete, when document reviewed, then pros/cons table for each approach included |
| AC1.4 | Given research complete, when document reviewed, then development effort estimates per platform provided |
| AC1.5 | Given research complete, when document reviewed, then clear recommendation with rationale documented |
| AC1.6 | Given research complete, then document saved to `docs/research/apple-apps-technology.md` |

### P8-4.2: Design Cloud Relay Architecture

| AC# | Acceptance Criteria |
|-----|---------------------|
| AC2.1 | Given design complete, when document reviewed, then connection flow (app → relay → local) diagrammed |
| AC2.2 | Given design complete, when document reviewed, then authentication/pairing mechanism documented |
| AC2.3 | Given design complete, when document reviewed, then Cloudflare Tunnel + Tailscale options compared |
| AC2.4 | Given design complete, when document reviewed, then security considerations addressed |
| AC2.5 | Given design complete, when document reviewed, then cost estimates per provider included |
| AC2.6 | Given design complete, when document reviewed, then sequence diagrams for key flows included |
| AC2.7 | Given design complete, then document saved to `docs/architecture/cloud-relay-design.md` |

### P8-4.3: Create ArgusAI API Specification for Mobile

| AC# | Acceptance Criteria |
|-----|---------------------|
| AC3.1 | Given API spec complete, when reviewed, then authentication endpoints documented (pair, verify, refresh) |
| AC3.2 | Given API spec complete, when reviewed, then mobile events endpoints documented with pagination |
| AC3.3 | Given API spec complete, when reviewed, then camera endpoints documented (list, snapshot) |
| AC3.4 | Given API spec complete, when reviewed, then push registration endpoints documented |
| AC3.5 | Given API spec complete, when reviewed, then response schemas defined for all endpoints |
| AC3.6 | Given API spec complete, when reviewed, then rate limits documented per endpoint |
| AC3.7 | Given API spec complete, when reviewed, then bandwidth estimates included |
| AC3.8 | Given API spec complete, then OpenAPI spec saved to `docs/api/mobile-api.yaml` |

### P8-4.4: Prototype iPhone App Structure

| AC# | Acceptance Criteria |
|-----|---------------------|
| AC4.1 | Given prototype complete, when launched, then login/pairing screen with code entry functional |
| AC4.2 | Given valid pairing code, when entered, then tokens received and stored in Keychain |
| AC4.3 | Given authenticated, when viewing, then event list shows recent events with thumbnails |
| AC4.4 | Given event list, when tapping event, then detail view shows full description |
| AC4.5 | Given authenticated, when pull-to-refresh, then event list updates |
| AC4.6 | Given push permission granted, when event occurs, then push notification received |
| AC4.7 | Given push notification, when tapped, then app opens to relevant event |
| AC4.8 | Given network error, when retrying, then error handled gracefully with retry UI |
| AC4.9 | Given local network, when available, then app discovers local ArgusAI via Bonjour |
| AC4.10 | Given prototype complete, then findings and blockers documented |

---

## Traceability Mapping

| AC | Spec Section | Component(s) | Test Idea |
|----|--------------|--------------|-----------
| AC1.1-1.5 | Workflows | Research document | Review checklist |
| AC1.6 | Workflows | docs/research/ | Verify file exists |
| AC2.1-2.6 | Workflows | Architecture document | Review checklist |
| AC2.7 | Workflows | docs/architecture/ | Verify file exists |
| AC3.1-3.7 | APIs | mobile_api.yaml, mobile/ routes | OpenAPI validation |
| AC3.8 | APIs | docs/api/ | Verify OpenAPI spec valid |
| AC4.1-4.2 | Workflows | iOS app, MobileAuthService | Manual test pairing flow |
| AC4.3-4.5 | Workflows | iOS app, mobile events API | Manual test event list |
| AC4.6-4.7 | Workflows | iOS app, APNS | Manual test on device |
| AC4.8 | Reliability | iOS app | Manual test offline mode |
| AC4.9 | Workflows | iOS app | Manual test local discovery |
| AC4.10 | Workflows | Documentation | Review findings doc |

---

## Risks, Assumptions, Open Questions

### Risks

| ID | Risk | Impact | Mitigation |
|----|------|--------|------------|
| R1 | Apple Developer Account required for device testing | Medium | Use simulator initially, acquire account before P8-4.4 |
| R2 | APNS setup complexity | Medium | Follow Apple documentation, test in sandbox first |
| R3 | Cloudflare Tunnel may change free tier | Low | Document Tailscale as fallback |
| R4 | SwiftUI learning curve for team | Medium | Start with simple views, use Apple documentation |

### Assumptions

| ID | Assumption |
|----|------------|
| A1 | macOS available for iOS development |
| A2 | Apple Developer Account available or acquirable |
| A3 | Cloudflare Tunnel free tier sufficient for initial use |
| A4 | Users have iOS 17+ devices |
| A5 | Local network has mDNS/Bonjour enabled |

### Open Questions

| ID | Question | Owner | Status |
|----|----------|-------|--------|
| Q1 | Should we support iOS 16? | PM | Decided: No, iOS 17+ only |
| Q2 | Do we need Android support? | PM | Decided: Out of scope for Phase 8 |
| Q3 | What's the APNS certificate type (development vs production)? | Dev | To decide during P8-4.4 |
| Q4 | Should relay be required or optional for local-only users? | PM | To discuss |

---

## Test Strategy Summary

### Test Levels

| Level | Framework | Coverage |
|-------|-----------|----------|
| Unit | pytest | MobileAuthService, token generation |
| Integration | pytest + TestClient | Mobile API endpoints |
| Component | XCTest | iOS app screens |
| E2E | Manual | Full pairing and event flow |

### Key Test Cases

**P8-4.1 (Research):**
- Manual review against checklist
- Document completeness verification

**P8-4.2 (Cloud Relay Design):**
- Manual review against checklist
- Diagram accuracy verification

**P8-4.3 (API Spec):**
- `test_pairing_code_generation`
- `test_pairing_code_verification`
- `test_pairing_code_expiry`
- `test_token_refresh`
- `test_mobile_events_pagination`
- `test_mobile_thumbnail_compression`
- `test_apns_registration`
- OpenAPI spec validation

**P8-4.4 (Prototype):**
- Manual: Pairing flow on device
- Manual: Event list and detail
- Manual: Push notification receipt
- Manual: Local network discovery
- XCTest: View model logic
- XCTest: API client parsing

### Edge Cases

- Pairing code entered after expiry
- Pairing code entered incorrectly
- Network timeout during pairing
- Refresh token expired
- Push notification when app in background
- Local network unavailable
- Cloud relay unavailable
- Device ID collision (multiple devices)
- Token replay attacks

---

## Appendix: iOS Project Structure

```
ios-app/
├── ArgusAI/
│   ├── ArgusAIApp.swift           # App entry point
│   ├── Models/
│   │   ├── Event.swift            # Event model
│   │   ├── Camera.swift           # Camera model
│   │   └── AuthToken.swift        # Token model
│   ├── Services/
│   │   ├── APIClient.swift        # HTTP client
│   │   ├── AuthService.swift      # Auth/pairing logic
│   │   ├── KeychainService.swift  # Secure storage
│   │   └── PushService.swift      # APNS handling
│   ├── Views/
│   │   ├── PairingView.swift      # Code entry screen
│   │   ├── EventListView.swift    # Event list
│   │   ├── EventDetailView.swift  # Event detail
│   │   └── SettingsView.swift     # App settings
│   ├── ViewModels/
│   │   ├── PairingViewModel.swift
│   │   ├── EventListViewModel.swift
│   │   └── EventDetailViewModel.swift
│   └── Resources/
│       ├── Assets.xcassets
│       └── Info.plist
├── ArgusAI.xcodeproj
└── README.md
```

---

## Appendix: Pairing Code Flow Diagram

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   ArgusAI Web   │     │  ArgusAI Backend│     │   iOS App       │
│   (Browser)     │     │                 │     │                 │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         │ 1. Click "Pair Device"│                       │
         │──────────────────────>│                       │
         │                       │                       │
         │    2. Generate Code   │                       │
         │    (847291, 5min TTL) │                       │
         │<──────────────────────│                       │
         │                       │                       │
         │ 3. Display "847291"   │                       │
         │    to User            │                       │
         │                       │                       │
         │                       │    4. User enters     │
         │                       │    "847291" in app    │
         │                       │<──────────────────────│
         │                       │                       │
         │                       │    5. Verify code,    │
         │                       │    create device,     │
         │                       │    return tokens      │
         │                       │──────────────────────>│
         │                       │                       │
         │                       │    6. Store tokens    │
         │                       │    in Keychain        │
         │                       │                       │
         │                       │    7. Navigate to     │
         │                       │    Event List         │
         │                       │                       │
```
