# ArgusAI

AI-powered event detection and monitoring for home security. Analyzes video feeds from multiple camera sources, detects motion and smart events, and uses AI to generate natural language descriptions of what's happening.

## What's New

### Phase 14 (Complete)
- **MCP Context Enhancement** - Improved AI context with parallel queries, 80ms timeout, and fail-open behavior
- **TF-IDF Pattern Extraction** - Smarter pattern detection with domain-specific stop words for security cameras
- **VIP/Blocked Entity Context** - AI now knows about VIP and blocked entities for personalized descriptions
- **Entity Adjustments** - User corrections to entity names are used to improve future descriptions
- **Context Metrics API** - New `/api/v1/ai/context-metrics` endpoint for monitoring context system performance
- **Cache Optimization** - Improved cache hit ratio through simplified key strategy
- **Code Standardization** - @singleton decorator, retry utility, consistent database patterns
- **Backend Testing** - Comprehensive test coverage for 6 previously untested services
- **Database Integrity** - Check constraints, timezone handling, API response format documentation

### Phase 13 (Complete)
- **API Key Management** - Create and manage API keys for external integrations
- **Scoped Permissions** - Granular access control with `read:events`, `read:cameras`, `write:cameras`, `admin` scopes
- **Per-Key Rate Limiting** - Configurable rate limits per API key with sliding window algorithm
- **API Key Settings UI** - Full management interface for creating, listing, and revoking keys

### Phase 11 (Complete)
- **Remote Access via Cloudflare Tunnel** - Secure access from anywhere without port forwarding
- **Tunnel Settings UI** - Configure tunnel token and monitor connection status
- **Tunnel Documentation** - Step-by-step setup guide for remote access

### Phase 10 (Complete)
- **Docker Containerization** - Single-command deployment with docker-compose
- **Multi-stage Dockerfiles** - Optimized backend and frontend images
- **Optional PostgreSQL** - Production database with `--profile postgres`
- **nginx SSL Reverse Proxy** - Secure HTTPS deployment with `--profile ssl`
- **Compose Profiles** - Flexible service selection for different deployment scenarios

### Phase 9 (Complete)
- **SSL/HTTPS Support** - Secure connections with certificate generation in install script
- **Frame Gallery Modal** - View all frames analyzed by AI for each event
- **Adaptive Frame Sampling** - Motion-based and similarity filtering for better frame selection
- **AI Context Enhancement** - Camera name and time of day included in AI prompts
- **Summary Feedback** - Thumbs up/down on daily summaries with custom prompt support
- **Entity Management** - Unlink, assign, move, and merge entities with full event history
- **Vehicle Entity Separation** - Distinct entities for each vehicle by make/model/color

### Phase 8 (Complete)
- **Frame Storage & Gallery** - All analysis frames stored and viewable in modal gallery
- **Configurable Frame Count** - Choose 5, 10, 15, or 20 frames for AI analysis
- **Frame Sampling Strategies** - Uniform, adaptive, or hybrid sampling modes
- **AI-Assisted Prompt Refinement** - AI helps improve your event description prompts
- **Full Motion Video Download** - Optional storage of complete motion clips
- **Native Apple Apps Foundation** - SwiftUI architecture, cloud relay design (Cloudflare Tunnel)
- **Bug Fixes** - Re-analyse function, installation script, push notification reliability

### Phase 7
- **Package Delivery Alerts** - Carrier detection (USPS, FedEx, UPS, Amazon)
- **Entities Page** - Browse and manage recognized people and vehicles
- **HomeKit Camera Streaming** - RTSP-to-SRTP with snapshot support
- **HomeKit Fixes** - Improved bridge discovery and event delivery

## Features

### Camera Support
- **UniFi Protect Integration** (Phase 2) - Native WebSocket connection for real-time events
  - Auto-discovery of cameras from Protect controller
  - Smart detection filtering (Person/Vehicle/Package/Animal)
  - Doorbell ring event detection with distinct styling
  - Multi-camera event correlation across cameras
  - Real-time camera status sync
- **ONVIF Camera Discovery** (Phase 5) - Auto-discover compatible IP cameras
- **RTSP IP Cameras** - Connect to any RTSP-compatible camera
- **USB/Webcam Support** - Use local cameras for testing or monitoring

