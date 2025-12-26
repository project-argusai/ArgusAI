# Phase 11 Architecture Additions

**Phase:** 11 - Mobile Platform & Remote Access
**Date:** 2025-12-25
**PRD:** docs/PRD-phase11.md
**Epics:** docs/epics-phase11.md

---

## Phase 11 Executive Summary

Phase 11 implements the mobile infrastructure designed in Phase 10, adding:

- **Remote Access Implementation** via Cloudflare Tunnel (design was completed in P10)
- **Mobile Push Notifications** with APNS (iOS) and FCM (Android) providers
- **AI Context Enhancement** through MCPContextProvider
- **Query-Adaptive Frame Selection** for targeted re-analysis
- **Platform Polish** including camera list optimization and documentation

---

## Phase 11 Technology Stack Additions

| Component | Technology | Version | Purpose |
|-----------|------------|---------|---------|
| Tunnel Client | cloudflared | 2024.x | Cloudflare Tunnel daemon |
| HTTP/2 Client | httpx | 0.26+ | APNS HTTP/2 connections |
| APNS Auth | PyJWT | 2.8+ | JWT signing for APNS |
| FCM Client | firebase-admin | 6.4+ | FCM HTTP v1 API |
| Virtual Scroll | react-window | 1.8+ | Camera list performance |
| Static Site | Docusaurus | 3.x | GitHub Pages documentation |

---

## Phase 11 Project Structure Additions

```
backend/
├── app/
│   ├── services/
│   │   ├── push/
│   │   │   ├── __init__.py
│   │   │   ├── apns_provider.py      # P11-2.1: iOS push
│   │   │   ├── fcm_provider.py       # P11-2.2: Android push
│   │   │   ├── dispatch_service.py   # P11-2.3: Unified routing
│   │   │   └── token_manager.py      # P11-2.4: Device tokens
│   │   ├── signed_url_service.py     # P11-2.6: Signed thumbnail URLs
│   │   ├── tunnel_service.py         # P11-1.1: Cloudflare Tunnel
│   │   └── mcp_context.py            # P11-3.1: Context provider
│   ├── api/v1/
│   │   ├── devices.py                # P11-2.4: Device registration
│   │   └── tunnel.py                 # P11-1.2: Tunnel status
│   └── models/
│       ├── device.py                 # P11-2.4: Device model
│       └── frame_embedding.py        # P11-4.2: Frame embeddings

frontend/
├── components/
│   ├── settings/
│   │   └── TunnelSettings.tsx        # P11-1.3: Tunnel config UI
│   └── cameras/
│       └── CameraListVirtual.tsx     # P11-5.1: Virtual scrolling

docs-site/                            # P11-5.3: GitHub Pages
├── docusaurus.config.js
├── docs/
│   ├── installation.md
│   ├── configuration.md
│   └── api-reference.md
└── static/
```

---

## Phase 11 Database Schema Additions

### Device Model (P11-2.4)

```python
class Device(Base):
    __tablename__ = "devices"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    device_id = Column(String(255), unique=True, nullable=False)  # UUID from device
    platform = Column(String(20), nullable=False)  # ios, android, web
    name = Column(String(100))  # User-friendly name
    push_token = Column(Text)  # Encrypted APNS/FCM token
    last_seen_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="devices")
```

### FrameEmbedding Model (P11-4.2)

```python
class FrameEmbedding(Base):
    __tablename__ = "frame_embeddings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(36), ForeignKey("events.id"), nullable=False)
    frame_index = Column(Integer, nullable=False)
    embedding = Column(JSON, nullable=False)  # [float, ...] - 512/768 dimensions
    model_version = Column(String(50), nullable=False)  # e.g., "clip-vit-base-patch32"
    created_at = Column(DateTime, default=datetime.utcnow)

    # Composite index for queries
    __table_args__ = (
        Index('ix_frame_embeddings_event_frame', 'event_id', 'frame_index'),
    )
```

### NotificationPreferences Extensions (P11-2.5)

```python
# Add to existing NotificationPreferences model
quiet_hours_start = Column(Time)  # e.g., 22:00
quiet_hours_end = Column(Time)    # e.g., 07:00
quiet_hours_timezone = Column(String(50))  # e.g., "America/Chicago"
quiet_hours_enabled = Column(Boolean, default=False)
```

---

## Phase 11 Service Architecture

