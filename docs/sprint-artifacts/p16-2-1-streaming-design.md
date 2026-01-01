# P16-2.1: Live Camera Streaming - Technical Design Document

**Story**: P16-2.1 - Research and Design Streaming Approach
**Epic**: P16-2 - Live Camera Streaming
**GitHub Issue**: #352
**Date**: 2026-01-01
**Author**: Claude Opus 4.5

## Executive Summary

This document evaluates streaming approaches for implementing live camera viewing in ArgusAI with **<3 second latency** requirements (FR17). After researching uiprotect library capabilities, browser streaming protocols, and existing ArgusAI infrastructure, the **recommended approach is MJPEG streaming via WebSocket** with HLS fallback for recorded playback.

---

## 1. uiprotect Library Streaming Capabilities

### 1.1 Available APIs

| Method | Description | Latency | Use Case |
|--------|-------------|---------|----------|
| `get_camera_snapshot()` | Single JPEG frame | N/A (single frame) | Thumbnails, previews |
| `get_camera_video(start, end)` | Download video clip | N/A (file download) | Recorded playback |
| `subscribe_websocket(callback)` | Real-time event updates | <1s | Event notifications |
| **RTSP Direct** | `rtsp://host:7447/{camera_id}` | <500ms | Live streaming |

### 1.2 Key Findings

1. **No native browser streaming API**: uiprotect does not provide direct browser-compatible video streams
2. **RTSP access available**: Cameras expose RTSP streams that can be proxied/transcoded
3. **WebSocket for events only**: The WebSocket API is for metadata events, not video frames
4. **Video clip download**: Full motion clips can be downloaded but not streamed in real-time

### 1.3 Existing ArgusAI Implementation

From codebase analysis:
- `snapshot_service.py`: Uses `get_camera_snapshot()` for event thumbnails
- `video_storage_service.py`: Uses `get_camera_video()` for clip downloads
- `camera_service.py`: RTSP capture via OpenCV/PyAV for non-Protect cameras
- `homekit_service.py`: ffmpeg transcoding for HomeKit SRTP streams

---

## 2. Streaming Protocol Comparison

### 2.1 Protocol Matrix

| Protocol | Latency | Browser Support | Complexity | Bandwidth | Scalability |
|----------|---------|-----------------|------------|-----------|-------------|
| **MJPEG** | 50-100ms | Native (all) | Low | High (~10 Mbps) | Medium |
| **HLS** | 6-30s | Native Safari, hls.js others | Medium | Medium (~3 Mbps) | Excellent |
| **LL-HLS** | 2-5s | Partial | High | Medium | Excellent |
| **WebRTC** | <200ms | Excellent | Very High | Low (~2 Mbps) | Poor |
| **WebSocket+Canvas** | 50-150ms | All | Medium | High | Medium |

### 2.2 Protocol Details

#### MJPEG (Motion JPEG)
- **Pros**: Simple, ultra-low latency (~50ms), universal browser support, no transcoding needed
- **Cons**: High bandwidth (no inter-frame compression), CPU-intensive in browser for HD
- **Implementation**: Proxy RTSP → Extract JPEGs → Stream via HTTP multipart or WebSocket

#### HLS (HTTP Live Streaming)
- **Pros**: Adaptive bitrate, excellent scalability, CDN-friendly, Safari native
- **Cons**: 6-30s latency (unacceptable for FR17), requires ffmpeg transcoding
- **Implementation**: RTSP → ffmpeg → HLS segments → hls.js player

#### Low-Latency HLS (LL-HLS)
- **Pros**: 2-5s latency, scalable, adaptive bitrate
- **Cons**: Complex server setup, partial browser support, borderline for FR17
- **Implementation**: RTSP → ffmpeg with LL-HLS → chunked transfer → hls.js

#### WebRTC
- **Pros**: Ultra-low latency (<200ms), efficient bandwidth, P2P capable
- **Cons**: Complex signaling, poor scalability, STUN/TURN needed, browser quirks
- **Implementation**: RTSP → WebRTC gateway (Janus/mediasoup) → Browser

#### WebSocket + Canvas
- **Pros**: Low latency (50-150ms), works everywhere, flexible encoding
- **Cons**: Custom implementation, no native controls, manual buffering
- **Implementation**: RTSP → Backend decode → WebSocket → Canvas render

---

## 3. Recommended Approach

### 3.1 Primary: MJPEG via WebSocket

