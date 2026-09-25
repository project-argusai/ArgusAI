---
sidebar_position: 2
---

# Docker Deployment

Deploy ArgusAI using Docker Compose for the easiest production-ready setup.

## Prerequisites

- **Docker Engine 20.10+**
- **Docker Compose V2+**
- **SSL certificates** (optional, for HTTPS)

## Quick Start

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

Access ArgusAI at `http://localhost:3000`

## Deployment Options

ArgusAI uses Docker Compose profiles for flexible deployment:

| Command | Description |
|---------|-------------|
| `docker-compose up -d` | Start with SQLite (default) |
| `docker-compose --profile postgres up -d` | Start with PostgreSQL |
| `docker-compose --profile ssl up -d` | Start with nginx SSL reverse proxy |
| `docker-compose --profile postgres --profile ssl up -d` | PostgreSQL + SSL (recommended for production) |

## Using PostgreSQL

For production deployments, PostgreSQL is recommended for better performance and reliability:

```bash
# Add PostgreSQL configuration to .env
echo "POSTGRES_PASSWORD=your-secure-password" >> .env
echo "DATABASE_URL=postgresql://argusai:your-secure-password@postgres:5432/argusai" >> .env

# Start with PostgreSQL
docker-compose --profile postgres up -d
```

:::tip PostgreSQL Benefits
- Better performance for concurrent access
- Full-text search capabilities
- Production-grade reliability
- Easier backup and restore
:::

## Using SSL/HTTPS

For secure deployments with HTTPS, ArgusAI includes an nginx reverse proxy:

### Generate Self-Signed Certificates (Development/Testing)

```bash
# Create certificates directory
mkdir -p data/certs

# Generate self-signed certificate
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout data/certs/key.pem \
  -out data/certs/cert.pem \
  -subj "/CN=localhost"

# Start with SSL
docker-compose --profile ssl up -d
```

### Use Your Own Certificates (Production)

```bash
# Copy your certificates
cp /path/to/your/cert.pem data/certs/cert.pem
cp /path/to/your/key.pem data/certs/key.pem

# Start with SSL
docker-compose --profile ssl up -d
```

Access ArgusAI at `https://localhost`

:::info SSL Features
The nginx reverse proxy provides:
- TLS 1.2/1.3 with modern cipher suite
- HTTP to HTTPS automatic redirect
- WebSocket proxy for real-time events
- Optimized routing for API and frontend
:::

## Architecture

When deployed with Docker Compose, the services are configured as follows:

```
                    ┌─────────────────────────────────────────┐
                    │           nginx (optional)              │
                    │        SSL Termination & Proxy          │
                    │     Ports: 80 (redirect) / 443 (HTTPS)  │
                    └──────────────┬──────────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
              ▼                    ▼                    │
    ┌─────────────────┐  ┌─────────────────┐           │
    │     Backend     │  │    Frontend     │           │
    │   FastAPI       │  │    Next.js      │           │
    │   Port: 8000    │  │    Port: 3000   │           │
    └────────┬────────┘  └─────────────────┘           │
             │                                         │
             ▼                                         │
    ┌─────────────────┐                               │
    │   PostgreSQL    │ ◄─────────────────────────────┘
    │   (optional)    │    --profile postgres
    │   Port: 5432    │
    └─────────────────┘
```

## Container Management

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f nginx
```

### Stop and Start

```bash
# Stop containers (preserves data)
docker-compose down

# Start containers
docker-compose up -d

# Restart a specific service
docker-compose restart backend
```

### Update Images

```bash
# Pull latest images
docker-compose pull

# Rebuild and restart
docker-compose up -d --build
```

### Clean Up

```bash
# Stop and remove containers (keeps volumes)
docker-compose down

# Stop and remove everything including volumes (WARNING: deletes all data)
docker-compose down -v

# Remove unused images
docker image prune
```

## Data Persistence

All persistent data is stored in Docker volumes:

| Volume | Contents |
|--------|----------|
| `argusai-data` | SQLite database, thumbnails, frames, certificates, HomeKit data |
| `pgdata` | PostgreSQL data (when using `--profile postgres`) |

### Backup Data

```bash
# Backup SQLite data volume
docker run --rm -v argusai_argusai-data:/data -v $(pwd):/backup alpine \
  tar czf /backup/argusai-backup.tar.gz /data

# Backup PostgreSQL (when using postgres profile)
docker-compose exec postgres pg_dump -U argusai argusai > backup.sql
```

### Restore Data

```bash
# Restore SQLite data volume
docker run --rm -v argusai_argusai-data:/data -v $(pwd):/backup alpine \
  tar xzf /backup/argusai-backup.tar.gz -C /

# Restore PostgreSQL
docker-compose exec -T postgres psql -U argusai argusai < backup.sql
```

## Environment Variables

Key environment variables for Docker deployment:

### Required

| Variable | Description |
|----------|-------------|
| `ENCRYPTION_KEY` | Fernet key for encrypting API keys |
| `JWT_SECRET_KEY` | Secret for JWT token signing |

### Database

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | Database connection string | `sqlite:///data/app.db` |
| `SQL_ECHO` | Log every SQL statement. Off unless set true. Not tied to `DEBUG` or `LOG_LEVEL`. `DB_ECHO=true` is an alias. | `false` |
| `POSTGRES_USER` | PostgreSQL username | `argusai` |
| `POSTGRES_PASSWORD` | PostgreSQL password | Required for postgres profile |
| `POSTGRES_DB` | PostgreSQL database name | `argusai` |

### AI Providers

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key |
| `XAI_API_KEY` | xAI Grok API key |
| `ANTHROPIC_API_KEY` | Anthropic Claude API key |
| `GOOGLE_AI_API_KEY` | Google AI API key |

See `.env.example` for the complete list of configuration options.

## Troubleshooting

### Container Won't Start

```bash
# Check container status
docker-compose ps

# View detailed logs
docker-compose logs backend
```

### Database Connection Issues

```bash
# Check if PostgreSQL is healthy
docker-compose ps postgres

# Test connection
docker-compose exec postgres pg_isready -U argusai
```

### Permission Issues

```bash
# Fix data directory permissions
sudo chown -R 1000:1000 data/
```

### SSL Certificate Issues

```bash
# Verify certificate files exist
ls -la data/certs/

# Check nginx configuration
docker-compose exec nginx nginx -t
```

## Alternative Deployment Options

- [Kubernetes Deployment](./kubernetes-deployment) - Deploy with raw Kubernetes manifests
- [Helm Chart](./helm-deployment) - Template-based Kubernetes deployment
- [CI/CD Pipeline](./ci-cd) - Automated builds with GitHub Actions

## Next Steps

- [Configuration](./configuration) - Configure AI providers and cameras
- [UniFi Protect](../features/unifi-protect) - Set up UniFi camera integration
- [HomeKit](../integrations/homekit) - Enable HomeKit integration
