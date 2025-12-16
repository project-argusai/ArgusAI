# ArgusAI

AI-powered event detection and monitoring for home security. Analyzes video feeds from multiple camera sources, detects motion and smart events, and uses AI to generate natural language descriptions of what's happening.

## What's New (Phase 4 Complete)

- **Named Entity Alerts** - Personalized notifications like "John is at the door" instead of generic "Person detected"
- **Person & Vehicle Recognition** - Privacy-first face/vehicle embeddings with VIP alerts and blocklist
- **Behavioral Anomaly Detection** - Baseline activity learning with anomaly scoring and alerts
- **HomeKit Integration** - Motion sensor accessories for Apple Home with real-time triggers
- **Voice Query API** - Natural language queries ("What happened at the front door today?")
- **Push Notifications** - Web Push with thumbnails and PWA support
- **Home Assistant via MQTT** - Auto-discovery, event publishing, camera status sensors

## Features

### Camera Support
- **UniFi Protect Integration** (Phase 2) - Native WebSocket connection for real-time events
  - Auto-discovery of cameras from Protect controller
  - Smart detection filtering (Person/Vehicle/Package/Animal)
  - Doorbell ring event detection with distinct styling
  - Multi-camera event correlation across cameras
  - Real-time camera status sync
- **RTSP IP Cameras** - Connect to any RTSP-compatible camera
- **USB/Webcam Support** - Use local cameras for testing or monitoring

### AI-Powered Analysis
- **Multi-Provider Support**: OpenAI GPT-4o → xAI Grok → Claude Haiku → Gemini Flash (automatic fallback)
- **xAI Grok Integration** (Phase 2) - Vision-capable AI with fast response times
- **Natural Language Descriptions**: Rich, contextual descriptions of events
- **Smart Filtering**: Configure which event types trigger AI analysis per camera

### Monitoring & Alerts
- **Real-Time Dashboard**: Live camera previews with event timeline
- **Alert Rules**: Custom rules based on detected objects/events
- **Webhook Integration**: Send alerts to external systems (Home Assistant, Slack, etc.)
- **In-App Notifications**: Real-time notification center
- **Push Notifications** (Phase 4) - Web Push with thumbnails, PWA support
- **Activity Summaries** (Phase 4) - Daily digests and on-demand reports

### Smart Home Integration (Phase 4)
- **Home Assistant via MQTT**: Auto-discovery, event publishing, camera status sensors
- **HomeKit Integration**: Motion sensor accessories, real-time event triggers
- **Voice Query API**: Natural language queries ("What happened at the front door today?")

### Intelligent Context (Phase 4)
- **Temporal Context Engine**: Find similar past events, recurring visitor detection
- **Pattern Detection**: Identify activity patterns and anomalies
- **Entity Management**: Track recognized people and vehicles
- **User Feedback Loop**: Thumbs up/down to improve AI accuracy

### Event Management
- **Persistent Storage**: Events stored with thumbnails and AI descriptions
- **Search & Filter**: Find events by description, camera, date, object type, or source type
- **Event Source Display**: Visual badges showing RTSP/USB/Protect source for each event
- **Multi-Camera Correlation**: View related events captured across multiple cameras simultaneously
- **Data Retention**: Configurable automatic cleanup policies
- **Export**: Download events as CSV or JSON

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
| **AI Providers** | OpenAI, Anthropic, Google | Latest APIs |
| **UniFi Integration** | uiprotect | Latest |

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
│   │       └── alert_engine.py        # Rule evaluation
│   ├── alembic/             # Database migrations
│   └── tests/               # 2,250+ tests
├── frontend/                 # Next.js frontend
│   ├── app/                 # App Router pages
│   ├── components/          # React components
│   │   ├── cameras/        # Camera management UI
│   │   ├── events/         # Event timeline
│   │   ├── protect/        # UniFi Protect components
│   │   └── ui/             # shadcn/ui components
│   └── lib/                 # API client, utilities
└── docs/                    # Project documentation
    ├── architecture.md      # System architecture
    ├── PRD-phase2.md        # Phase 2 requirements
    ├── epics-phase2.md      # Story breakdown
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

**Current Coverage:** 2,250+ tests including integration and performance tests

### Frontend

```bash
cd frontend

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
| [Epics Phase 3](docs/epics-phase3.md) | Phase 3 story breakdown |
| [Epics Phase 4](docs/epics-phase4.md) | Phase 4 story breakdown |

## Roadmap

### Completed (MVP + Phase 2 + Phase 3 + Phase 4)
- ✅ RTSP/USB camera support with motion detection
- ✅ Multi-provider AI descriptions (OpenAI, xAI Grok, Claude, Gemini)
- ✅ Event storage with search and retention
- ✅ Alert rules with webhook integration
- ✅ Real-time dashboard with notifications
- ✅ UniFi Protect controller integration
- ✅ Camera auto-discovery and smart detection filtering
- ✅ Real-time camera status sync
- ✅ Event source type display (RTSP/USB/Protect badges)
- ✅ Doorbell ring event detection and distinct styling
- ✅ Multi-camera event correlation service
- ✅ Correlated events display in dashboard (link indicators, related events section)
- ✅ xAI Grok provider with vision capabilities
- ✅ RTSP/USB/Protect camera coexistence
- ✅ Comprehensive error handling and recovery
- ✅ **Phase 3: Video Analysis**
  - Video clip download from UniFi Protect
  - Multi-frame analysis mode (3-5 key frames)
  - AI confidence scoring and quality indicators
  - Cost monitoring dashboard with daily/monthly caps
  - Key frames gallery on event detail
  - Analysis mode filter on timeline
- ✅ **Phase 4: Intelligent Context & Smart Home**
  - Push notifications with thumbnails (PWA support)
  - Home Assistant integration via MQTT with auto-discovery
  - Temporal context engine (similar events, recurring visitors)
  - Activity summaries and daily digests
  - User feedback loop for AI accuracy improvement
  - HomeKit integration with motion sensor accessories
  - Voice query API for natural language event queries
  - Behavioral anomaly detection (baseline learning, anomaly scoring, alerts)
  - Person & vehicle recognition (privacy-first face/vehicle embeddings)
  - Named entity alerts ("John is at the door" personalized notifications)
  - VIP alerts and entity blocklist for notification control

### Future
- 📋 Local LLM support (Ollama)
- 📋 Alexa voice assistant integration
- 📋 Multi-user authentication and permissions
- 📋 Cloud backup and sync

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
- **Testing**: Write tests for all new functionality (pytest for backend)
- **Documentation**: Update relevant docs when adding features

### Pull Request Process

1. Create a feature branch from `development`
2. Make your changes following existing code patterns
3. Ensure all tests pass: `pytest tests/ -v`
4. Update documentation as needed
5. Submit a PR with a clear description of changes

For questions or issues, please open a GitHub issue.
