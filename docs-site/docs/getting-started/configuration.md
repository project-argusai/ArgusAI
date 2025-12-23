---
sidebar_position: 2
---

# Configuration

Learn how to configure ArgusAI for your environment.

## AI Providers

ArgusAI supports multiple AI providers with automatic fallback:

1. **OpenAI GPT-4o mini** (default primary)
2. **xAI Grok 2 Vision**
3. **Anthropic Claude 3 Haiku**
4. **Google Gemini Flash**

### Configuring AI Providers

Navigate to **Settings > AI Models** in the dashboard to configure your providers.

Each provider requires an API key:

| Provider | API Key Source |
|----------|---------------|
| OpenAI | [platform.openai.com](https://platform.openai.com/api-keys) |
| xAI Grok | [console.x.ai](https://console.x.ai/) |
| Anthropic | [console.anthropic.com](https://console.anthropic.com/) |
| Google Gemini | [aistudio.google.com](https://aistudio.google.com/) |

### Provider Priority

You can arrange providers in priority order. The system will:
1. Try the primary provider first
2. Fall back to secondary providers on failure
3. Continue until a successful response or all providers fail

## Camera Configuration

### UniFi Protect Cameras

1. Navigate to **Settings > Protect Controllers**
2. Add your controller details:
   - **Host**: IP address or hostname of your Protect controller
   - **Username**: Local user credentials
   - **Password**: User password
   - **Port**: Usually 443
3. Click **Test Connection** then **Save**
4. Discovered cameras will appear for enabling

### RTSP Cameras

1. Navigate to **Cameras** page
2. Click **Add Camera**
3. Enter camera details:
   - **Name**: Friendly name
   - **RTSP URL**: Full RTSP stream URL
   - **Username/Password**: Camera credentials (optional)
4. Click **Test Connection** to verify
5. Save and enable the camera

### USB Webcams

1. Navigate to **Cameras** page
2. Click **Add Camera**
3. Select **USB** as source type
4. Choose the device from available webcams

## Analysis Settings

Configure how ArgusAI analyzes video events:

### Frame Count

Choose how many frames to analyze per event:
- **5 frames**: Fast, lower cost
- **10 frames**: Balanced (default)
- **15 frames**: Better accuracy
- **20 frames**: Maximum detail

### Sampling Strategy

- **Uniform**: Fixed interval extraction (predictable)
- **Adaptive**: Content-aware selection (better quality)
- **Hybrid**: Dense extraction with filtering (best quality)

## Alert Rules

Create rules to trigger notifications:

1. Navigate to **Settings > Alert Rules**
2. Click **Add Rule**
3. Configure conditions:
   - **Object Types**: person, vehicle, package, animal
   - **Cameras**: Select specific cameras
   - **Schedule**: Time-based activation
4. Configure actions:
   - **Push Notification**: Browser push alerts
   - **Webhook**: Send to external URL

## SSL/HTTPS

For secure connections (required for push notifications):

```bash
# Environment variables
SSL_ENABLED=true
SSL_CERT_FILE=data/certs/cert.pem
SSL_KEY_FILE=data/certs/key.pem
```

See [Troubleshooting](../troubleshooting) for certificate generation.
