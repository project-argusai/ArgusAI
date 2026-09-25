---
sidebar_position: 1
---

# Installation

This guide will help you install ArgusAI on your system.

## Choose Your Installation Method

| Method | Best For | Requirements |
|--------|----------|--------------|
| [Docker Compose](./docker-deployment) | Single server, Easy setup | Docker, Docker Compose |
| [Kubernetes](./kubernetes-deployment) | Scalable clusters, Fine control | Kubernetes 1.25+, kubectl |
| [Helm Chart](./helm-deployment) | Template-based K8s, GitOps | Kubernetes 1.25+, Helm 3.10+ |
| Manual Installation | Development, Customization | Python 3.11+, Node.js 18+ |

:::tip Recommended
- **Single server**: Use [Docker Compose](./docker-deployment) for the easiest setup
- **Kubernetes clusters**: Use [Helm Chart](./helm-deployment) for customizable deployments
- **CI/CD pipelines**: Pre-built images are available from [GitHub Container Registry](./ci-cd)
:::

## Prerequisites (Manual Installation)

Before installing ArgusAI manually, ensure you have the following:

- **Python 3.11+** - Required for the backend
- **Node.js 18+** - Required for the frontend
- **Git** - For cloning the repository
- **SQLite** or **PostgreSQL** - Database (SQLite is default)

## Quick Installation (Script)

```bash
# Clone the repository
git clone https://github.com/project-argusai/ArgusAI.git
cd argusai

# Run the installation script
./scripts/install.sh
```

The script will:
1. Create a Python virtual environment
2. Install backend dependencies
3. Install frontend dependencies
4. Set up the database
5. Optionally configure SSL certificates

## Manual Installation

### Backend Setup

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up database
alembic upgrade head
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Build for production
npm run build
```

## Environment Configuration

Create a `.env` file in the backend directory:

```bash
# Database
DATABASE_URL=sqlite:///./data/app.db

# Encryption key (generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
ENCRYPTION_KEY=your-encryption-key-here

# CORS origins. Cookie-authenticated writes trust this exact list.
CORS_ORIGINS=http://localhost:3000,http://localhost:8000

# Session cookies. lax is the default because the web app calls the API on the
# same site (Next.js `/api/v1` proxy or nginx). Set none only when the browser
# calls the API on a different site, and keep COOKIE_SECURE=true.
COOKIE_SECURE=true
COOKIE_SAMESITE=lax

# Debug mode
DEBUG=True
LOG_LEVEL=INFO

# Per-statement SQL logs. Off by default; not enabled by DEBUG or LOG_LEVEL.
SQL_ECHO=false
```

## Running ArgusAI

### Development Mode

```bash
# Backend (terminal 1)
cd backend
source venv/bin/activate
uvicorn main:app --reload

# Frontend (terminal 2)
cd frontend
npm run dev
```

### Production Mode

```bash
# Backend
cd backend
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000

# Frontend
cd frontend
npm run build
npm run start
```

## Next Steps

### Deployment Options
- [Docker Compose](./docker-deployment) - Single-server deployment with Docker Compose
- [Kubernetes](./kubernetes-deployment) - Deploy with raw Kubernetes manifests
- [Helm Chart](./helm-deployment) - Template-based Kubernetes deployment
- [CI/CD Pipeline](./ci-cd) - Automated builds and deployments

### Configuration
- [Configuration](./configuration) - Configure AI providers and cameras
- [UniFi Protect](../features/unifi-protect) - Set up UniFi camera integration