**Rationale**:
- Meets FR17 (<3s latency) with significant margin (~100ms actual)
- Leverages existing RTSP/frame extraction infrastructure
- Works in all browsers without plugins
- Simple implementation with existing Python libraries
- Natural fallback to snapshot mode

**Architecture**:
```
UniFi Protect Camera
        │
        ├── RTSP Stream (rtsp://protect:7447/{camera_id})
        │
        ▼
   Backend Service
   (rtsp_stream_service.py)
        │
        ├── OpenCV/PyAV capture
        ├── Frame extraction (5-15 FPS)
        ├── JPEG encoding (quality: 70-90)
        │
        ▼
   WebSocket Endpoint
   (/api/v1/cameras/{id}/stream)
        │
        ├── Binary frame messages
        ├── Rate limiting per client
        │
        ▼
   Browser Client
        │
        ├── WebSocket connection
        ├── <img> tag or Canvas render
        └── Fallback to snapshot polling
```

### 3.2 Secondary: HLS for Recorded Playback

For viewing recorded clips (not live), use HLS with hls.js:
- Pre-transcoded clips from `get_camera_video()`
- On-demand HLS generation via ffmpeg
- Adaptive quality for variable bandwidth

---

## 4. Technical Specifications

### 4.1 Quality Levels (FR18)

| Quality | Resolution | FPS | Bandwidth | Use Case |
|---------|------------|-----|-----------|----------|
| Low | 640x360 | 5 | ~1 Mbps | Mobile, poor connection |
| Medium | 1280x720 | 10 | ~3 Mbps | Default viewing |
| High | 1920x1080 | 15 | ~8 Mbps | Detailed analysis |

### 4.2 Bandwidth Estimates

**Per Camera (MJPEG)**:
- Low: 640×360 @ 5fps × 30KB/frame = **1.2 Mbps**
- Medium: 1280×720 @ 10fps × 50KB/frame = **4.0 Mbps**
- High: 1920×1080 @ 15fps × 80KB/frame = **9.6 Mbps**

**Concurrent Streams (FR21)**:
- 4 cameras @ Medium = 16 Mbps server upload
- Limit: 8 concurrent streams per server (configurable)

### 4.3 Latency Budget

| Stage | Target | Notes |
|-------|--------|-------|
| Camera capture | 33ms | 30fps source |
| RTSP transmission | 50ms | Local network |
| Backend decode | 20ms | OpenCV/PyAV |
| WebSocket send | 10ms | Binary frames |
| Browser render | 16ms | 60fps display |
| **Total** | **~130ms** | Well under 3s requirement |

### 4.4 Browser Support Matrix (FR17)

| Browser | MJPEG | WebSocket | Status |
|---------|-------|-----------|--------|
| Chrome 100+ | ✅ | ✅ | Full support |
| Firefox 100+ | ✅ | ✅ | Full support |
| Safari 15+ | ✅ | ✅ | Full support |
| Edge 100+ | ✅ | ✅ | Full support |
| Mobile Safari | ✅ | ✅ | Full support |
| Mobile Chrome | ✅ | ✅ | Full support |

---

## 5. Implementation Plan

### 5.1 Backend Components

1. **RTSPStreamService** (`rtsp_stream_service.py`)
   - Connect to camera RTSP stream
   - Decode frames using OpenCV/PyAV
   - JPEG encode at target quality
   - Maintain frame buffer for new clients

2. **StreamManager** (`stream_manager.py`)
   - Track active streams per camera
   - Implement stream sharing (1 capture, N clients)
   - Handle client connect/disconnect
   - Enforce concurrent stream limits

3. **WebSocket Endpoint** (`/api/v1/cameras/{id}/stream`)
   - Authenticate client
   - Subscribe to stream
   - Send binary JPEG frames
   - Handle quality change requests

### 5.2 Frontend Components

1. **LiveStreamPlayer** (`components/cameras/LiveStreamPlayer.tsx`)
   - WebSocket connection management
   - Frame rendering (img.src = blob URL)
   - Quality selector (FR18)
   - Fullscreen support (FR19)
   - Snapshot fallback (FR20)

2. **MultiStreamView** (`components/cameras/MultiStreamView.tsx`)
   - Grid layout for multiple cameras
   - Bandwidth management
   - Quality auto-adjustment

### 5.3 Required Libraries

**Backend**:
- `opencv-python` (existing) - RTSP capture, frame decode
- `av` (PyAV, existing) - RTSP for secure streams
- `fastapi[websockets]` (existing) - WebSocket endpoint
- No new dependencies required

