---
sidebar_position: 7
---

# Settings

The Settings page provides access to all system configuration options, from AI providers to integrations and storage management.

## Accessing Settings

Navigate to **Settings** from the main menu, or click the gear icon in the header.

Settings are organized into sections:

| Section | Purpose |
|---------|---------|
| **AI Models** | Configure AI providers and analysis settings |
| **Protect Controllers** | Manage UniFi Protect connections |
| **Notifications** | Push notification settings |
| **Integrations** | Home Assistant, MQTT, and more |
| **Storage** | Data retention and cleanup |
| **System** | General system settings |

## AI Models

### Provider Configuration

ArgusAI supports multiple AI providers:

| Provider | Configure |
|----------|-----------|
| **OpenAI** | GPT-4o mini, GPT-4 Vision |
| **xAI Grok** | Grok 2 Vision |
| **Anthropic** | Claude 3 Haiku, Sonnet |
| **Google Gemini** | Gemini Flash, Pro |

For each provider:

1. Enter your **API Key**
2. Click **Test** to verify
3. Green checkmark indicates success
4. Select the **Model** to use

#### Getting API Keys

| Provider | Where to Get Key |
|----------|-----------------|
| OpenAI | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| xAI | [console.x.ai](https://console.x.ai/) |
| Anthropic | [console.anthropic.com](https://console.anthropic.com/) |
| Google | [aistudio.google.com](https://aistudio.google.com/) |

### Provider Priority

Drag providers to set the order:

1. **Primary provider** is used first
2. **Fallback providers** used if primary fails
3. Disabled providers are skipped

### Analysis Settings

Configure how events are analyzed:

| Setting | Options |
|---------|---------|
| **Analysis Mode** | Single Frame, Multi-Frame, Video Native |
| **Frame Count** | 5, 10, 15, 20 (for multi-frame) |
| **Sampling Strategy** | Uniform, Adaptive, Hybrid |


### Custom Prompts

Customize the AI prompt:

1. Expand **Advanced Settings**
2. Edit the **Analysis Prompt** text
3. Use variables: `{camera_name}`, `{timestamp}`, `{date}`
4. Click **Refine Prompt** for AI-assisted improvements
5. Save changes

## Protect Controllers

Manage UniFi Protect controller connections.

### Adding a Controller

1. Click **Add Controller**
2. Enter connection details:

| Field | Description |
|-------|-------------|
| **Name** | Friendly identifier |
| **Host** | IP address or hostname |
| **Port** | HTTPS port (default: 443) |
| **Username** | Local user account |
| **Password** | User password |
| **Verify SSL** | Validate certificate |

3. Click **Test Connection**
4. Click **Save** if successful

### Managing Cameras

For each controller:

1. Click the controller name
2. View **Discovered Cameras**
3. Toggle cameras on/off for AI analysis
4. Configure **Event Filters** per camera

### Event Filters

Control which Protect events trigger AI analysis:

| Filter | Description |
|--------|-------------|
| **Person** | Human detection events |
| **Vehicle** | Vehicle detection events |
| **Package** | Package detection events |
| **Animal** | Animal/pet detection events |
| **Ring** | Doorbell ring events |

## Notifications

### Push Notifications

Enable browser push notifications:

1. Click **Enable Push Notifications**
2. Grant browser permission when prompted
3. **Test** to verify with a sample notification

#### Requirements

- HTTPS connection (SSL required)
- Browser notification permission
- Service worker support

Check **Push Status** for current state:

| Status | Meaning |
|--------|---------|
| **Ready** | Notifications will work |
| **Permission Denied** | User blocked notifications |
| **Not Supported** | Browser doesn't support push |
| **HTTPS Required** | Need SSL certificate |

### Notification Preferences

Configure default notification behavior:

| Setting | Description |
|---------|-------------|
| **Sound** | Play audio on notification |
| **Vibration** | Vibrate on mobile |
| **Quiet Hours** | Suppress notifications during hours |

## Integrations

### Home Assistant (MQTT)

Connect to Home Assistant via MQTT:

1. Toggle **MQTT Integration** on
2. Configure connection:

| Field | Description |
|-------|-------------|
| **Host** | MQTT broker address |
| **Port** | Broker port (1883 default) |
| **Username** | MQTT user (optional) |
| **Password** | MQTT password (optional) |
| **Topic Prefix** | Base topic (argusai default) |

3. Click **Test Connection**
4. Save configuration

See [Home Assistant Integration](/docs/integrations/home-assistant) for full setup.

### HomeKit

Native Apple Home integration:

1. Toggle **HomeKit** on
2. A pairing code is generated
3. Open Apple Home app
4. Add accessory using the code

See [HomeKit Integration](/docs/integrations/homekit) for details.

## Storage

### Data Retention

Configure how long to keep data:

| Setting | Default | Description |
|---------|---------|-------------|
| **Event Retention** | 30 days | How long to keep events |
| **Thumbnail Retention** | 30 days | How long to keep images |
| **Motion Events** | 7 days | Low-level motion data |
| **Logs** | 14 days | System log retention |

### Storage Usage

View current storage consumption:

- **Events**: Number and size
- **Thumbnails**: Image storage
- **Video Clips**: Downloaded clips
- **Database**: SQLite file size
- **Total**: Combined usage

### Cleanup Actions

| Action | Description |
|--------|-------------|
| **Run Cleanup Now** | Immediately apply retention rules |
| **Clear Old Events** | Delete events older than X days |
| **Clear All Data** | Delete everything (requires confirmation) |

:::caution
Cleanup operations cannot be undone. Consider backing up data first.
:::

## System

### General Settings

| Setting | Description |
|---------|-------------|
| **System Name** | Display name for your installation |
| **Time Zone** | For timestamp display |
| **Date Format** | How dates are shown |
| **Theme** | Light, Dark, or System |

### Video Storage

Store full motion video clips for complete event review:

| Setting | Description |
|---------|-------------|
| **Store Motion Videos** | Download and save video clips from Protect cameras |
| **Video Retention** | How long to keep videos (7, 14, 30, 60, 90 days) |

When enabled:
- Motion clips are automatically downloaded from UniFi Protect cameras
- Videos appear with a blue video icon on event cards
- Click the icon to play or download the video
- Storage usage is shown in the Storage section

:::note
Video storage only works with UniFi Protect cameras. RTSP and USB cameras do not support video clip downloads.
:::

### SSL/HTTPS

If SSL is configured:

- **Status**: Whether SSL is active
- **Certificate**: Certificate info and expiry
- **Redirect HTTP**: Automatically redirect HTTP to HTTPS

See [Configuration](/docs/getting-started/configuration) for SSL setup.

### Health & Status

View system health:

| Metric | Description |
|--------|-------------|
| **API Status** | Backend connectivity |
| **Database** | Database connection |
| **WebSocket** | Real-time connection |
| **Protect** | Controller connections |

### Logs

Access system logs:

1. Click **View Logs**
2. Filter by level (Error, Warning, Info, Debug)
3. Search for specific messages
4. Download logs for support

## Backup & Export

### Configuration Backup

Export your settings:

1. Click **Export Configuration**
2. Download the JSON file
3. Store securely

Restore from backup:

1. Click **Import Configuration**
2. Select the backup file
3. Choose what to restore
4. Confirm import

### Event Export

Export events for external analysis:

1. Go to **Events** page
2. Apply filters for desired date range
3. Click **Export** button
4. Choose format (JSON, CSV)
5. Download the file

## Tips

### Settings Best Practices

- Test API keys after entry
- Use high provider priority for best quality/cost
- Review retention settings for storage management
- Enable SSL for push notifications

### Troubleshooting Settings

- **API Key Invalid**: Re-copy from provider dashboard
- **Controller Won't Connect**: Check network access and credentials
- **Push Not Working**: Verify HTTPS and permissions
- **MQTT Disconnecting**: Check broker settings and auth
