# UniFi Protect Troubleshooting Guide

This guide covers common issues and solutions when integrating UniFi Protect controllers with the Live Object AI Classifier.

## Table of Contents

- [Connection Issues](#connection-issues)
- [Authentication Errors](#authentication-errors)
- [SSL/Certificate Issues](#sslcertificate-issues)
- [Camera Discovery Problems](#camera-discovery-problems)
- [Event Processing Issues](#event-processing-issues)
- [Doorbell Integration](#doorbell-integration)
- [Performance Issues](#performance-issues)
- [WebSocket Connection Problems](#websocket-connection-problems)

---

## Connection Issues

### "Host unreachable" Error

**Symptoms:**
- Test Connection fails with "Host unreachable"
- Controller status shows "Disconnected"

**Solutions:**

1. **Verify IP address or hostname**
   - Ensure the UDM/Cloud Key/NVR IP address is correct
   - Try pinging the host: `ping 192.168.1.1`
   - If using hostname, verify DNS resolution

2. **Check network connectivity**
   - Ensure the backend server can reach the Protect controller
   - If running in Docker, check container networking
   - Verify firewall rules allow outbound HTTPS (port 443)

3. **Controller firmware**
   - Update UniFi Protect to the latest firmware version
   - Some older firmware versions have API compatibility issues

### "Connection timed out" Error

**Symptoms:**
- Test Connection hangs and then fails
- Controller takes too long to respond

**Solutions:**

1. **Network latency**
   - Check network path between backend and controller
   - Consider local deployment if controller is remote

2. **Controller load**
   - Large camera deployments (20+) may cause slower responses
   - Check UniFi Protect dashboard for controller CPU/memory usage

3. **Port blocking**
   - Verify port 443 is not blocked by firewall
   - Some corporate networks block unusual HTTPS traffic

---

## Authentication Errors

### "Authentication failed - check username and password"

**Symptoms:**
- Test Connection fails with 401 error
- "Invalid credentials" message

**Solutions:**

1. **Use local account (not SSO)**
   - UniFi SSO/Cloud accounts are NOT supported
   - Create a dedicated local account on the Protect controller:
     1. Open UniFi Protect web UI
     2. Go to Settings → Users
     3. Create new local user
     4. Assign "View Only" or "Admin" role

2. **Verify credentials**
   - Double-check username (case-sensitive)
   - Re-enter password (don't copy/paste special characters)
   - Test login via Protect web UI first

3. **Account locked**
   - After multiple failed attempts, account may be locked
   - Wait 15-30 minutes or unlock in Protect settings

### "Insufficient permissions" Error

**Symptoms:**
- Connection succeeds but cameras don't appear
- Event subscription fails

**Solutions:**

1. **Check user role**
   - User needs at least "View Only" access to cameras
   - For full functionality, "Admin" role is recommended

2. **Camera-specific permissions**
   - Some deployments restrict camera access by user
   - Verify the local account can see all desired cameras in Protect UI

---

## SSL/Certificate Issues

### "SSL certificate verification failed"

**Symptoms:**
- Test Connection fails with 502 error
- "Certificate verify failed" in logs

**Solutions:**

1. **Disable SSL verification** (recommended for local deployments)
   - In the Controller Form, turn OFF "Verify SSL Certificate"
   - Most UniFi deployments use self-signed certificates

2. **If SSL verification is required**
   - Import the controller's CA certificate to the backend server
   - Configure trusted certificates in the backend environment

3. **Certificate expired**
   - Check if the controller's certificate has expired
   - Regenerate certificates in UniFi OS settings

---

## Camera Discovery Problems

### Cameras Not Appearing

**Symptoms:**
- Connection successful but no cameras listed
- Discovery returns empty list

**Solutions:**

1. **Wait for bootstrap**
   - Initial discovery may take 5-10 seconds for large deployments
   - Refresh the camera list after a few seconds

2. **Camera adoption**
   - Only fully adopted cameras appear in discovery
   - Check Protect UI for cameras in "Adopting" state

3. **Controller type**
   - Verify using correct controller (UDM, Cloud Key, or NVR)
   - Each controller has its own camera list

### Camera Status "Disconnected"

**Symptoms:**
- Camera shows in list but status is "Disconnected"
- Thumbnails don't load

**Solutions:**

1. **Camera offline**
   - Check physical camera connection and power
   - Verify camera appears online in Protect UI

2. **Network issues**
   - Camera may have lost network connectivity
   - Check camera's network settings in Protect

3. **Firmware mismatch**
   - Update camera firmware to match controller version
   - Protect will indicate firmware update available

---

## Event Processing Issues

### Events Not Being Detected

**Symptoms:**
- Motion occurs but no events appear
- Dashboard shows no activity

**Solutions:**

1. **Enable AI analysis for camera**
   - Toggle "Enable AI" switch ON for the camera
   - Verify the camera is enabled (green indicator)

2. **Check event type filters**
   - Click "Filters" on the camera card
   - Ensure desired detection types are selected
   - "All Motion" captures everything but may be noisy

3. **Smart detection availability**
   - Not all camera models support smart detection
   - Older cameras may only support basic motion
   - Check camera specs in Protect UI

### Duplicate Events

**Symptoms:**
- Same event appears multiple times
- Event storm in dashboard

**Solutions:**

1. **Deduplication window**
   - Events within 5 seconds are deduplicated automatically
   - Very rapid events may still appear separately

2. **Multiple cameras**
   - Events from different cameras are intentionally separate
   - Use correlation view to see related multi-camera events

3. **Event filtering**
   - Reduce event types being analyzed
   - Filter to specific detection types (Person, Vehicle, etc.)

### AI Descriptions Missing

**Symptoms:**
- Events appear but have no AI description
- "Processing..." shown indefinitely

**Solutions:**

1. **Configure AI provider**
   - Go to Settings → AI Providers
   - Set up at least one provider (OpenAI recommended)

2. **API key issues**
   - Test API key in settings
   - Verify API quota/billing is active

3. **Snapshot unavailable**
   - AI needs event thumbnail to generate description
   - Check if thumbnail appears on event card

---

## Doorbell Integration

### Doorbell Ring Not Detected

**Symptoms:**
- Physical doorbell press not showing as event
- Ring events missing distinct styling

**Solutions:**

1. **Doorbell model support**
   - Verify doorbell is G4 Doorbell or G4 Doorbell Pro
   - Older models may not report ring events

2. **Enable doorbell camera**
   - Doorbell must be enabled for AI analysis
   - Check camera list for doorbell with bell icon

3. **Event type filter**
   - Ring events are detected automatically
   - No specific filter needed, but camera must be enabled

### Doorbell Events Show as Regular Motion

**Symptoms:**
- Ring appears but without doorbell styling
- `is_doorbell_ring` flag is false

**Solutions:**

1. **Firmware update**
   - Update doorbell firmware to latest version
   - Newer firmware provides better ring detection

2. **Press type**
   - Quick taps may not register as proper rings
   - Full button press should trigger ring event

---

## Performance Issues

### Slow Camera Discovery

**Symptoms:**
- Discovery takes more than 10 seconds
- UI appears frozen during discovery

**Solutions:**

1. **Large deployments**
   - 50+ cameras naturally take longer
   - Consider enabling only needed cameras

2. **Network latency**
   - High latency to controller slows discovery
   - Deploy backend closer to controller

3. **Controller resources**
   - Check UDM/NVR CPU and memory usage
   - Heavy recording load affects API response time

### High Event Latency

**Symptoms:**
- Events appear significantly after occurrence
- Timestamps show delay

**Solutions:**

1. **AI provider latency**
   - AI description generation is the main bottleneck
   - Configure faster provider (Grok or OpenAI GPT-4o mini)

2. **Event queue backup**
   - High event volume can cause queue delay
   - Filter to reduce event types being processed

3. **Database performance**
   - For large event history, consider PostgreSQL over SQLite
   - Ensure adequate disk I/O for database

---

## WebSocket Connection Problems

### Frequent Disconnections

**Symptoms:**
- Controller status flips between Connected/Disconnected
- Events stop for periods then resume

**Solutions:**

1. **Network stability**
   - Check for network interruptions
   - Use wired connection for backend server

2. **Controller resources**
   - WebSocket connections consume controller resources
   - Reduce other integrations if possible

3. **Reconnection backoff**
   - System automatically reconnects with exponential backoff
   - Initial reconnect in 1-2 seconds, then increasing delays

### "WebSocket connection closed unexpectedly"

**Symptoms:**
- Error in logs about closed connection
- Events stop without apparent reason

**Solutions:**

1. **Firewall/proxy issues**
   - WebSocket may be terminated by corporate firewalls
   - Configure proxy to allow persistent connections

2. **Controller restart**
   - Normal during Protect updates/restarts
   - System will auto-reconnect within 5 seconds

3. **Session timeout**
   - Re-authentication happens automatically
   - If persistent, check API credentials

---

## Getting Help

If issues persist after trying these solutions:

1. **Check logs**
   - Backend: `docker logs <container>` or check `logs/app.log`
   - Look for specific error codes and messages

2. **Enable debug logging**
   - Set `LOG_LEVEL=DEBUG` in backend `.env`
   - Restart backend to see detailed logs

3. **Report issues**
   - Open GitHub issue with:
     - Controller type and firmware version
     - Camera model(s)
     - Error messages from logs
     - Steps to reproduce

---

## Quick Reference

| Issue | First Thing to Try |
|-------|-------------------|
| Host unreachable | Verify IP, check ping |
| Auth failed | Use local account, not SSO |
| SSL error | Disable SSL verification |
| No cameras | Wait for bootstrap, check adoption |
| No events | Enable AI, check filters |
| Missing descriptions | Configure AI provider |
| Doorbell not detected | Update firmware |
| Slow discovery | Check network latency |
| Disconnections | Check network stability |