### AI-Powered Analysis
- **Multi-Provider Support**: OpenAI GPT-4o → xAI Grok → Claude Haiku → Gemini Flash (automatic fallback)
- **xAI Grok Integration** (Phase 2) - Vision-capable AI with fast response times
- **Video Analysis** (Phase 3) - Multi-frame and native video analysis modes
- **Frame Gallery** (Phase 8) - View all frames analyzed by AI in modal gallery
- **Adaptive Frame Sampling** (Phase 8/9) - Motion-based and similarity filtering for optimal frame selection
- **Configurable Frame Count** (Phase 8) - Choose 5, 10, 15, or 20 frames per analysis
- **AI-Assisted Prompt Refinement** (Phase 8) - AI helps optimize your description prompts
- **Context-Aware Prompts** (Phase 9) - Camera name and time of day in AI context
- **Audio Analysis** (Phase 6) - Glass break, alarm, and doorbell sound detection
- **Natural Language Descriptions**: Rich, contextual descriptions of events
- **Confidence Scoring** (Phase 3) - Quality indicators with re-analyze option
- **Smart Filtering**: Configure which event types trigger AI analysis per camera

### Monitoring & Alerts
- **Real-Time Dashboard**: Live camera previews with event timeline
- **Alert Rules**: Custom rules based on detected objects/events
- **Package Delivery Alerts** (Phase 7) - Carrier-specific delivery notifications
- **Webhook Integration**: Send alerts to external systems (Home Assistant, Slack, etc.)
- **In-App Notifications**: Real-time notification center
- **Push Notifications** (Phase 4) - Web Push with thumbnails, PWA support
- **Activity Summaries** (Phase 4) - Daily digests and on-demand reports
- **Summary Feedback** (Phase 9) - Rate summaries with custom prompt support
- **Cost Monitoring** (Phase 3) - Track AI usage with daily/monthly caps

### Smart Home Integration
- **Home Assistant via MQTT** (Phase 4): Auto-discovery, event publishing, camera status sensors
- **Assistant connector (MCP)**: Read-only MCP server at `/api/v1/mcp` so an assistant bot can answer "what happened at home?" with a dedicated `read:mcp` API key ([docs](docs-site/docs/integrations/mcp-connector.md))
- **HomeKit Integration** (Phase 5) - Native HAP-Python bridge with:
  - Motion sensor accessories for all cameras
  - Occupancy sensors for person detection
  - Package, vehicle, and animal sensors
  - Doorbell accessory for Protect cameras
  - Camera streaming with RTSP-to-SRTP (Phase 7)
  - QR code pairing and diagnostics
- **Voice Query API** (Phase 4): Natural language queries ("What happened at the front door today?")

### Intelligent Context (Phase 4+)
- **Temporal Context Engine**: Find similar past events, recurring visitor detection
- **Pattern Detection**: Identify activity patterns and anomalies
- **Behavioral Anomaly Detection**: Baseline learning with anomaly scoring and alerts
- **Entity Management**: Track recognized people and vehicles
- **Entities Page** (Phase 7) - Browse, search, and manage recognized entities
- **Entity Event List** (Phase 9) - View all events linked to each entity
- **Entity Assignment** (Phase 9) - Unlink, assign, move events between entities
- **Entity Merge** (Phase 9) - Combine duplicate entities
- **Vehicle Separation** (Phase 9) - Distinct entities by make/model/color
- **User Feedback Loop**: Thumbs up/down to improve AI accuracy
- **Package False Positive Feedback** (Phase 9) - Mark incorrect package detections
- **Named Entity Alerts**: Personalized notifications like "John is at the door"

### Event Management
- **Persistent Storage**: Events stored with thumbnails and AI descriptions
- **Search & Filter**: Find events by description, camera, date, object type, or source type
- **Event Source Display**: Visual badges showing RTSP/USB/Protect source for each event
- **Multi-Camera Correlation**: View related events captured across multiple cameras simultaneously
- **Frame Gallery Modal** (Phase 8/9) - Click thumbnails to view all analyzed frames
- **Stored Analysis Frames** (Phase 8) - All frames used for AI analysis are preserved
- **Data Retention**: Configurable automatic cleanup policies
- **Export**: Download events as CSV or JSON
- **Motion Events Export** (Phase 6) - Export motion detection data for analysis
- **Full Video Storage** (Phase 8) - Optional download and storage of motion clips

### Performance & Accessibility (Phase 6)
- **Virtual Scrolling**: Efficient camera list rendering for large deployments
- **React Query Caching**: Optimized data fetching with automatic revalidation
- **Skip-to-Content Links**: Keyboard navigation improvements
- **ARIA Labels**: Full accessibility audit and fixes

### Native Apple Apps (Phase 8+)
- **SwiftUI Architecture**: Native iOS, iPadOS, watchOS, tvOS, and macOS apps planned
- **Cloud Relay**: Cloudflare Tunnel for secure remote access without port forwarding
- **Device Pairing**: 6-digit code pairing with JWT authentication
- **Local Network Fallback**: Automatic Bonjour/mDNS discovery for LAN access
- **Platform-Specific Features**:
  - iPhone/iPad: Push notifications, widgets, Siri shortcuts
  - Apple Watch: Complications for event status, haptic alerts
  - Apple TV: Dashboard view, video playback, Top Shelf integration
  - macOS: Menu bar app, keyboard navigation