### Push Notification Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Event Processor                               │
│                              │                                       │
│                              ▼                                       │
│                   ┌─────────────────────┐                           │
│                   │  PushDispatchService │                          │
│                   │  (dispatch_service)  │                          │
│                   └──────────┬──────────┘                           │
│                              │                                       │
│           ┌──────────────────┼──────────────────┐                   │
│           ▼                  ▼                  ▼                   │
│   ┌───────────────┐  ┌───────────────┐  ┌───────────────┐          │
│   │ WebPushService│  │  APNSProvider │  │  FCMProvider  │          │
│   │  (existing)   │  │  (new P11)    │  │  (new P11)    │          │
│   └───────┬───────┘  └───────┬───────┘  └───────┬───────┘          │
│           │                  │                  │                   │
│           ▼                  ▼                  ▼                   │
│       Web Push           Apple APNS         Google FCM              │
│       Server             HTTP/2 API         HTTP v1 API             │
└─────────────────────────────────────────────────────────────────────┘
```

### APNS Provider (P11-2.1)

```python
class APNSProvider:
    """iOS Push Notification provider using Apple Push Notification Service."""

    def __init__(self, config: APNSConfig):
        self.team_id = config.team_id
        self.key_id = config.key_id
        self.key_path = config.key_path
        self.bundle_id = config.bundle_id
        self.sandbox = config.sandbox  # True for development
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_jwt_token(self) -> str:
        """Generate JWT for APNS authentication (valid for 1 hour)."""
        with open(self.key_path, 'r') as f:
            private_key = f.read()

        payload = {
            'iss': self.team_id,
            'iat': int(time.time())
        }
        headers = {
            'kid': self.key_id,
            'alg': 'ES256'
        }
        return jwt.encode(payload, private_key, algorithm='ES256', headers=headers)

    async def send(self, token: str, payload: APNSPayload) -> DeliveryResult:
        """Send push notification to iOS device."""
        url = f"https://api.push.apple.com/3/device/{token}"
        if self.sandbox:
            url = f"https://api.sandbox.push.apple.com/3/device/{token}"

        headers = {
            'apns-topic': self.bundle_id,
            'apns-push-type': 'alert',
            'apns-priority': '10',
            'authorization': f'bearer {await self._get_jwt_token()}'
        }

        async with self._get_client() as client:
            response = await client.post(url, json=payload.dict(), headers=headers)
            return self._handle_response(response, token)
```

### FCM Provider (P11-2.2)

```python
class FCMProvider:
    """Android Push Notification provider using Firebase Cloud Messaging."""

    def __init__(self, config: FCMConfig):
        self.project_id = config.project_id
        self.credentials_path = config.credentials_path
        self._initialize_firebase()

    def _initialize_firebase(self):
        """Initialize Firebase Admin SDK."""
        cred = credentials.Certificate(self.credentials_path)
        firebase_admin.initialize_app(cred)

    async def send(self, token: str, payload: FCMPayload) -> DeliveryResult:
        """Send push notification to Android device."""
        message = messaging.Message(
            notification=messaging.Notification(
                title=payload.title,
                body=payload.body,
                image=payload.image_url,
            ),
            data=payload.data,
            token=token,
            android=messaging.AndroidConfig(
                priority='high',
                notification=messaging.AndroidNotification(
                    channel_id='argusai_events',
                    icon='ic_notification',
                ),
            ),
        )

        try:
            response = await asyncio.to_thread(messaging.send, message)
            return DeliveryResult(success=True, message_id=response)
        except messaging.UnregisteredError:
            return DeliveryResult(success=False, error='token_invalid')
        except Exception as e:
            return DeliveryResult(success=False, error=str(e))
```

### Unified Push Dispatch (P11-2.3)

```python
class PushDispatchService:
    """Routes notifications to appropriate push providers."""

    def __init__(
        self,
        web_push: WebPushService,
        apns: Optional[APNSProvider],
        fcm: Optional[FCMProvider],
        db: AsyncSession,
    ):
        self.web_push = web_push
        self.apns = apns
        self.fcm = fcm
        self.db = db

    async def dispatch(
        self,
        user_id: str,
        notification: EventNotification,
    ) -> DispatchResult:
        """Send notification to all user's devices."""
        # Get user's devices and preferences
        devices = await self._get_user_devices(user_id)
        preferences = await self._get_notification_preferences(user_id)

        # Check quiet hours
        if self._is_quiet_hours(preferences):
            if not notification.is_critical:
                return DispatchResult(skipped=True, reason="quiet_hours")

        # Dispatch to all devices in parallel
        tasks = []
        for device in devices:
            if device.platform == 'web' and self.web_push:
                tasks.append(self._send_web_push(device, notification))
            elif device.platform == 'ios' and self.apns:
                tasks.append(self._send_apns(device, notification))
            elif device.platform == 'android' and self.fcm:
                tasks.append(self._send_fcm(device, notification))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        return DispatchResult(
            sent=len([r for r in results if r.success]),
            failed=len([r for r in results if not r.success]),
            details=results,
        )
