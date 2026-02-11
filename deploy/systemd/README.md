# ArgusAI systemd Service Files

Hardened systemd service files for running ArgusAI on a standalone Linux server.

## Features (Issue #383)

These service files include hardening to prevent port binding restart loops:

| Setting | Value | Purpose |
|---------|-------|---------|
| `KillMode=mixed` | mixed | Ensures child processes (workers) are killed when main process stops |
| `TimeoutStopSec=15` | 15s | Gives uvicorn time to gracefully shutdown and release port |
| `TimeoutStartSec=30` | 30s | Allows time for startup (DB connections, model loading) |
| `RestartSec=5` | 5s | Delay between restarts to ensure port is released |
| `--timeout-graceful-shutdown 10` | 10s | Uvicorn graceful shutdown timeout |

## Installation

```bash
# Copy service files
sudo cp argusai-backend.service /etc/systemd/system/
sudo cp argusai-frontend.service /etc/systemd/system/

# Edit paths to match your installation
sudo nano /etc/systemd/system/argusai-backend.service
sudo nano /etc/systemd/system/argusai-frontend.service

# Reload systemd
sudo systemctl daemon-reload

# Enable services to start on boot
sudo systemctl enable argusai-backend argusai-frontend

# Start services
sudo systemctl start argusai-backend argusai-frontend
```

## Troubleshooting

### Check service status
```bash
sudo systemctl status argusai-backend
sudo systemctl status argusai-frontend
```

### View logs
```bash
journalctl -u argusai-backend -f
journalctl -u argusai-frontend -f
```

### Check for port conflicts
```bash
# Check if port 8000 is in use
sudo ss -tlnp | grep 8000

# Check if port 3000 is in use  
sudo ss -tlnp | grep 3000
```

### Reset restart counter
If the service has been restarting, reset the counter:
```bash
sudo systemctl reset-failed argusai-backend
```

## Security Hardening

The service files include security sandboxing:

- `NoNewPrivileges=true` - Prevents privilege escalation
- `PrivateTmp=true` - Isolated /tmp directory
- `ProtectSystem=strict` - Read-only system directories
- `ProtectHome=read-only` - Read-only home directories
- `ReadWritePaths=...` - Explicit write access only where needed
