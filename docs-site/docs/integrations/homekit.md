---
sidebar_position: 2
---

# Apple HomeKit Integration

ArgusAI integrates with Apple HomeKit for Home app and Siri control.

## Features

- **Motion Sensors**: Per-camera motion detection
- **Occupancy Sensors**: Person detection
- **Contact Sensors**: Vehicle, package, animal detection
- **Doorbell Support**: Ring event handling
- **Camera Streaming**: RTSP to HLS for HomeKit viewing

## Setup

### Prerequisites

- iOS/iPadOS device or Mac with Home app
- ArgusAI running with HTTPS (recommended)
- HAP-Python bridge configured

### Pairing Process

1. Navigate to **Settings > HomeKit**
2. Note the **Setup Code** displayed
3. Open **Home** app on iOS/Mac
4. Tap **+** > **Add Accessory**
5. Select **Don't Have a Code or Can't Scan?**
6. Choose **ArgusAI Bridge**
7. Enter the setup code
8. Follow prompts to complete pairing

### QR Code Pairing

For easier pairing:
1. Go to **Settings > HomeKit**
2. Click **Show QR Code**
3. Scan with iPhone camera
4. Complete pairing in Home app

## Available Accessories

### Motion Sensor

Triggers when motion is detected on a camera.

- **Entity**: One per enabled camera
- **State**: Motion Detected / No Motion
- **Automation**: Use in scenes and automations

### Occupancy Sensor

Triggers when a person is detected.

- **Entity**: One per enabled camera
- **State**: Occupied / Not Occupied
- **Use Case**: Presence-based automations

### Contact Sensors

Specialized sensors for detection types:

| Sensor | Detection Type |
|--------|---------------|
| Vehicle | Car, truck, motorcycle |
| Package | Delivery detection |
| Animal | Pet and wildlife |

### Doorbell

For UniFi Protect doorbell cameras:

- **Button**: Ring event notification
- **Integration**: Works with Home notifications

## Automations

### Example: Lights on Person Detection

1. Open **Home** app
2. Tap **+** > **Add Automation**
3. Choose **A Sensor Detects Something**
4. Select ArgusAI occupancy sensor
5. Add action to turn on lights
6. Save automation

### Example: Night Mode Alert

```
When: ArgusAI Motion Sensor detects motion
Time: 10 PM - 6 AM
Action: Turn on porch light, Send notification
```

## Camera Streaming

ArgusAI can stream camera feeds to HomeKit:

### Requirements

- Camera must support RTSP
- HAP-Python with camera accessory enabled
- Sufficient network bandwidth

### Enabling Streaming

1. Go to **Settings > HomeKit**
2. Enable **Camera Streaming**
3. Select cameras to expose
4. Restart HomeKit bridge

### Viewing in Home App

1. Open **Home** app
2. Find camera accessory
3. Tap for live view
4. Use fullscreen for better quality

## Troubleshooting

### Bridge Not Discoverable

- Ensure ArgusAI is running
- Check network connectivity
- Verify mDNS/Bonjour is working
- Try restarting HomeKit bridge

### Sensors Not Updating

- Check camera is enabled and online
- Verify event processing is working
- Restart HomeKit bridge
- Check ArgusAI logs for errors

### Pairing Failed

- Reset HomeKit accessory in ArgusAI settings
- Remove old pairing from Home app
- Restart both ArgusAI and Home app
- Try pairing again
