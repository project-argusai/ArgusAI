# Live Object AI Classifier

AI-powered event detection and monitoring for home security. Analyzes video feeds from multiple camera sources, detects motion and smart events, and uses AI to generate natural language descriptions of what's happening.

## Features

### Camera Support
- **UniFi Protect Integration** (Phase 2) - Native WebSocket connection for real-time events
  - Auto-discovery of cameras from Protect controller
  - Smart detection filtering (Person/Vehicle/Package/Animal)
  - Doorbell ring notifications
  - Real-time camera status sync
- **RTSP IP Cameras** - Connect to any RTSP-compatible camera
- **USB/Webcam Support** - Use local cameras for testing or monitoring

### AI-Powered Analysis
- **Multi-Provider Support**: OpenAI GPT-4o → Claude Haiku → Gemini Flash (automatic fallback)
- **Natural Language Descriptions**: Rich, contextual descriptions of events
- **Smart Filtering**: Configure which event types trigger AI analysis per camera

### Monitoring & Alerts
- **Real-Time Dashboard**: Live camera previews with event timeline
- **Alert Rules**: Custom rules based on detected objects/events
- **Webhook Integration**: Send alerts to external systems (Home Assistant, Slack, etc.)
- **In-App Notifications**: Real-time notification center

### Event Management
- **Persistent Storage**: Events stored with thumbnails and AI descriptions
- **Search & Filter**: Find events by description, camera, date, or object type
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

```bash
cd frontend

# Install dependencies
npm install

# Configure API URL
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

# Start development server
npm run dev
```

Frontend runs at: `http://localhost:3000`

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
| Anthropic | Claude 3 Haiku | Fallback |
| Google | Gemini Flash | Free tier fallback |

The system automatically falls back to the next provider if one fails.

## Project Structure

```
live-object-ai-classifier/
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
│   │       └── alert_engine.py        # Rule evaluation
│   ├── alembic/             # Database migrations
│   └── tests/               # 444 tests
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

**Current Coverage:** 444 tests, 100% pass rate

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

| Document | Description |
|----------|-------------|
| [Product Brief](docs/product-brief.md) | Project vision and goals |
| [PRD Phase 2](docs/PRD-phase2.md) | UniFi Protect integration requirements |
| [Architecture](docs/architecture.md) | System design and decisions |
| [Epics](docs/epics-phase2.md) | Story breakdown and status |
| [UX Design](docs/ux-design-specification.md) | UI/UX specifications |

## Roadmap

### Completed (MVP + Phase 2.1-2.2)
- ✅ RTSP/USB camera support with motion detection
- ✅ Multi-provider AI descriptions (OpenAI, Claude, Gemini)
- ✅ Event storage with search and retention
- ✅ Alert rules with webhook integration
- ✅ Real-time dashboard with notifications
- ✅ UniFi Protect controller integration
- ✅ Camera auto-discovery and smart detection filtering
- ✅ Real-time camera status sync

### In Progress (Phase 2.3-2.6)
- 🔄 Doorbell ring notifications
- 🔄 Multi-camera event correlation
- 🔄 xAI Grok provider integration

### Planned
- 📋 Local LLM support (Ollama)
- 📋 Mobile push notifications
- 📋 Historical pattern analysis
- 📋 HomeKit integration

## License

MIT

## Contributing

1. Fork the repository
2. Create a feature branch
3. Follow existing code patterns
4. Write tests for new functionality
5. Submit a pull request

For questions or issues, please open a GitHub issue.
