# HomeKit Troubleshooting Guide

This guide covers common issues and solutions when integrating ArgusAI with Apple HomeKit (Story P7-1.2).

## Table of Contents

- [Discovery Issues](#discovery-issues)
- [Pairing Problems](#pairing-problems)
- [Event Delivery Issues](#event-delivery-issues)
- [Network Configuration](#network-configuration)
- [Firewall Requirements](#firewall-requirements)
- [Diagnostic Tools](#diagnostic-tools)

---

## Discovery Issues

### Home App Can't Find ArgusAI Bridge

**Symptoms:**
- Apple Home app shows "No accessories found"
- QR code scan times out
- Manual code entry fails

**Solutions:**

1. **Check mDNS/Bonjour service**
   - HomeKit uses mDNS (Bonjour) for device discovery
   - Verify mDNS is working on your network

   ```bash
   # macOS - Check for HAP services
   dns-sd -B _hap._tcp

   # Linux - Check for HAP services
   avahi-browse -a | grep hap
   ```

2. **Verify HomeKit bridge is running**
   - Check Settings > HomeKit in ArgusAI web UI
   - Bridge status should show "Running"
   - Use the "Test Connectivity" button

3. **Check network isolation**
   - iOS device must be on the same network subnet as ArgusAI
   - Some routers isolate devices - check "AP isolation" or "Client isolation" settings
   - Guest networks often block mDNS

4. **Restart the HomeKit bridge**
   - Toggle HomeKit off, wait 5 seconds, toggle back on
   - This restarts mDNS advertisement

### Bridge Discovered But Pairing Fails

**Symptoms:**
- Home app finds the bridge
- Pairing code rejected or times out

**Solutions:**

1. **Verify pairing code**
   - Double-check the 8-digit code matches exactly
   - Use the QR code if available for reliable scanning

2. **Reset pairing state**
   - Click "Reset Pairing" in HomeKit settings
   - This generates a new pairing code
   - Re-pair with the new code

3. **Check for duplicate bridge names**
   - If you have another HomeKit bridge with the same name, conflicts can occur
   - Change the bridge name in settings

---

## Pairing Problems

### "Accessory Already Paired" Error

**Symptoms:**
- Home app says accessory is already paired
- But no pairing exists in current Home

**Solutions:**

1. **Reset HomeKit pairing**
   - Go to Settings > HomeKit in ArgusAI
   - Click "Reset Pairing"
   - This clears the accessory state file

2. **Remove from another Home**
   - If previously paired to a different Apple Home
   - You must remove it from that Home first
   - Or reset pairing on ArgusAI side

### Pairing Keeps Disconnecting

**Symptoms:**
- Pairing succeeds but disconnects after a while
- Sensors show "No Response" in Home app

**Solutions:**

1. **Check network stability**
   - Ensure ArgusAI server has stable network
   - Check for IP address changes (use static IP)

2. **Verify port accessibility**
   - TCP port 51826 must be accessible continuously
   - See [Firewall Requirements](#firewall-requirements)

3. **Check server resources**
   - HomeKit bridge runs in a background thread
   - Ensure server has adequate CPU/memory

---

## Event Delivery Issues

### Motion Events Not Triggering

**Symptoms:**
- Motion detected in ArgusAI events
- HomeKit automations don't trigger
- Sensors show stale state

**Solutions:**

1. **Check camera-sensor mapping**
   - Verify cameras are enabled for HomeKit
   - Each camera creates a motion sensor

2. **Verify event processing**
   - Check HomeKit diagnostics panel
   - Look for "Last Event Delivery" timestamp
   - Ensure events are reaching the HomeKit service

3. **Check automation configuration**
   - In Home app, verify automation is enabled
   - Test by manually triggering (if possible)

### Events Delayed

**Symptoms:**
- Motion events arrive late in HomeKit
- Automations trigger seconds after actual motion

**Solutions:**

1. **Normal latency**
   - Some delay is normal (1-3 seconds typical)
   - AI description takes ~1-2 seconds
   - Event propagation adds small overhead

2. **Reduce processing time**
   - Use faster AI provider
   - Consider disabling AI descriptions for HomeKit-only events

---

## Network Configuration

### Binding to Specific IP Address

For multi-homed servers or Docker deployments, you may need to bind to a specific IP:

**Environment Variable:**
```bash
HOMEKIT_BIND_ADDRESS=192.168.1.100
```

**Use Cases:**
- Docker containers with multiple networks
- Servers with multiple NICs
- VPN setups where default route isn't optimal

### mDNS Interface Configuration

If mDNS advertisement isn't working on the correct interface:

**Environment Variable:**
```bash
HOMEKIT_MDNS_INTERFACE=eth0
```

**Note:** This is rarely needed. Only use if auto-detection fails.

---

## Firewall Requirements

HomeKit requires specific ports to be open:

### Required Ports

| Port | Protocol | Purpose | Notes |
|------|----------|---------|-------|
| 5353 | UDP | mDNS/Bonjour | Multicast discovery |
| 51826 | TCP | HAP protocol | Default HomeKit port |

### Firewall Configuration Commands

#### Linux (ufw)
```bash
# Allow mDNS multicast
sudo ufw allow 5353/udp comment 'mDNS for HomeKit'

# Allow HomeKit HAP port
sudo ufw allow 51826/tcp comment 'HomeKit HAP'

# Verify rules
sudo ufw status numbered
```

#### Linux (iptables)
```bash
# Allow mDNS multicast
sudo iptables -A INPUT -p udp --dport 5353 -j ACCEPT

# Allow HomeKit HAP port
sudo iptables -A INPUT -p tcp --dport 51826 -j ACCEPT

# Save rules (Debian/Ubuntu)
sudo iptables-save > /etc/iptables/rules.v4
```

#### Linux (firewalld)
```bash
# Allow mDNS
sudo firewall-cmd --permanent --add-service=mdns

# Allow HomeKit HAP port
sudo firewall-cmd --permanent --add-port=51826/tcp

# Reload
sudo firewall-cmd --reload
```

#### macOS
```bash
# macOS firewall is typically configured through System Settings
# If using app-level firewall, ensure ArgusAI is allowed

# Check if mDNSResponder is running
launchctl list | grep mDNSResponder
```

#### Docker
```yaml
# docker-compose.yml
services:
  argusai:
    ports:
      - "51826:51826"       # HomeKit HAP
      - "5353:5353/udp"     # mDNS (optional - host network may be needed)

    # For mDNS, host network is often more reliable:
    # network_mode: host
```

### Router/Network Level

- **AP Isolation**: Must be disabled for HomeKit discovery
- **mDNS Reflector**: Enable if running VLANs
- **IGMP Snooping**: Can affect multicast; test if issues persist

---

## Diagnostic Tools

### Built-in Diagnostics

1. **HomeKit Diagnostics Panel**
   - Settings > HomeKit > Diagnostics (collapsible)
   - Shows bridge status, mDNS advertising, connected clients
   - Recent logs with timestamp and category

2. **Connectivity Test Button**
   - Click "Test Connectivity" in HomeKit settings
   - Tests mDNS visibility and port accessibility
   - Shows specific firewall issues and recommendations

### Command-Line Tools

#### macOS
```bash
# Discover all HAP services
dns-sd -B _hap._tcp

# Get detailed service info
dns-sd -L "ArgusAI" _hap._tcp

# Browse all Bonjour services
dns-sd -B _services._dns-sd._udp
```

#### Linux
```bash
# Discover HAP services (requires avahi-utils)
avahi-browse -r _hap._tcp

# Check avahi daemon status
systemctl status avahi-daemon

# View all mDNS advertisements
avahi-browse -a
```

### Python Debug Script

```python
# test_homekit_discovery.py
from zeroconf import Zeroconf, ServiceBrowser, ServiceListener

class MyListener(ServiceListener):
    def add_service(self, zc, type_, name):
        print(f"Found: {name}")
        info = zc.get_service_info(type_, name)
        if info:
            print(f"  Address: {info.parsed_addresses()}")
            print(f"  Port: {info.port}")

zc = Zeroconf()
browser = ServiceBrowser(zc, "_hap._tcp.local.", MyListener())
input("Press Enter to exit...\n")
zc.close()
```

---

## Common Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| "mDNS service not visible" | UDP 5353 blocked or avahi not running | Open firewall, start mDNS daemon |
| "TCP port not accessible" | Port 51826 blocked | Open firewall, check bind address |
| "HAP-python not installed" | Missing dependency | `pip install HAP-python` |
| "zeroconf library not installed" | Missing test dependency | `pip install zeroconf` |
| "No Response" in Home app | Bridge offline or network issue | Check server status, restart bridge |

---

## Getting Help

If issues persist after following this guide:

1. Check HomeKit diagnostics panel for recent errors
2. Review backend logs for HomeKit-related entries
3. Run connectivity test and note all issues
4. Verify all firewall ports are open
5. File an issue with diagnostic information
