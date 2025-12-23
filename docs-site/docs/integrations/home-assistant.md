---
sidebar_position: 1
---

# Home Assistant Integration

ArgusAI integrates with Home Assistant via MQTT with auto-discovery.

## Features

- **Auto-Discovery**: Devices appear automatically in Home Assistant
- **Event Publishing**: Security events published as MQTT messages
- **Camera Status**: Online/offline status sensors
- **Motion Sensors**: Per-camera motion detection

## Requirements

- Home Assistant with MQTT integration
- MQTT broker (Mosquitto recommended)
- Network access between ArgusAI and MQTT broker

## Configuration

### Enable MQTT Integration

1. Navigate to **Settings > Integrations**
2. Enable **MQTT Integration**
3. Configure connection:

| Field | Description |
|-------|-------------|
| Host | MQTT broker address |
| Port | Broker port (default: 1883) |
| Username | MQTT username (optional) |
| Password | MQTT password (optional) |
| Topic Prefix | Base topic (default: argusai) |

4. Click **Test Connection**
5. Save configuration

### Home Assistant Setup

Ensure MQTT integration is configured in Home Assistant:

```yaml
# configuration.yaml
mqtt:
  broker: localhost
  port: 1883
  discovery: true
  discovery_prefix: homeassistant
```

## Discovered Devices

ArgusAI creates these entities in Home Assistant:

### Binary Sensors

- `binary_sensor.argusai_camera_name_motion` - Motion detection
- `binary_sensor.argusai_camera_name_person` - Person detection
- `binary_sensor.argusai_camera_name_vehicle` - Vehicle detection

### Sensors

- `sensor.argusai_camera_name_status` - Camera status
- `sensor.argusai_camera_name_last_event` - Last event timestamp

## Event Publishing

Events are published to MQTT topics:

```
argusai/events/{camera_id}
```

Payload example:
```json
{
  "event_id": "uuid",
  "timestamp": "2025-12-23T10:30:00Z",
  "camera_id": "camera-1",
  "camera_name": "Front Door",
  "detection_type": "person",
  "description": "Person approaching",
  "confidence": 85
}
```

## Automation Examples

### Notify on Person Detection

```yaml
automation:
  - alias: "ArgusAI Person Alert"
    trigger:
      platform: state
      entity_id: binary_sensor.argusai_front_door_person
      to: "on"
    action:
      service: notify.mobile_app
      data:
        title: "Person Detected"
        message: "Person at {{ trigger.to_state.attributes.camera_name }}"
```

### Log Events to History

```yaml
automation:
  - alias: "Log ArgusAI Events"
    trigger:
      platform: mqtt
      topic: argusai/events/#
    action:
      service: logbook.log
      data:
        name: "ArgusAI"
        message: "{{ trigger.payload_json.description }}"
```

## Troubleshooting

### Devices Not Appearing

- Verify MQTT discovery is enabled in HA
- Check MQTT broker connection
- Restart Home Assistant after enabling

### Events Not Publishing

- Check MQTT connection status in ArgusAI settings
- Verify topic prefix matches HA discovery prefix
- Check MQTT broker logs for errors
