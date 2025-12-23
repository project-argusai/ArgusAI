---
sidebar_position: 4
---

# Notifications

ArgusAI provides multiple notification channels for security events.

## Push Notifications

Browser push notifications with event thumbnails.

### Requirements

- HTTPS enabled (required for web push)
- Browser notification permissions granted
- Service worker registered

### Enabling Push Notifications

1. Navigate to **Settings > Notifications**
2. Click **Enable Push Notifications**
3. Grant browser permission when prompted
4. Test with the **Send Test** button

### Notification Content

Push notifications include:
- Event description
- Camera name
- Thumbnail image
- Timestamp
- Action buttons (View, Dismiss)

## Alert Rules

Create custom rules to filter notifications:

### Rule Components

| Component | Description |
|-----------|-------------|
| Name | Rule identifier |
| Object Types | person, vehicle, package, animal |
| Cameras | Specific cameras or all |
| Schedule | Time-based activation |
| Actions | What happens when triggered |

### Creating Rules

1. Go to **Settings > Alert Rules**
2. Click **Add Rule**
3. Configure:
   - **Conditions**: When to trigger
   - **Actions**: What to do
4. Save and enable

### Example Rules

**Package Detection During Work Hours**
```yaml
Name: Package Alerts
Object Types: [package]
Cameras: [Front Door, Porch]
Schedule: Mon-Fri 9am-5pm
Actions: [Push Notification, Webhook]
```

**After-Hours Person Detection**
```yaml
Name: Night Watch
Object Types: [person]
Cameras: [All]
Schedule: Daily 10pm-6am
Actions: [Push Notification]
```

## Webhooks

Send events to external services:

### Webhook Configuration

1. Go to **Settings > Alert Rules**
2. Add a rule with Webhook action
3. Configure:
   - **URL**: Target endpoint
   - **Method**: POST (default)
   - **Headers**: Custom headers
   - **Retry**: On failure behavior

### Webhook Payload

```json
{
  "event_id": "uuid",
  "timestamp": "2025-12-23T10:30:00Z",
  "camera_name": "Front Door",
  "description": "Person approaching front door",
  "detection_type": "person",
  "thumbnail_url": "https://...",
  "confidence": 85
}
```

### Integration Examples

- **Slack**: Use incoming webhook URL
- **Discord**: Use webhook URL with Slack compatibility
- **Home Assistant**: Use REST API endpoint
- **IFTTT**: Use webhooks service

## Daily Summaries

AI-generated activity digests:

1. Navigate to **Dashboard > Summaries**
2. View daily activity summary
3. Provide feedback (thumbs up/down)

### Customizing Summaries

1. Go to **Settings > AI Models**
2. Edit **Summary Prompt**
3. Adjust style and content preferences
4. Save changes
