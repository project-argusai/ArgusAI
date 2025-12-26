# Cloudflare Tunnel Setup Guide

This guide walks you through setting up Cloudflare Tunnel for secure remote access to ArgusAI. With Cloudflare Tunnel, you can access your ArgusAI dashboard from anywhere without port forwarding or VPN configuration.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Installing cloudflared](#installing-cloudflared)
4. [Creating a Tunnel in Cloudflare](#creating-a-tunnel-in-cloudflare)
5. [Configuring ArgusAI](#configuring-argusai)
6. [Verifying the Connection](#verifying-the-connection)
7. [Troubleshooting](#troubleshooting)
8. [Security Considerations](#security-considerations)

---

## Overview

Cloudflare Tunnel creates a secure, encrypted connection from your ArgusAI server to Cloudflare's global network. This allows you to:

- Access ArgusAI from anywhere via a custom domain (e.g., `argusai.yourdomain.com`)
- Avoid exposing your home network by opening ports
- Benefit from Cloudflare's DDoS protection and global edge network
- Use Cloudflare Access for additional authentication (optional)

### How It Works

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

**Key Points:**
- All connections are **outbound** from your network (no port forwarding needed)
- Traffic is encrypted end-to-end with TLS 1.3
- Works on any ISP, including those with CGNAT (Carrier-Grade NAT)
- Free tier supports personal use

---

## Prerequisites

Before starting, ensure you have:

1. **A Cloudflare account** - Sign up at [cloudflare.com](https://cloudflare.com) (free)
2. **A domain on Cloudflare** - Your domain must use Cloudflare's nameservers
3. **ArgusAI running** - The backend should be accessible at `localhost:8000`
4. **Internet access** - Outbound HTTPS (port 443) must be allowed

---

## Installing cloudflared

`cloudflared` is the Cloudflare Tunnel client that runs on your ArgusAI server. Choose the installation method for your operating system:

### Linux

#### Debian/Ubuntu (Recommended)

```bash
# Add Cloudflare's GPG key
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null

# Add the repository
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/cloudflared.list

# Install
sudo apt update
sudo apt install cloudflared
```

#### RHEL/CentOS/Fedora

```bash
# Add repository
sudo rpm -ivh https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-x86_64.rpm
```

#### Arch Linux

```bash
# From AUR
yay -S cloudflared
# Or manually
paru -S cloudflared
```

#### Manual Installation (Any Linux)

```bash
# Download latest binary
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared

# Make executable
chmod +x cloudflared

# Move to system path
sudo mv cloudflared /usr/local/bin/

# Verify installation
cloudflared --version
```

For ARM systems (Raspberry Pi, etc.):
```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 -o cloudflared
```

### macOS

#### Using Homebrew (Recommended)

```bash
# Install
brew install cloudflared

# Verify
cloudflared --version
```

#### Manual Installation

```bash
# Intel Mac
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz | tar xz

# Apple Silicon (M1/M2)
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-arm64.tgz | tar xz

# Move to path
sudo mv cloudflared /usr/local/bin/
```

### Windows

#### Using Chocolatey

```powershell
choco install cloudflared
```

#### Using Winget

```powershell
winget install Cloudflare.cloudflared
```

#### Manual Installation

1. Download the MSI installer from [Cloudflare releases](https://github.com/cloudflare/cloudflared/releases/latest)
2. Run the installer
3. Cloudflared will be added to your PATH automatically

### Verify Installation

After installation, verify cloudflared is working:

```bash
cloudflared --version
```

Expected output:
```
cloudflared version 2024.x.x (built 2024-xx-xx)
```

---

## Creating a Tunnel in Cloudflare

### Step 1: Log in to Cloudflare Dashboard

1. Go to [dash.cloudflare.com](https://dash.cloudflare.com)
2. Log in to your Cloudflare account

### Step 2: Access Zero Trust Dashboard

1. In the left sidebar, click **Zero Trust**
2. If this is your first time, you may need to set up a team name (any name works)

### Step 3: Create a Tunnel

1. In Zero Trust dashboard, go to **Networks** > **Tunnels**
2. Click **Create a tunnel**
3. Select **Cloudflared** as the connector type
4. Click **Next**

### Step 4: Name Your Tunnel

1. Enter a name for your tunnel (e.g., `argusai-home`)
2. Click **Save tunnel**

### Step 5: Copy the Tunnel Token

After saving, Cloudflare will display a tunnel token. This is a long base64-encoded string.

**IMPORTANT:**
- Copy this token now - you'll need it for ArgusAI configuration
- Store it securely - it grants access to your tunnel
- Never share or commit this token to version control

The token looks like:
```
eyJhIjoiYWJjMTIzNDU2Nzg5MDEyMzQ1Njc4OTAxMjM0NTY3ODkwIiwidCI6ImRlZjEyMzQ1LTY3ODktMDEyMy00NTY3LTg5MDEyMzQ1Njc4OSIsInMiOiJnaGkxMjM0NS02Nzg5LTAxMjMtNDU2Ny04OTAxMjM0NTY3ODkifQ==
```

### Step 6: Configure Public Hostname

1. Click **Next** after copying the token
2. In the **Public hostnames** section, click **Add a public hostname**
3. Configure:
   - **Subdomain**: `argusai` (or your preferred subdomain)
   - **Domain**: Select your domain from the dropdown
   - **Type**: `HTTP`
   - **URL**: `localhost:8000`
4. Click **Save hostname**

Your full URL will be: `https://argusai.yourdomain.com`

### Step 7: Save the Tunnel

Click **Save tunnel** to finish setup.

---

## Configuring ArgusAI

Now configure ArgusAI to use the tunnel token you created.

### Step 1: Navigate to Tunnel Settings

1. Open ArgusAI in your browser: `http://localhost:3000`
2. Go to **Settings** > **Integrations**
3. Find the **Cloudflare Tunnel** section

### Step 2: Enable and Configure

1. **Enable Tunnel**: Toggle the switch to enable
2. **Tunnel Token**: Paste the token you copied from Cloudflare
3. Click **Save Settings**

### Step 3: Start the Tunnel

Click the **Test Connection** button to start the tunnel and verify connectivity.

### Status Indicators

The tunnel status shows one of four states:

| Status | Indicator | Meaning |
|--------|-----------|---------|
| **Disconnected** | Gray dot | Tunnel is not running |
| **Connecting** | Yellow dot (pulsing) | Tunnel is starting up |
| **Connected** | Green dot | Tunnel is active and working |
| **Error** | Red dot | Connection failed (see error message) |

### Additional Information Displayed

When connected, you'll see:
- **Uptime**: How long the tunnel has been connected
- **Last Connected**: Timestamp of last successful connection
- **Reconnect Count**: Number of automatic reconnections

---

## Verifying the Connection

### Test Remote Access

1. On a different network (e.g., mobile data), open your browser
2. Navigate to `https://argusai.yourdomain.com`
3. You should see the ArgusAI login page

### Check Tunnel Status via API

```bash
curl https://argusai.yourdomain.com/api/v1/health
```

Expected response:
```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

### Check Tunnel Status in Cloudflare

1. Go to Cloudflare Zero Trust dashboard
2. Navigate to **Networks** > **Tunnels**
3. Your tunnel should show as **Healthy** with a green indicator

---

## Troubleshooting

### "cloudflared not found"

**Cause**: The cloudflared binary is not installed or not in PATH.

**Solution**:
1. Verify installation: `which cloudflared` or `where cloudflared` (Windows)
2. If not found, reinstall following the installation steps above
3. If installed but not in PATH, add the installation directory to your PATH

### "Invalid tunnel token"

**Cause**: The token is incorrect, corrupted, or expired.

**Solution**:
1. Go to Cloudflare Zero Trust > Tunnels
2. Click on your tunnel
3. Go to **Configure** > **Overview**
4. Click **Generate new token** if needed
5. Copy the new token and update ArgusAI settings

### Connection Timeout

**Cause**: Outbound connections are blocked or network issues.

**Solution**:
1. Verify internet connectivity: `ping cloudflare.com`
2. Check if port 443 outbound is allowed
3. If using a proxy, configure cloudflared to use it:
   ```bash
   export HTTPS_PROXY=http://proxy:8080
   ```
4. Check firewall rules on your router/system

### Tunnel Connects but Website Doesn't Load

**Cause**: ArgusAI backend not running or hostname misconfigured.

**Solution**:
1. Verify ArgusAI is running: `curl http://localhost:8000/api/v1/health`
2. Check the public hostname configuration in Cloudflare:
   - Type should be `HTTP` (not HTTPS)
   - URL should be `localhost:8000`
3. Check cloudflared logs for errors

### Auto-Reconnect Not Working

**Cause**: Network instability or cloudflared process issues.

**Solution**:
1. Check ArgusAI logs in **Settings** > **System** > **Logs**
2. Look for tunnel-related log entries
3. Restart the tunnel via **Settings** > **Integrations** > Toggle off/on

### "Permission denied" Error

**Cause**: cloudflared doesn't have permission to run.

**Solution**:
```bash
# Linux/macOS
sudo chmod +x /usr/local/bin/cloudflared

# Or run with appropriate user
sudo chown $USER:$USER /usr/local/bin/cloudflared
```

### Viewing Tunnel Logs

ArgusAI logs tunnel events. Check:
1. **Settings** > **System** > **View Logs**
2. Filter for `tunnel` in the search
3. Look for entries like:
   - `tunnel.connected` - Successful connection
   - `tunnel.disconnected` - Disconnection event
   - `tunnel.reconnecting` - Reconnection attempt

---

## Security Considerations

### Token Security

Your tunnel token is like a password - protect it carefully:

- **Never share** your tunnel token publicly
- **Never commit** the token to Git or other version control
- **Rotate the token** if you suspect it's been compromised:
  1. Go to Cloudflare Zero Trust > Tunnels
  2. Click your tunnel > Configure > Overview
  3. Click "Generate new token"
  4. Update ArgusAI with the new token

ArgusAI stores your token encrypted using Fernet encryption.

### Network Security

- **No port forwarding required**: All connections are outbound
- **TLS 1.3**: All tunnel traffic is encrypted
- **No public IP exposure**: Your home IP is not revealed

### Optional: Cloudflare Access

For additional security, enable Cloudflare Access to require authentication before accessing ArgusAI:

1. Go to Cloudflare Zero Trust > Access > Applications
2. Click **Add an application**
3. Select **Self-hosted**
4. Configure:
   - Application domain: `argusai.yourdomain.com`
   - Session duration: Your preference
5. Add a policy:
   - Policy name: `ArgusAI Access`
   - Action: `Allow`
   - Configure rules (e.g., email domain, specific users)
6. Save the application

Now users must authenticate via Cloudflare before accessing ArgusAI.

### Domain Recommendations

- Use a **custom domain** rather than Cloudflare's default subdomains
- Consider a **subdomain** like `home.yourdomain.com` for privacy
- Enable **Cloudflare WAF** rules for additional protection (optional)

### Best Practices

1. **Keep cloudflared updated**: New versions include security fixes
   ```bash
   # Debian/Ubuntu
   sudo apt update && sudo apt upgrade cloudflared

   # macOS
   brew upgrade cloudflared
   ```

2. **Monitor tunnel activity**: Check Cloudflare Analytics for unusual traffic

3. **Use strong authentication**: Enable ArgusAI's authentication features

4. **Regular security reviews**: Periodically review who has access to your tunnel configuration

---

## Additional Resources

- [Cloudflare Tunnel Documentation](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
- [Cloudflare Zero Trust](https://developers.cloudflare.com/cloudflare-one/)
- [ArgusAI Documentation](../README.md)
- [Cloud Relay Architecture](../architecture/cloud-relay-architecture.md)

---

## Changelog

| Date | Changes |
|------|---------|
| 2025-12-26 | Initial documentation (Story P11-1.4) |
