---
sidebar_position: 1
---

# Installation

This guide will help you install ArgusAI on your system.

## Prerequisites

Before installing ArgusAI, ensure you have the following:

- **Python 3.11+** - Required for the backend
- **Node.js 18+** - Required for the frontend
- **Git** - For cloning the repository
- **SQLite** or **PostgreSQL** - Database (SQLite is default)

## Quick Installation

The easiest way to install ArgusAI is using the installation script:

```bash
# Clone the repository
git clone https://github.com/bbengt1/argusai.git
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

# CORS origins
CORS_ORIGINS=http://localhost:3000,http://localhost:8000

# Debug mode
DEBUG=True
LOG_LEVEL=INFO
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

- [Configuration](./configuration) - Configure AI providers and cameras
- [UniFi Protect](../features/unifi-protect) - Set up UniFi camera integration