### Security & Infrastructure (Phase 9+)
- **SSL/HTTPS Support** - Secure connections with TLS 1.2+
- **Certificate Generation** - Self-signed or Let's Encrypt integration in install script
- **HTTP to HTTPS Redirect** - Automatic secure redirect when SSL enabled
- **Encrypted Credentials** - Fernet encryption for all sensitive credentials
- **API Key Authentication** (Phase 13) - Programmatic access with scoped permissions
- **Per-Key Rate Limiting** (Phase 13) - Configurable rate limits with X-RateLimit headers
- **Dual Authentication** (Phase 13) - Support for both JWT tokens and API keys

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Camera Sources                                 │
├─────────────────┬─────────────────┬─────────────────────────────────────┤
│  UniFi Protect  │   RTSP Cameras  │         USB/Webcam                  │
│  (WebSocket)    │   (Polling)     │         (Capture)                   │
└────────┬────────┴────────┬────────┴──────────────┬──────────────────────┘
         │                 │                       │
         ▼                 ▼                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Event Processing Pipeline                             │
│  ┌───────────┐   ┌───────────────┐   ┌────────────┐   ┌──────────────┐ │
│  │  Motion   │──▶│  AI Provider  │──▶│   Event    │──▶│   Alert      │ │
│  │ Detection │   │  (Multi-API)  │   │   Storage  │   │   Engine     │ │
│  └───────────┘   └───────────────┘   └────────────┘   └──────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
         │                                              │
         ▼                                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        Next.js Dashboard                                 │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────────────┐│
│  │   Live     │  │   Event    │  │   Alert    │  │     Settings       ││
│  │  Cameras   │  │  Timeline  │  │   Rules    │  │  (Cameras, AI)     ││
│  └────────────┘  └────────────┘  └────────────┘  └────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology | Version |
|-------|------------|---------|
| **Frontend** | Next.js (App Router) | 15.x |
| **UI Components** | shadcn/ui + Tailwind CSS | Latest |
| **State Management** | TanStack Query + React Context | v5 |
| **Backend** | FastAPI | 0.115+ |
| **Database** | SQLite (default) / PostgreSQL | 3.x |
| **ORM** | SQLAlchemy + Alembic | 2.0+ |
| **Camera Processing** | OpenCV + PyAV | 4.12+ |
| **AI Providers** | OpenAI, xAI, Anthropic, Google | Latest APIs |
| **UniFi Integration** | uiprotect | Latest |
| **HomeKit** | HAP-Python | Latest |
| **MQTT** | aiomqtt | 2.x |

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- UniFi Protect controller (optional, for native integration)

### Automated Installation (Recommended)

The easiest way to set up the application is using the installation script:

```bash
# Make the script executable
chmod +x install.sh

# Run full installation
./install.sh

# Or check dependencies only
./install.sh --check

# Or install specific components
./install.sh --backend   # Backend only
./install.sh --frontend  # Frontend only
./install.sh --services  # Generate service files only
```

The installation script will:
1. Check all required dependencies (Python 3.11+, Node.js 18+)
2. Create Python virtual environment and install packages
3. Install frontend dependencies and build
4. Generate encryption key
5. Initialize the database
6. Print next steps for configuration

After installation, visit `http://localhost:3000/setup` for the first-run setup wizard.

### Manual Setup

If you prefer manual installation:

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings (ENCRYPTION_KEY, AI API keys)

# Run migrations
alembic upgrade head

# Start server
uvicorn main:app --reload
```

Backend runs at: `http://localhost:8000`
API docs at: `http://localhost:8000/docs`

### Frontend Setup

#### Prerequisites

- **Node.js 18+** (LTS recommended) - Check with `node --version`
- **npm 9+** (comes with Node.js) - Check with `npm --version`

Optional but recommended:
- VS Code with ESLint and Prettier extensions
- React Developer Tools browser extension

#### Installation

```bash
cd frontend

# Install dependencies
npm install
```

#### Environment Configuration

Create a `.env.local` file in the frontend directory:

```bash
# Required: Backend API URL
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Or create it with a single command:
```bash
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
```

#### Development Server

```bash
# Start development server with hot reload
npm run dev
```

Frontend runs at: `http://localhost:3000`

### Docker Deployment (Recommended for Production)

The easiest way to deploy ArgusAI is using Docker Compose:

#### Prerequisites

- Docker Engine 20.10+
- Docker Compose V2+

#### Quick Start

```bash
# Clone the repository
git clone https://github.com/project-argusai/ArgusAI.git
cd ArgusAI

# Copy environment template
cp .env.example .env

# Generate required secrets
python -c "from cryptography.fernet import Fernet; print(f'ENCRYPTION_KEY={Fernet.generate_key().decode()}')" >> .env
openssl rand -hex 32 | xargs -I {} echo "JWT_SECRET_KEY={}" >> .env

# Start the application
docker-compose up -d
```

