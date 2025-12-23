---
sidebar_position: 1
---

# UniFi Protect Integration

ArgusAI provides native integration with Ubiquiti's UniFi Protect system.

## Features

- **Real-time Events**: WebSocket connection for instant event detection
- **Smart Detection Types**: Person, vehicle, package, animal, doorbell ring
- **Snapshot Retrieval**: Automatic snapshot download for AI analysis
- **Multi-Camera Support**: Manage all Protect cameras from one dashboard

## Setting Up Protect Integration

### Prerequisites

- UniFi Protect controller running on UniFi OS 3.0+
- Local user account with admin or view access
- Network access from ArgusAI to the Protect controller

### Adding a Controller

1. Navigate to **Settings > Protect Controllers**
2. Click **Add Controller**
3. Enter your controller details:

| Field | Description |
|-------|-------------|
| Name | Friendly name for the controller |
| Host | IP address or hostname |
| Port | HTTPS port (default: 443) |
| Username | Local user account |
| Password | User password |
| Verify SSL | Enable for production |

4. Click **Test Connection**
5. If successful, click **Save**

### Enabling Cameras

After adding a controller:

1. Go to **Settings > Protect Controllers**
2. Click on your controller
3. View the **Discovered Cameras** list
4. Toggle cameras ON to enable AI analysis
5. Configure event filters per camera

### Event Filters

For each camera, you can filter which events trigger AI analysis:

- **Person**: Human detection
- **Vehicle**: Cars, trucks, motorcycles
- **Package**: Delivery detection
- **Animal**: Pet and wildlife
- **Ring**: Doorbell events

## Event Processing

When a Protect event is detected:

```
1. Protect WebSocket → Event received
2. Filter check → Does event match enabled filters?
3. Snapshot download → Get image from Protect API
4. AI analysis → Send to configured AI provider
5. Description stored → Save to database
6. Notifications → Trigger alert rules
```

## Doorbell Events

ArgusAI provides special handling for doorbell events:

- Distinct visual styling in the dashboard
- Ring event type for targeted alerts
- Quick-view timeline filter

## Troubleshooting

### Connection Issues

- Verify the controller is accessible from your ArgusAI server
- Check username/password are for a local account (not Ubiquiti SSO)
- Ensure the port is correct (usually 443)

### Missing Events

- Check event filters are enabled for the camera
- Verify the camera is set to record motion events in Protect
- Check Protect controller logs for connection issues

### Slow Snapshot Downloads

- Ensure good network connectivity
- Check controller CPU/memory usage
- Consider reducing concurrent camera count