```

### Notification Thumbnail Attachments (P11-2.6)

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Thumbnail Attachment Flow                        │
│                                                                      │
│  Event Created ─► Thumbnail Saved ─► Push Dispatch                   │
│                                            │                         │
│                         ┌──────────────────┼──────────────────┐     │
│                         ▼                  ▼                  ▼     │
│                    Optimize           Generate          Verify       │
│                    Thumbnail          Signed URL        Thumbnail    │
│                   (≤1MB, 1024px)     (HMAC-SHA256)     File Exists   │
│                         │                  │                  │     │
│                         └──────────────────┼──────────────────┘     │
│                                            ▼                         │
│                                     Include in Payload               │
│                                            │                         │
│                         ┌──────────────────┼──────────────────┐     │
│                         ▼                  ▼                  ▼     │
│                       APNS              FCM             Fallback     │
│                  (mutable-content)  (BigPicture)    (text-only)     │
│                         │                  │                         │
│                         ▼                  ▼                         │
│                   iOS NSE           Android SDK                      │
│                  Downloads         Auto-downloads                    │
│                   Attaches          & Displays                       │
└─────────────────────────────────────────────────────────────────────┘
```

**Signed URL Service:**

```python
class SignedURLService:
    """Generates time-limited signed URLs for secure thumbnail access."""

    def generate_signed_url(
        self,
        event_id: str,
        base_url: str,
        expiration_seconds: int = 60,
    ) -> str:
        """
        Generate HMAC-SHA256 signed URL for thumbnail.

        URL format: {base_url}/api/v1/events/{event_id}/thumbnail?signature={sig}&expires={ts}
        """
        expires = int(time.time()) + expiration_seconds
        message = f"{event_id}:{expires}".encode()
        signature = hmac.new(secret_key, message, hashlib.sha256).hexdigest()
        return f"{base_url}/api/v1/events/{event_id}/thumbnail?signature={signature}&expires={expires}"

    def verify_signed_url(self, event_id: str, signature: str, expires: int) -> bool:
        """Verify URL signature and expiration."""
        if time.time() > expires:
            return False  # Expired
        expected = hmac.new(secret_key, f"{event_id}:{expires}".encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)
```

**Image Optimization:**

- Maximum dimension: 1024x1024px (maintains aspect ratio)
- Maximum file size: 1MB
- JPEG quality: 80 (reduced to 20 if needed for size)
- Cached with `_notification` suffix to avoid re-processing

**Platform-Specific Handling:**

| Platform | Mechanism | Maximum Size | Notes |
|----------|-----------|--------------|-------|
| iOS | Notification Service Extension | ~10MB | App must implement UNNotificationServiceExtension |
| Android | FCM BigPicture style | 1MB recommended | SDK auto-downloads image |
| Web | Web Push image field | 1MB | Browser displays automatically |

**Fallback Behavior (AC-2.6.5):**

- Missing thumbnail file → Send text-only notification
- Optimization failure → Use original thumbnail
- Signed URL failure → Send without image
- All failures logged with structured metadata

### MCP Context Provider (P11-3.1)