Access the application at `http://localhost:3000`

#### Deployment Options

| Command | Description |
|---------|-------------|
| `docker-compose up -d` | Start with SQLite (default) |
| `docker-compose --profile postgres up -d` | Start with PostgreSQL |
| `docker-compose --profile ssl up -d` | Start with nginx SSL reverse proxy |
| `docker-compose --profile postgres --profile ssl up -d` | PostgreSQL + SSL |

#### Using PostgreSQL

For production deployments, PostgreSQL is recommended:

```bash
# Set PostgreSQL password
echo "POSTGRES_PASSWORD=your-secure-password" >> .env
echo "DATABASE_URL=postgresql://argusai:your-secure-password@postgres:5432/argusai" >> .env

# Start with PostgreSQL
docker-compose --profile postgres up -d
```

#### Using SSL/HTTPS (nginx Reverse Proxy)

For secure deployments with HTTPS:

```bash
# Create certificates directory
mkdir -p data/certs

# Generate self-signed certificate (for testing)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout data/certs/key.pem \
  -out data/certs/cert.pem \
  -subj "/CN=localhost"

# Or use your own certificates:
# cp /path/to/your/cert.pem data/certs/cert.pem
# cp /path/to/your/key.pem data/certs/key.pem

# Start with SSL
docker-compose --profile ssl up -d
```

Access the application at `https://localhost`

The nginx reverse proxy provides:
- TLS 1.2/1.3 with modern cipher suite
- HTTP to HTTPS automatic redirect
- WebSocket proxy for real-time events
- Optimized routing for API and frontend

#### Docker Compose Management

```bash
# View logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f backend

# Stop containers (preserves data)
docker-compose down

# Stop and remove volumes (WARNING: deletes all data)
docker-compose down -v

# Rebuild images
docker-compose build --no-cache

# Update to latest images
docker-compose pull
docker-compose up -d
```

#### Data Persistence

All persistent data is stored in Docker volumes:

| Volume | Contents |
|--------|----------|
| `argusai-data` | SQLite database, thumbnails, frames, certificates |
| `pgdata` | PostgreSQL data (when using `--profile postgres`) |

#### Available Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start development server with hot reload |
| `npm run build` | Create optimized production build |
| `npm run start` | Start production server (requires build first) |
| `npm run lint` | Run ESLint code quality checks |
| `npm run test` | Run Vitest in watch mode |
| `npm run test:run` | Run all tests once |
| `npm run test:coverage` | Run tests with coverage report |

#### Frontend Troubleshooting

**Port 3000 already in use:**
```bash
# Find process using port 3000
lsof -i :3000
# Kill the process or use a different port
npm run dev -- -p 3001
```

**npm install fails with permission errors:**
```bash
# Clear npm cache and retry
npm cache clean --force
rm -rf node_modules package-lock.json
npm install
```

**API connection errors (CORS or 404):**
1. Verify backend is running on the URL specified in `.env.local`
2. Check CORS_ORIGINS in backend `.env` includes `http://localhost:3000`
3. Restart the frontend dev server after changing `.env.local`

**Node.js version mismatch errors:**
```bash
# Check your Node.js version
node --version
# If below 18, update Node.js:
# macOS: brew upgrade node
# Linux: nvm install 18 && nvm use 18
# Windows: Download from nodejs.org
```

**TypeScript/Build errors after pulling new code:**
```bash
# Clean and reinstall dependencies
rm -rf node_modules .next
npm install
npm run build
```

## Camera Configuration

### UniFi Protect (Recommended)

1. Navigate to **Settings** → **UniFi Protect**
2. Click **Add Controller**
3. Enter controller details:
   - **Name**: Descriptive name (e.g., "Home UDM Pro")
   - **Host**: IP address or hostname of your UDM/Cloud Key
   - **Username/Password**: Local Protect account credentials
4. Click **Test Connection** then **Save**
5. Enable cameras from the discovered list
6. Configure event type filters per camera (Person, Vehicle, Package, etc.)

### ONVIF Discovery (Phase 5)

1. Navigate to **Settings** → **Cameras**
2. Click **Discover Cameras**
3. Wait for network scan to complete
4. Select cameras to add and configure credentials
5. Test connection and save

### RTSP Cameras

1. Navigate to **Cameras** → **Add Camera**
2. Select **RTSP Camera**
3. Enter RTSP URL: `rtsp://192.168.1.50:554/stream1`
4. Add credentials if required
5. Test connection and save

### USB/Webcam

1. Navigate to **Cameras** → **Add Camera**
2. Select **USB Camera**
3. Choose device index (0 = primary, 1 = secondary, etc.)
4. Test connection and save

