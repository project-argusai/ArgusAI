---
sidebar_position: 3
---

# Native Apple Apps

ArgusAI is developing native apps for iPhone, iPad, Apple Watch, Apple TV, and macOS using SwiftUI.

## Status

The native Apple apps are currently in the **planning and architecture phase**:

- **SwiftUI**: Selected as the development framework for best native experience
- **Cloud Relay**: Cloudflare Tunnel architecture designed for secure remote access
- **API Specification**: Mobile-optimized API endpoints defined

## Planned Features

### iPhone & iPad

- **Event Timeline**: Browse security events with thumbnails
- **Push Notifications**: Rich notifications with event images
- **Home Screen Widgets**: Quick status at a glance
- **Siri Shortcuts**: "What happened at the front door?"
- **Face ID/Touch ID**: Secure authentication
- **Offline Support**: View cached events without connection

### Apple Watch

- **Complications**: Event count and camera status on watch face
- **Glanceable Alerts**: Quick event summaries on your wrist
- **Haptic Feedback**: Distinct vibrations for different event types
- **Quick Actions**: Acknowledge alerts directly from Watch

### Apple TV

- **Dashboard View**: Full-screen event timeline for living room
- **Video Playback**: View motion clips on the big screen
- **Camera Grid**: Live preview of all cameras
- **Top Shelf**: Recent events for quick access
- **Siri Remote**: Voice control and navigation

### macOS

- **Menu Bar App**: Quick access to recent events
- **Notifications**: Native notification center integration
- **Keyboard Shortcuts**: Power user navigation
- **Multiple Windows**: View different cameras simultaneously

## Cloud Relay Architecture

Native apps connect to your ArgusAI instance securely without port forwarding.

### How It Works

```
┌─────────────┐         ┌─────────────────┐       ┌───────────┐
│   iOS App   │◄───────►│  Cloud Relay    │◄─────►│  ArgusAI  │
│  (Mobile)   │  HTTPS  │  (Cloudflare)   │ Tunnel│  (Local)  │
└─────────────┘         └─────────────────┘       └───────────┘
```

### Key Benefits

- **No Port Forwarding**: Works behind any router/firewall
- **End-to-End Encryption**: TLS 1.3 for all traffic
- **Automatic Failover**: Falls back to local network when available
- **DDoS Protection**: Cloudflare's edge network security

### Local Network Fallback

When your device is on the same network as ArgusAI:

1. App discovers ArgusAI via Bonjour/mDNS
2. Automatically switches to direct local connection
3. Lower latency, no cloud relay needed
4. Seamless transition back to cloud when leaving home

## Device Pairing

### Pairing Process

1. Open ArgusAI web UI on your computer
2. Go to **Settings > Mobile Devices**
3. Click **Pair New Device**
4. A 6-digit code appears (valid for 5 minutes)
5. Open ArgusAI app on your iPhone
6. Enter the pairing code
7. Device is now connected!

### Security

- **6-Digit Codes**: Single-use, 5-minute expiry
- **JWT Authentication**: 1-hour access tokens, 30-day refresh
- **Device Binding**: Tokens tied to specific device
- **Token Rotation**: Refresh tokens rotate on each use
- **iOS Keychain**: Secure credential storage

## Technology Decisions

### Why SwiftUI?

| Feature | SwiftUI | React Native | Flutter |
|---------|---------|--------------|---------|
| Apple Platform Support | Full | Limited | None (Watch/TV) |
| Native Performance | Excellent | Good | Good |
| HomeKit Integration | Native | Very Limited | Not Available |
| Apple API Access | Complete | Limited | Limited |
| Code Sharing (Apple) | 60-80% | Poor | Poor |

SwiftUI was selected for:

1. **Full platform coverage** - All Apple devices with shared code
2. **Native HomeKit** - Seamless integration with existing features
3. **Best performance** - No bridge overhead
4. **Future-proof** - Apple's strategic UI framework

### Why Cloudflare Tunnel?

| Provider | Free Tier | Setup | NAT Traversal |
|----------|-----------|-------|---------------|
| Cloudflare Tunnel | Yes | Easy | Excellent |
| Tailscale | Limited | Medium | Excellent |
| AWS API Gateway | No | Complex | Via EC2 |

Cloudflare Tunnel was selected for:

1. **Free for home use** - No subscription required
2. **Simple setup** - Single daemon on ArgusAI server
3. **Built-in security** - DDoS protection, TLS certificates
4. **Global CDN** - Low latency from anywhere

## Roadmap

### Phase 1: iPhone MVP

- Pairing flow
- Event list and detail views
- Push notifications
- Local network discovery

### Phase 2: iPad + Polish

- Adaptive layouts for larger screens
- Split view and multitasking
- App Store preparation

### Phase 3: Apple Watch

- Complications
- Notification responses
- Quick glance views

### Phase 4: Apple TV + macOS

- TV dashboard
- Menu bar app
- Multi-device sync

## Requirements

### For Development

- macOS 14+ (Sonoma)
- Xcode 15+
- Apple Developer Account ($99/year)

### For Users

- iOS 17+ / iPadOS 17+
- watchOS 10+
- tvOS 17+
- macOS 14+

## Documentation

For detailed technical information, see the main repository:

- [Apple Apps Technology Research](https://github.com/bbengt1/argusai/blob/main/docs/research/apple-apps-technology.md)
- [Cloud Relay Architecture Design](https://github.com/bbengt1/argusai/blob/main/docs/architecture/cloud-relay-design.md)
