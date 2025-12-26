---
sidebar_position: 4
---

# Cloudflare Tunnel (Remote Access)

ArgusAI supports secure remote access via Cloudflare Tunnel, allowing you to access your dashboard from anywhere without port forwarding or VPN configuration.

## Overview

Cloudflare Tunnel creates a secure, encrypted connection from your ArgusAI server to Cloudflare's global network. This enables:

- **Remote Access**: View cameras and events from anywhere via custom domain
- **No Port Forwarding**: All connections are outbound from your network
- **TLS 1.3 Encryption**: End-to-end encrypted traffic
- **DDoS Protection**: Cloudflare's global edge network protection
- **CGNAT Compatible**: Works on any ISP, including those with carrier-grade NAT

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                     Your Home Network                            │
│                                                                  │
│   ┌──────────────┐         ┌──────────────┐                     │
│   │   ArgusAI    │ ◄──────►│  cloudflared │ ────► (outbound)    │
│   │  localhost   │         │   daemon     │                     │
│   │    :8000     │         │              │                     │
│   └──────────────┘         └──────────────┘                     │
│                                    │                             │
└────────────────────────────────────│────────────────────────────┘
                                     │  TLS 1.3
                                     ▼
                        ┌────────────────────────┐
                        │   Cloudflare Edge      │
                        │   (Global Network)     │
                        └────────────┬───────────┘
                                     │  HTTPS
                                     ▼
                        ┌────────────────────────┐
                        │    Your Phone/Laptop   │
                        │   argusai.example.com  │
                        └────────────────────────┘
```

## Prerequisites

Before setting up Cloudflare Tunnel:

1. **Cloudflare Account** - Sign up at [cloudflare.com](https://cloudflare.com) (free)
2. **Domain on Cloudflare** - Your domain must use Cloudflare's nameservers
3. **ArgusAI Running** - Backend accessible at `localhost:8000`

## Installation

### Linux (Debian/Ubuntu)

```bash
# Add Cloudflare's GPG key
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null

# Add the repository
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/cloudflared.list

# Install
sudo apt update
sudo apt install cloudflared
```

### Linux (RHEL/CentOS/Fedora)

```bash
sudo rpm -ivh https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-x86_64.rpm
```

### macOS

```bash
brew install cloudflared
```

### Windows

```powershell
# Using Chocolatey
choco install cloudflared

# Or using Winget
winget install Cloudflare.cloudflared
```

### Verify Installation

```bash
cloudflared --version
```

## Creating a Tunnel

### Step 1: Access Zero Trust Dashboard

1. Log in to [dash.cloudflare.com](https://dash.cloudflare.com)
2. Click **Zero Trust** in the left sidebar
3. Set up a team name if prompted

### Step 2: Create Tunnel

1. Navigate to **Networks > Tunnels**
2. Click **Create a tunnel**
3. Select **Cloudflared** connector type
4. Name your tunnel (e.g., `argusai-home`)
5. Click **Save tunnel**

### Step 3: Copy Token

After saving, Cloudflare displays a tunnel token. **Copy this token** - you'll need it for ArgusAI configuration.

:::warning Token Security
Never share or commit your tunnel token. It grants access to your tunnel.
:::

### Step 4: Configure Hostname

1. Click **Next** after copying the token
2. Add a public hostname:
   - **Subdomain**: `argusai` (or your preference)
   - **Domain**: Select your domain
   - **Type**: `HTTP`
   - **URL**: `localhost:8000`
3. Click **Save hostname**

## ArgusAI Configuration

### Using the Settings UI

1. Open ArgusAI at `http://localhost:3000`
2. Navigate to **Settings > Integrations**
3. Find the **Cloudflare Tunnel** section
4. Toggle **Enable Tunnel**
5. Paste your tunnel token
6. Click **Save Settings**
7. Click **Test Connection**

### Status Indicators

| Status | Indicator | Meaning |
|--------|-----------|---------|
| **Disconnected** | Gray | Tunnel not running |
| **Connecting** | Yellow (pulsing) | Starting up |
| **Connected** | Green | Active and working |
| **Error** | Red | Failed (see error message) |

### Additional Metrics

When connected, the UI displays:
- **Uptime**: Connection duration
- **Last Connected**: Timestamp
- **Reconnect Count**: Auto-reconnection count

## Troubleshooting

### cloudflared Not Found

**Cause**: Binary not installed or not in PATH.

**Solution**:
```bash
# Verify installation
which cloudflared

# If not found, reinstall following platform-specific instructions
```

### Invalid Tunnel Token

**Cause**: Token corrupted or expired.

**Solution**:
1. Go to Cloudflare Zero Trust > Tunnels
2. Click your tunnel > Configure > Overview
3. Click **Generate new token**
4. Update token in ArgusAI settings

### Connection Timeout

**Cause**: Outbound connections blocked.

**Solution**:
1. Verify internet: `ping cloudflare.com`
2. Check port 443 outbound is allowed
3. Configure proxy if needed:
   ```bash
   export HTTPS_PROXY=http://proxy:8080
   ```

### Tunnel Connects but Site Doesn't Load

**Cause**: Backend not running or hostname misconfigured.

**Solution**:
1. Verify ArgusAI backend: `curl http://localhost:8000/api/v1/health`
2. Check hostname configuration in Cloudflare:
   - Type: `HTTP` (not HTTPS)
   - URL: `localhost:8000`

### Permission Denied

**Cause**: cloudflared lacks execution permissions.

**Solution**:
```bash
sudo chmod +x /usr/local/bin/cloudflared
```

## Security Best Practices

### Token Security

- **Never share** your tunnel token publicly
- **Never commit** tokens to version control
- **Rotate tokens** if compromised:
  1. Cloudflare Zero Trust > Tunnels
  2. Click tunnel > Configure > Overview
  3. Generate new token
  4. Update in ArgusAI

### Optional: Cloudflare Access

Add authentication before users can access ArgusAI:

1. Go to Zero Trust > Access > Applications
2. Add a self-hosted application
3. Configure your ArgusAI domain
4. Add authentication rules (email, identity provider, etc.)

### Recommendations

- Use a **custom domain** rather than Cloudflare subdomains
- Consider a **subdomain** like `home.yourdomain.com` for privacy
- Keep **cloudflared updated** for security patches:
  ```bash
  # Debian/Ubuntu
  sudo apt update && sudo apt upgrade cloudflared

  # macOS
  brew upgrade cloudflared
  ```

## Benefits Summary

| Feature | Benefit |
|---------|---------|
| No port forwarding | No router configuration needed |
| CGNAT compatible | Works with any ISP |
| TLS 1.3 | End-to-end encryption |
| DDoS protection | Cloudflare edge network |
| Free tier | Personal use supported |
| Auto-reconnect | Survives network changes |

## Related Documentation

- [Full Tunnel Setup Guide](/docs/guides/tunnel-setup.md) - Comprehensive reference
- [Cloud Relay Architecture](/docs/architecture/cloud-relay-architecture.md) - Technical design
- [Cloudflare Tunnel Docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) - Official documentation