## AI Provider Setup

Configure AI providers in **Settings** → **AI Providers**:

| Provider | Model | Use Case |
|----------|-------|----------|
| OpenAI | GPT-4o-mini | Primary (best cost/quality) |
| xAI | Grok 2 Vision | Fast vision analysis |
| Anthropic | Claude 3 Haiku | Reliable fallback |
| Google | Gemini Flash | Free tier fallback |

The system automatically falls back to the next provider if one fails.

### xAI Grok Provider

To enable xAI Grok:
1. Get an API key from [xAI Console](https://console.x.ai)
2. Add to **Settings** → **AI Providers** → **xAI Grok**
3. Grok uses the `grok-2-vision-1212` model for image analysis

## Remote Access (Phase 11)

ArgusAI supports secure remote access via Cloudflare Tunnel, allowing you to access your dashboard from anywhere without port forwarding or VPN.

### Quick Setup

1. Install cloudflared on your ArgusAI server:
   ```bash
   # Debian/Ubuntu
   curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
   echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/cloudflared.list
   sudo apt update && sudo apt install cloudflared

   # macOS
   brew install cloudflared
   ```

2. Create a tunnel in Cloudflare Zero Trust dashboard
3. Copy the tunnel token
4. In ArgusAI, go to **Settings** → **Integrations** → **Cloudflare Tunnel**
5. Enable tunnel and paste the token
6. Click **Test Connection**

For detailed setup instructions, see the [Tunnel Setup Guide](docs/guides/tunnel-setup.md).

### Benefits

- No port forwarding required
- Works with CGNAT (Carrier-Grade NAT)
- TLS 1.3 encryption
- Optional Cloudflare Access for additional authentication
- Free tier for personal use

## HomeKit Setup (Phase 5+)

ArgusAI includes native HomeKit integration via HAP-Python:

1. Navigate to **Settings** → **HomeKit**
2. Enable HomeKit Bridge
3. Scan the QR code with Apple Home app
4. Accessories are auto-created for enabled cameras:
   - Motion sensors for all detection events
   - Occupancy sensors for person detection
   - Package/vehicle/animal sensors
   - Doorbell accessory for Protect doorbells
   - Camera streaming (Phase 7)

### HomeKit Troubleshooting

See [Troubleshooting Guide](docs/troubleshooting-protect.md) for common issues.

## Home Assistant Automations

ArgusAI publishes events to MQTT which Home Assistant can use to trigger automations and notifications.

### Prerequisites

1. MQTT configured in ArgusAI (**Settings → Integrations → MQTT**)
2. Home Assistant MQTT integration connected to the same broker
3. Discovery published (devices appear under MQTT → Devices)

### Available Sensors Per Camera

| Entity | Type | Purpose |
|--------|------|---------|
| `sensor.liveobject_{camera}_event` | Sensor | AI description of latest event |
| `sensor.liveobject_{camera}_status` | Sensor | online/offline/unavailable |
| `sensor.liveobject_{camera}_last_event` | Sensor | Timestamp of last event |
| `sensor.liveobject_{camera}_events_today` | Sensor | Daily event count |
| `binary_sensor.liveobject_{camera}_activity` | Binary | ON when motion detected |

### Basic Notification Automation

```yaml
automation:
  - alias: "ArgusAI - Motion Alert"
    trigger:
      - platform: state
        entity_id: sensor.liveobject_front_door_event
    condition:
      - condition: template
        value_template: "{{ trigger.to_state.state not in ['unknown', 'unavailable', ''] }}"
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "{{ trigger.to_state.attributes.camera_name }}"
          message: "{{ trigger.to_state.state }}"
          data:
            image: "{{ trigger.to_state.attributes.thumbnail_url }}"
```

### Person Detection Alert

```yaml
automation:
  - alias: "ArgusAI - Person Detected"
    trigger:
      - platform: state
        entity_id: sensor.liveobject_front_door_event
    condition:
      - condition: template
        value_template: "{{ trigger.to_state.attributes.smart_detection_type == 'person' }}"
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "Person at Front Door"
          message: "{{ trigger.to_state.state }}"
          data:
            image: "{{ trigger.to_state.attributes.thumbnail_url }}"
```

### Package Delivery Alert

```yaml
automation:
  - alias: "ArgusAI - Package Delivered"
    trigger:
      - platform: state
        entity_id: sensor.liveobject_front_porch_event
    condition:
      - condition: template
        value_template: "{{ trigger.to_state.attributes.smart_detection_type == 'package' }}"
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "Package Detected"
          message: "{{ trigger.to_state.state }}"
```

### Available Event Attributes

Use these in your automation templates:

- `trigger.to_state.state` - AI description
- `trigger.to_state.attributes.camera_name` - Camera name
- `trigger.to_state.attributes.smart_detection_type` - person, vehicle, package, animal, ring
- `trigger.to_state.attributes.is_doorbell_ring` - true/false
- `trigger.to_state.attributes.thumbnail_url` - URL to event image
- `trigger.to_state.attributes.confidence` - 0-100

For comprehensive automation examples, see the [Home Assistant Integration Guide](docs-site/docs/integrations/home-assistant.md).

## Project Structure

```
argusai/
├── backend/                  # FastAPI backend
│   ├── app/
│   │   ├── api/v1/          # REST API endpoints
│   │   ├── models/          # SQLAlchemy models
│   │   ├── schemas/         # Pydantic schemas
│   │   └── services/        # Business logic
│   │       ├── camera_service.py      # RTSP/USB capture
│   │       ├── protect_service.py     # UniFi Protect integration
│   │       ├── ai_service.py          # Multi-provider AI
│   │       ├── event_processor.py     # Event pipeline
│   │       ├── correlation_service.py # Multi-camera correlation
│   │       ├── homekit_service.py     # HomeKit bridge
│   │       └── alert_engine.py        # Rule evaluation
│   ├── alembic/             # Database migrations
│   └── tests/               # 3,100+ tests
├── frontend/                 # Next.js frontend
│   ├── app/                 # App Router pages
│   ├── components/          # React components
│   │   ├── cameras/        # Camera management UI
│   │   ├── entities/       # Entity management
│   │   ├── events/         # Event timeline
│   │   ├── protect/        # UniFi Protect components
│   │   ├── settings/       # Settings pages
│   │   └── ui/             # shadcn/ui components
│   └── lib/                 # API client, utilities
└── docs/                    # Project documentation
    ├── architecture.md      # System architecture
    ├── PRD-phase*.md        # Phase requirements
    ├── epics-phase*.md      # Story breakdowns
    └── sprint-artifacts/    # Completed stories
```

## Testing

### Backend

```bash
cd backend
source venv/bin/activate

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html

# Run specific test file
pytest tests/test_api/test_protect.py -v
```

**Current Coverage:** 3,100+ tests including integration and performance tests

### Frontend

```bash
cd frontend

# Run tests
npm run test:run

# Run with coverage
npm run test:coverage

# Lint check
npm run lint

# Type check
npm run build
```

## Environment Variables

### Backend (.env)

```bash
# Required
DATABASE_URL=sqlite:///./data/app.db
ENCRYPTION_KEY=<generate-with-fernet>

# AI Providers (at least one required)
OPENAI_API_KEY=sk-...
XAI_API_KEY=xai-...           # xAI Grok
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...

# Optional
DEBUG=True
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:3000

# SSL/HTTPS (Phase 9)
SSL_ENABLED=false               # Enable HTTPS
SSL_CERT_FILE=data/certs/cert.pem
SSL_KEY_FILE=data/certs/key.pem
SSL_REDIRECT_HTTP=true          # Redirect HTTP to HTTPS
SSL_MIN_VERSION=TLSv1_2         # TLSv1_2 or TLSv1_3

# HomeKit (auto-generated if not set)
HOMEKIT_PIN=123-45-678
```

Generate encryption key:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Frontend (.env.local)

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Documentation

### User & API Documentation

| Document | Description |
|----------|-------------|
| [User Guide](docs/user-guide.md) | Complete guide for setup and usage |
| [Tunnel Setup Guide](docs/guides/tunnel-setup.md) | Remote access via Cloudflare Tunnel |
| [API Reference](docs/api-reference.md) | Full REST API documentation |
| [API Quick Reference](docs/api-quick-reference.md) | One-page endpoint summary with curl examples |
| [OpenAPI Guide](docs/openapi-guide.md) | Export and use OpenAPI specs |
| [Webhook Integration](docs/webhook-integration.md) | Connect to Slack, Discord, Home Assistant, etc. |
| [Troubleshooting UniFi Protect](docs/troubleshooting-protect.md) | Common issues and solutions |

### Project Documentation

| Document | Description |
|----------|-------------|
| [Product Brief](docs/product-brief.md) | Project vision and goals |
| [Architecture](docs/architecture.md) | System design and decisions |
| [UX Design](docs/ux-design-specification.md) | UI/UX specifications |
| [PRD Phase 2](docs/PRD-phase2.md) | UniFi Protect integration requirements |
| [PRD Phase 3](docs/PRD-phase3.md) | Video analysis requirements |
| [PRD Phase 4](docs/PRD-phase4.md) | Context & smart home requirements |
| [PRD Phase 5](docs/PRD-phase5.md) | HomeKit & quality requirements |
| [PRD Phase 9](docs/PRD-phase9.md) | AI accuracy & entity management |
| [Apple Apps Research](docs/research/apple-apps-technology.md) | SwiftUI vs React Native vs Flutter analysis |
| [Cloud Relay Design](docs/architecture/cloud-relay-design.md) | Remote access architecture (Cloudflare Tunnel) |
| [Epics Phase 5](docs/epics-phase5.md) | Phase 5 story breakdown |
| [Epics Phase 6](docs/epics-phase6.md) | Phase 6 story breakdown |
| [Epics Phase 7](docs/epics-phase7.md) | Phase 7 story breakdown |
| [Epics Phase 8](docs/epics-phase8.md) | Phase 8 story breakdown |
| [Epics Phase 9](docs/epics-phase9.md) | Phase 9 story breakdown |

## Roadmap

### Completed (MVP through Phase 7)

**MVP (Phase 1)**
- ✅ RTSP/USB camera support with motion detection
- ✅ Multi-provider AI descriptions (OpenAI, Claude, Gemini)
- ✅ Event storage with search and retention
- ✅ Alert rules with webhook integration
- ✅ Real-time dashboard with notifications

**Phase 2: UniFi Protect Integration**
- ✅ UniFi Protect controller integration
- ✅ Camera auto-discovery and smart detection filtering
- ✅ Real-time camera status sync
- ✅ Event source type display (RTSP/USB/Protect badges)
- ✅ Doorbell ring event detection and distinct styling
- ✅ Multi-camera event correlation service
- ✅ xAI Grok provider with vision capabilities

**Phase 3: Video Analysis**
- ✅ Video clip download from UniFi Protect
- ✅ Multi-frame analysis mode (3-5 key frames)
- ✅ Native video analysis for supported providers
- ✅ AI confidence scoring and quality indicators
- ✅ Cost monitoring dashboard with daily/monthly caps
- ✅ Key frames gallery on event detail

**Phase 4: Intelligent Context & Smart Home**
- ✅ Push notifications with thumbnails (PWA support)
- ✅ Home Assistant integration via MQTT with auto-discovery
- ✅ Temporal context engine (similar events, recurring visitors)
- ✅ Activity summaries and daily digests
- ✅ User feedback loop for AI accuracy improvement
- ✅ Voice query API for natural language event queries
- ✅ Behavioral anomaly detection
- ✅ Person & vehicle recognition (privacy-first embeddings)
- ✅ Named entity alerts ("John is at the door")

**Phase 5: HomeKit & Quality**
- ✅ Native HomeKit integration via HAP-Python
- ✅ HomeKit pairing with QR code
- ✅ Motion/occupancy/package/vehicle/animal sensors
- ✅ Doorbell accessory for Protect events
- ✅ ONVIF camera discovery
- ✅ CI/CD with GitHub Actions
- ✅ Frontend testing with Vitest
- ✅ Accessibility improvements (ARIA, keyboard nav)
- ✅ MQTT 5.0 enhancements

**Phase 6: Polish & Performance**
- ✅ Pre-save camera connection testing
- ✅ Virtual scrolling for camera lists
- ✅ React Query caching optimization
- ✅ Skip-to-content and ARIA audit
- ✅ Audio analysis (glass break, alarms)
- ✅ Motion events CSV export

**Phase 7: HomeKit & Entities**
- ✅ HomeKit diagnostic logging and fixes
- ✅ HomeKit bridge discovery improvements
- ✅ HomeKit event delivery reliability
- ✅ Package delivery carrier detection (USPS, FedEx, UPS, Amazon)
- ✅ Package delivery alert rules and dashboard widget
- ✅ HomeKit camera streaming (RTSP-to-SRTP)
- ✅ Camera snapshot support
- ✅ Entities page with search and filtering
- ✅ Entity alert configuration stub UI

**Phase 8: Video Analysis & AI Enhancements**
- ✅ Store all analysis frames during event processing
- ✅ Frame gallery modal for viewing analyzed frames
- ✅ Configurable frame count (5, 10, 15, 20 frames)
- ✅ Adaptive frame sampling (motion-based, similarity filtering)
- ✅ Frame sampling strategy selection in settings
- ✅ AI-assisted prompt refinement
- ✅ Full motion video download toggle
- ✅ Hide MQTT form when integration disabled
- ✅ Native Apple apps technology research (SwiftUI selected)
- ✅ Cloud relay architecture design (Cloudflare Tunnel)

**Phase 9: AI Accuracy & Entity Management** (Complete)
- ✅ SSL/HTTPS support with certificate generation
- ✅ Frame capture timing optimization
- ✅ Camera and time context in AI prompts
- ✅ Package false positive feedback
- ✅ Summary feedback and custom prompts
- ✅ Vehicle entity separation by make/model
- ✅ Entity event list with unlink/assign/move
- ✅ Entity merge functionality
- ✅ Documentation updates (README refactor, GitHub Pages)
- ✅ GitHub Pages project site with landing page and docs

**Phase 10: Docker & Kubernetes** (In Progress)
- ✅ Backend Dockerfile with multi-stage build
- ✅ Frontend Dockerfile with Next.js standalone output
- ✅ Docker Compose for single-command deployment
- ✅ Environment configuration and volumes
- ✅ Optional PostgreSQL with `--profile postgres`
- ✅ nginx SSL reverse proxy with `--profile ssl`
- 📋 Kubernetes deployment manifests
- 📋 Helm chart for configurable deployments
- 📋 Container CI/CD pipeline

**Phase 11: Remote Access** (Complete)
- ✅ SwiftUI technology decision (research complete)
- ✅ Cloud relay architecture design (Cloudflare Tunnel)
- ✅ Mobile API specification
- ✅ Remote access via Cloudflare Tunnel
- ✅ Tunnel Settings UI

**Phase 13: API Key Management** (Complete)
- ✅ API Key database model with bcrypt hashing
- ✅ API endpoints for key CRUD operations
- ✅ API key authentication middleware
- ✅ Per-key rate limiting with sliding window
- ✅ Scoped permissions (read:events, read:cameras, write:cameras, admin)
- ✅ Frontend settings UI for key management

**Phase 14: Technical Excellence & Quality Foundation** (Complete)
- ✅ Critical security fixes (asyncio.run misuse, debug endpoints)
- ✅ Backend code quality (session management, FK constraints, indexes, rate limiting)
- ✅ Backend testing infrastructure (6 services with 0% → comprehensive coverage)
- ✅ Frontend code quality (test fixtures, unused imports cleanup)
- ✅ Code standardization (@singleton decorator, retry utility)
- ✅ MCP Context System Enhancement with parallel queries
- ✅ 80ms query timeout with fail-open behavior
- ✅ TF-IDF pattern extraction algorithm
- ✅ VIP/Blocked entity context for AI descriptions
- ✅ Entity adjustments context integration
- ✅ Context metrics API endpoint
- ✅ Cache hit ratio optimization
- ✅ Frontend enhancements (accessibility, React Query devtools, hook tests)
- ✅ Database integrity (check constraints, timezone handling)
- ✅ API response format documentation

### Future
- 📋 Native Apple Apps (iPhone, iPad, Apple Watch, Apple TV, macOS)
- 📋 Local LLM support (Ollama)
- 📋 Alexa voice assistant integration
- 📋 Multi-user authentication and permissions
- 📋 Android app (React Native)

## Troubleshooting

### Common Issues

**SSL/HTTPS Not Working:**
1. Verify certificates exist at configured paths (`SSL_CERT_FILE`, `SSL_KEY_FILE`)
2. Check certificate permissions are readable by the backend process
3. For self-signed certs, add them to your browser's trusted certificates
4. Check SSL status: `GET /api/v1/system/ssl-status`

**Push Notifications Not Working:**
- Push notifications require HTTPS - ensure SSL is enabled and working
- Check browser permissions for notifications
- Verify VAPID keys are generated (happens automatically on first enable)

**Camera Connection Issues:**
- For RTSP: Verify URL format `rtsp://user:pass@ip:port/stream`
- For UniFi Protect: Use local account credentials, not Ubiquiti cloud account
- Test connection before saving in the UI

**AI Provider Errors:**
- Verify API key is valid and has credits/quota
- Check rate limits for your provider tier
- System will automatically fallback to next configured provider

**Events Not Appearing:**
- Check camera is enabled for AI analysis
- Verify event type filters allow the detection type
- Check backend logs for processing errors: `Settings > Logs`

For detailed troubleshooting, see:
- [UniFi Protect Issues](docs/troubleshooting-protect.md)
- [User Guide](docs/user-guide.md)

## License

MIT

## Contributing

We welcome contributions! Here's how to get started:

### Development Setup

1. Fork and clone the repository
2. Run `./install.sh` to set up the development environment
3. Review `CLAUDE.md` for codebase conventions and architecture details

### Development Workflow

This project uses the **BMAD Method** for structured development:

- **Stories** are defined in `docs/sprint-artifacts/`
- **Architecture decisions** are documented in `docs/architecture.md`
- Run `/bmad:bmm:workflows:dev-story` to execute story implementation

### Code Standards

- **Backend**: Follow FastAPI patterns, use async/await, add type hints
- **Frontend**: Use TypeScript, follow existing component patterns
- **Testing**: Write tests for all new functionality (pytest for backend, Vitest for frontend)
- **Documentation**: Update relevant docs when adding features

### Pull Request Process

1. Create a feature branch from `main`
2. Make your changes following existing code patterns
3. Ensure all tests pass: `pytest tests/ -v` and `npm run test:run`
4. Update documentation as needed
5. Submit a PR with a clear description of changes

For questions or issues, please open a GitHub issue.
