---
sidebar_position: 10
---

# Troubleshooting

Common issues and solutions for ArgusAI.

## Installation Issues

### Python Version Error

**Error**: `Python 3.11 or higher is required`

**Solution**:
```bash
# Check Python version
python3 --version

# Install Python 3.11+ via pyenv
pyenv install 3.11.0
pyenv global 3.11.0
```

### Node.js Version Error

**Error**: `Node.js 18 or higher is required`

**Solution**:
```bash
# Check Node version
node --version

# Install via nvm
nvm install 20
nvm use 20
```

### Database Migration Failed

**Error**: `alembic.util.exc.CommandError: Can't locate revision`

**Solution**:
```bash
cd backend
alembic stamp head
alembic upgrade head
```

## Camera Issues

### RTSP Connection Failed

**Symptoms**: Camera shows offline, no frames captured

**Checklist**:
1. Verify RTSP URL format: `rtsp://user:pass@ip:port/path`
2. Test with VLC: `vlc rtsp://...`
3. Check firewall allows RTSP port (usually 554)
4. Verify camera credentials

### UniFi Protect Connection Failed

**Error**: `Unable to connect to Protect controller`

**Solutions**:
1. Use IP address instead of hostname
2. Verify local user credentials (not Ubiquiti SSO)
3. Check port 443 is accessible
4. Disable SSL verification for self-signed certs

### USB Camera Not Found

**Error**: `No video devices found`

**Solutions**:
```bash
# List available devices
ls -la /dev/video*

# Check permissions
sudo usermod -a -G video $USER
# Logout and login again
```

## AI Provider Issues

### API Key Invalid

**Error**: `401 Unauthorized` or `Invalid API key`

**Solutions**:
1. Verify API key is correct (no extra spaces)
2. Check key has required permissions
3. Ensure key is not expired
4. Try regenerating the API key

### Rate Limited

**Error**: `429 Too Many Requests`

**Solutions**:
1. Reduce frame count per analysis
2. Enable cost caps in settings
3. Use fallback providers
4. Wait and retry

### Timeout Errors

**Error**: `Request timeout` or `AI analysis failed`

**Solutions**:
1. Check network connectivity
2. Reduce image size/quality
3. Try a different provider
4. Increase timeout in settings

## Push Notification Issues

### Notifications Not Working

**Checklist**:
1. HTTPS is enabled (required for web push)
2. Browser notifications are allowed
3. Service worker is registered
4. Test notification works

### HTTPS Not Working

**Error**: `SSL certificate error`

**Generate self-signed certificate**:
```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout data/certs/key.pem \
  -out data/certs/cert.pem \
  -subj "/CN=localhost"
```

**Configure environment**:
```bash
SSL_ENABLED=true
SSL_CERT_FILE=data/certs/cert.pem
SSL_KEY_FILE=data/certs/key.pem
```

### Push Only Works Once

**Issue**: First notification works, subsequent ones don't

**Solutions**:
1. Check service worker console for errors
2. Verify push subscription is persisted
3. Clear browser cache and re-subscribe
4. Check backend push service logs

## HomeKit Issues

### Bridge Not Discoverable

**Solutions**:
1. Ensure mDNS/Bonjour is working
2. Check no firewall blocking discovery
3. Restart HomeKit bridge service
4. Reset pairing and try again

### Pairing Failed

**Error**: `Accessory not responding`

**Solutions**:
1. Reset accessory in ArgusAI settings
2. Remove old pairing from Home app
3. Restart both ArgusAI and Home app
4. Check network connectivity

## MQTT Issues

### Connection Refused

**Error**: `MQTT connection refused`

**Solutions**:
1. Verify MQTT broker is running
2. Check host and port are correct
3. Verify credentials if auth is enabled
4. Check firewall allows MQTT port

### Devices Not Appearing in Home Assistant

**Solutions**:
1. Verify MQTT discovery is enabled in HA
2. Check topic prefix matches HA configuration
3. Restart Home Assistant
4. Check MQTT broker logs

## Performance Issues

### High CPU Usage

**Solutions**:
1. Reduce number of active cameras
2. Lower frame rate for analysis
3. Disable motion detection on quiet cameras
4. Increase event processing interval

### High Memory Usage

**Solutions**:
1. Reduce frame buffer size
2. Enable aggressive cleanup
3. Reduce concurrent AI requests
4. Restart services periodically

### Slow Event Processing

**Solutions**:
1. Use faster AI provider
2. Reduce frame count
3. Enable multi-frame instead of video mode
4. Check network latency to AI providers

## Getting Help

If these solutions don't resolve your issue:

1. Check [GitHub Issues](https://github.com/bbengt1/argusai/issues)
2. Search for similar problems
3. Create a new issue with:
   - ArgusAI version
   - Operating system
   - Relevant logs
   - Steps to reproduce