```python
class MCPContextProvider:
    """Provides context for AI prompts based on accumulated knowledge."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._cache: Dict[str, CachedContext] = {}
        self._cache_ttl = 60  # seconds

    async def get_context(
        self,
        camera_id: str,
        event_time: datetime,
        entity_id: Optional[str] = None,
    ) -> AIContext:
        """
        Gather context for AI prompt generation.

        Includes:
        - Feedback history (recent corrections, accuracy stats)
        - Entity context (if entity matched)
        - Camera context (location hints, typical activity)
        - Time patterns (unusual timing detection)
        """
        cache_key = f"{camera_id}:{event_time.hour}"
        if cached := self._get_cached(cache_key):
            return cached

        # Gather context in parallel for speed
        feedback_ctx, entity_ctx, camera_ctx, time_ctx = await asyncio.gather(
            self._get_feedback_context(camera_id),
            self._get_entity_context(entity_id) if entity_id else asyncio.sleep(0),
            self._get_camera_context(camera_id),
            self._get_time_context(camera_id, event_time),
            return_exceptions=True,  # Fail-open
        )

        context = AIContext(
            feedback=feedback_ctx if not isinstance(feedback_ctx, Exception) else None,
            entity=entity_ctx if not isinstance(entity_ctx, Exception) else None,
            camera=camera_ctx if not isinstance(camera_ctx, Exception) else None,
            time_pattern=time_ctx if not isinstance(time_ctx, Exception) else None,
        )

        self._cache[cache_key] = CachedContext(context, datetime.utcnow())
        return context

    async def _get_feedback_context(self, camera_id: str) -> FeedbackContext:
        """Get recent feedback and accuracy stats for camera."""
        # Query recent feedback (last 50)
        recent = await self.db.execute(
            select(EventFeedback)
            .join(Event)
            .where(Event.camera_id == camera_id)
            .order_by(EventFeedback.created_at.desc())
            .limit(50)
        )
        feedbacks = recent.scalars().all()

        # Calculate accuracy
        total = len(feedbacks)
        positive = sum(1 for f in feedbacks if f.is_positive)

        # Extract common corrections
        corrections = [f.correction_text for f in feedbacks if f.correction_text]
        common_corrections = self._extract_common_patterns(corrections)

        return FeedbackContext(
            accuracy_rate=positive / total if total > 0 else None,
            total_feedback=total,
            common_corrections=common_corrections,
        )

    def format_for_prompt(self, context: AIContext) -> str:
        """Format context for inclusion in AI prompt."""
        parts = []

        if context.feedback and context.feedback.accuracy_rate:
            parts.append(
                f"Previous accuracy for this camera: {context.feedback.accuracy_rate:.0%}"
            )
            if context.feedback.common_corrections:
                parts.append(
                    f"Common corrections: {', '.join(context.feedback.common_corrections[:3])}"
                )

        if context.entity:
            parts.append(f"Known entity: {context.entity.name} ({context.entity.type})")

        if context.camera and context.camera.location_hint:
            parts.append(f"Camera location: {context.camera.location_hint}")

        if context.time_pattern and context.time_pattern.is_unusual:
            parts.append("Note: This is unusual activity for this time of day")

        return "\n".join(parts) if parts else ""
```

---

## Phase 11 API Contracts

### Device Registration API (P11-2.4)

```yaml
/api/v1/devices:
  get:
    summary: List registered devices
    responses:
      200:
        content:
          application/json:
            schema:
              type: object
              properties:
                devices:
                  type: array
                  items:
                    $ref: '#/components/schemas/Device'

  post:
    summary: Register new device
    requestBody:
      content:
        application/json:
          schema:
            type: object
            required: [device_id, platform, push_token]
            properties:
              device_id:
                type: string
                description: Unique device identifier
              platform:
                type: string
                enum: [ios, android, web]
              name:
                type: string
              push_token:
                type: string
                description: APNS/FCM/Web Push token
    responses:
      201:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Device'

/api/v1/devices/{device_id}:
  delete:
    summary: Remove device registration
    responses:
      204:
        description: Device removed
```

### Tunnel Status API (P11-1.2)

```yaml
/api/v1/system/tunnel-status:
  get:
    summary: Get Cloudflare Tunnel status
    responses:
      200:
        content:
          application/json:
            schema:
              type: object
              properties:
                enabled:
                  type: boolean
                connected:
                  type: boolean
                tunnel_id:
                  type: string
                hostname:
                  type: string
                last_connected:
                  type: string
                  format: date-time
                error:
                  type: string
```

### Smart Re-analyze API (P11-4.3)

```yaml
/api/v1/events/{event_id}/smart-reanalyze:
  post:
    summary: Re-analyze event with query-focused frame selection
    parameters:
      - name: event_id
        in: path
        required: true
        schema:
          type: string
      - name: query
        in: query
        required: true
        schema:
          type: string
        description: Question to focus analysis on (e.g., "Was there a package?")
    responses:
      200:
        content:
          application/json:
            schema:
              type: object
              properties:
                description:
                  type: string
                frames_analyzed:
                  type: integer
                frame_scores:
                  type: array
                  items:
                    type: object
                    properties:
                      frame_index:
                        type: integer
                      relevance_score:
                        type: number
                selection_time_ms:
                  type: number
```

---

## Phase 11 ADRs

### ADR-P11-001: Cloudflare Tunnel over Self-Hosted Relay

**Status:** Accepted

**Context:** Need secure remote access without port forwarding.

**Decision:** Use Cloudflare Tunnel as primary remote access solution.

**Rationale:**
- Free tier sufficient for personal use
- No server infrastructure to manage
- Automatic TLS, global edge network
- Zero Trust capabilities available
- Simpler than AWS IoT or self-hosted frp

**Consequences:**
- Requires Cloudflare account and domain on Cloudflare DNS
- Dependency on Cloudflare infrastructure
- cloudflared daemon must run on ArgusAI server