**Frontend**:
- `hls.js` (NEW) - HLS playback for recorded clips
- React hooks for WebSocket management

### 5.4 Story Breakdown

| Story | Description | Points |
|-------|-------------|--------|
| P16-2.2 | Backend stream service | 5 |
| P16-2.3 | WebSocket streaming endpoint | 3 |
| P16-2.4 | Frontend LiveStreamPlayer component | 5 |
| P16-2.5 | Quality selection UI | 2 |
| P16-2.6 | Fullscreen mode | 2 |
| P16-2.7 | Multi-camera grid view | 3 |
| P16-2.8 | Snapshot fallback handling | 2 |

---

## 6. Fallback Strategy (FR20)

```
┌─────────────────────────────────────────────────────────────┐
│                    Stream Request                            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ WebSocket Stream │
                    │   Available?     │
                    └─────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │ Yes                           │ No
              ▼                               ▼
    ┌─────────────────┐             ┌─────────────────┐
    │  Live MJPEG     │             │  RTSP Direct    │
    │  via WebSocket  │             │  Available?     │
    └─────────────────┘             └─────────────────┘
                                              │
                              ┌───────────────┴───────────────┐
                              │ Yes                           │ No
                              ▼                               ▼
                    ┌─────────────────┐             ┌─────────────────┐
                    │  Retry with     │             │  Snapshot Poll  │
                    │  lower quality  │             │  (1 FPS fallback)│
                    └─────────────────┘             └─────────────────┘
```

---

## 7. Security Considerations

1. **Authentication**: All WebSocket connections require valid JWT
2. **Authorization**: Role-based access to camera streams
3. **Rate Limiting**: Max 1 stream per camera per user, server-wide limits
4. **Encryption**: WSS (WebSocket Secure) required in production
5. **RTSP Credentials**: Never exposed to frontend, backend-only access

---

## 8. Performance Optimizations

1. **Stream Sharing**: Single RTSP connection serves multiple WebSocket clients
2. **Lazy Loading**: Don't start stream until viewport visible
3. **Quality Adaptation**: Auto-downgrade on network congestion
4. **Frame Skipping**: Skip frames if client can't keep up
5. **Connection Pooling**: Reuse RTSP connections across stream restarts

---

## 9. Monitoring & Metrics

- `stream_active_count`: Number of active streams
- `stream_frame_rate`: Frames per second delivered
- `stream_latency_ms`: End-to-end latency
- `stream_bandwidth_mbps`: Bandwidth usage
- `stream_errors_total`: Connection/decode errors

---

## 10. Alternatives Considered

### WebRTC (Rejected)
- Too complex for current scope
- Requires signaling server (STUN/TURN)
- Poor scalability without SFU
- Future enhancement for P2P viewing

### LL-HLS (Rejected)
- 2-5s latency borderline acceptable
- Complex server setup
- Partial browser support
- Consider for cloud relay feature

### Native RTSP in Browser (Not Possible)
- No browser supports RTSP natively
- Would require browser extension/plugin
- Not viable for web application

---

## 11. References

### Documentation Sources
- [uiprotect GitHub Repository](https://github.com/uilibs/uiprotect)
- [HLS Low Latency Guide](https://www.videosdk.live/developer-hub/hls/hls-low-latency)
- [HLS vs MJPEG Comparison](https://www.videosdk.live/developer-hub/hls/hls-vs-mjpeg)
- [WebRTC vs HLS Comparison](https://www.digitalsamba.com/blog/webrtc-vs-hls)

### Internal References
- `backend/app/services/snapshot_service.py` - Existing snapshot implementation
- `backend/app/services/camera_service.py` - RTSP capture infrastructure
- `backend/app/services/homekit_service.py` - ffmpeg transcoding patterns
- `docs/PRD-phase16.md` - Product requirements
- `docs/epics-phase16.md` - Epic definitions

---

## 12. Decision Record

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Primary protocol | MJPEG via WebSocket | <100ms latency, simple, universal browser support |
| Recorded playback | HLS with hls.js | Adaptive quality, Safari native, standard approach |
| Frame extraction | OpenCV/PyAV | Already in codebase, proven reliable |
| Quality levels | 3 (Low/Medium/High) | Balance between choice and complexity |
| Max concurrent | 8 streams/server | Memory/CPU budget for typical deployment |

---

## Approval

- [ ] Technical review completed
- [ ] Architecture alignment confirmed
- [ ] Security review completed
- [ ] Ready for implementation

---

*Document generated as part of Story P16-2.1: Research and Design Streaming Approach*