---

### ADR-P11-002: Native Push Providers vs Unified Gateway

**Status:** Accepted

**Context:** Could use a unified push gateway service (e.g., OneSignal, Pusher) vs native APNS/FCM.

**Decision:** Implement native APNS and FCM providers.

**Rationale:**
- No third-party service dependency or costs
- Full control over notification format and delivery
- Local-first philosophy - no data goes through third parties
- Native providers support all features (attachments, silent push)

**Consequences:**
- Must maintain separate APNS and FCM code
- Requires managing Apple/Google credentials
- More complex setup for users

---

### ADR-P11-003: MCP Context via Database vs External MCP Server

**Status:** Accepted

**Context:** Could implement full MCP protocol server or simpler database-backed context.

**Decision:** Start with MCPContextProvider class querying local database.

**Rationale:**
- Simpler implementation, faster to market
- No external dependencies
- Can evolve to full MCP protocol in future
- 50ms target achievable with local queries

**Consequences:**
- Not compatible with external MCP clients (Claude Desktop) initially
- Future work needed for full protocol compliance
- Context limited to ArgusAI's own data

---

### ADR-P11-004: CLIP for Frame Embeddings

**Status:** Accepted

**Context:** Need to encode frames for query-based selection.

**Decision:** Reuse existing CLIP model (ViT-B/32) from EmbeddingService.

**Rationale:**
- Already deployed for entity embedding
- Text-image alignment enables query matching
- 512-dim embeddings are compact and fast
- No additional model deployment needed

**Consequences:**
- Frame embeddings ~2KB each (512 floats)
- 5 frames per event = ~10KB per event
- Query encoding adds ~50ms latency

---

## Phase 11 Performance Considerations

### Push Notification Delivery

| Metric | Target | Measurement |
|--------|--------|-------------|
| Dispatch latency | <100ms | Time to send to all providers |
| APNS delivery | <1s | Apple's SLA |
| FCM delivery | <1s | Google's SLA |
| Total event-to-notification | <3s | End-to-end target |

### MCP Context Gathering

| Metric | Target | Measurement |
|--------|--------|-------------|
| Context query (cached) | <5ms | Cache hit |
| Context query (uncached) | <50ms | Parallel DB queries |
| Context format for prompt | <1ms | String building |

### Query-Adaptive Selection

| Metric | Target | Measurement |
|--------|--------|-------------|
| Text encoding | <30ms | CLIP text encoder |
| Similarity scoring | <20ms | Cosine on 5-10 frames |
| Total selection overhead | <60ms | End-to-end |

---

## Phase 11 Epic to Architecture Mapping

| Epic | Components | Services |
|------|------------|----------|
| P11-1: Remote Access | TunnelSettings.tsx, tunnel.py | TunnelService |
| P11-2: Mobile Push | devices.py, push/* | APNSProvider, FCMProvider, PushDispatchService |
| P11-3: AI Context | context_prompt_service.py | MCPContextProvider |
| P11-4: Query-Adaptive | events.py, embedding_service.py | EmbeddingService, FrameEmbedding |
| P11-5: Polish | CameraListVirtual.tsx, cameras.py | N/A |

---

## Phase 11 Validation Checklist

### Remote Access (P11-1)
- [ ] Cloudflare Tunnel connects and maintains connection
- [ ] Tunnel auto-reconnects on network changes
- [ ] Settings UI shows tunnel status
- [ ] Documentation covers setup process

### Mobile Push (P11-2)
- [ ] APNS sends notifications to iOS devices
- [ ] FCM sends notifications to Android devices
- [ ] Dispatch service routes to correct provider
- [ ] Device registration stores encrypted tokens
- [ ] Quiet hours suppress non-critical notifications
- [ ] Thumbnails appear in notifications

### AI Context (P11-3)
- [ ] Feedback context gathered in <50ms
- [ ] Entity context included when matched
- [ ] Camera location hints in prompts
- [ ] Time pattern detection works
- [ ] Fail-open when context unavailable

### Query-Adaptive (P11-4)
- [ ] Text queries encoded correctly
- [ ] Frame embeddings generated on extraction
- [ ] Cosine similarity ranks frames
- [ ] Smart-reanalyze endpoint works
- [ ] Selection overhead <60ms

### Platform Polish (P11-5)
- [ ] Camera list scrolls smoothly with 100 cameras
- [ ] Test connection validates before save
- [ ] GitHub Pages site deploys on push
- [ ] CSV export downloads correctly

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-12-25 | Initial Phase 11 architecture document |
