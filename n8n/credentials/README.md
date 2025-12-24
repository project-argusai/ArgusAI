# n8n Credentials Setup

This guide explains how to configure credentials for the n8n Claude Code integration workflows.

## Required Credentials

### 1. ANTHROPIC_API_KEY

The Claude Code CLI requires an Anthropic API key for authentication.

**Getting an API Key:**
1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Sign in or create an account
3. Navigate to API Keys
4. Create a new API key
5. Copy the key (it won't be shown again)

**Setting the Key:**

The API key must be available as an environment variable to the n8n process.

**Docker Deployment:**
```bash
docker run -d \
  --name n8n \
  -p 5678:5678 \
  -e ANTHROPIC_API_KEY=sk-ant-api03-xxxxx \
  -e ARGUSAI_PROJECT_PATH=/app/argusai \
  -v /path/to/argusai:/app/argusai \
  n8nio/n8n
```

**Docker Compose:**
```yaml
services:
  n8n:
    image: n8nio/n8n
    environment:
      - ANTHROPIC_API_KEY=sk-ant-api03-xxxxx
      - ARGUSAI_PROJECT_PATH=/app/argusai
    volumes:
      - /path/to/argusai:/app/argusai
```

**systemd Service:**
```ini
[Service]
Environment="ANTHROPIC_API_KEY=sk-ant-api03-xxxxx"
Environment="ARGUSAI_PROJECT_PATH=/path/to/argusai"
ExecStart=/usr/local/bin/n8n start
```

**.env File (if supported by your deployment):**
```
ANTHROPIC_API_KEY=sk-ant-api03-xxxxx
ARGUSAI_PROJECT_PATH=/path/to/argusai
```

## Optional Credentials

### Notification Services (for error alerts)

If you want to add notifications when workflows fail:

**Slack:**
1. Create a Slack app at api.slack.com
2. Add Bot Token Scopes: `chat:write`
3. Install to workspace
4. In n8n: Credentials > New > Slack API
5. Add the Bot Token

**Email (SMTP):**
1. In n8n: Credentials > New > SMTP
2. Configure:
   - Host: Your SMTP server
   - Port: 587 (TLS) or 465 (SSL)
   - User: Your email
   - Password: App password or SMTP password

### GitHub (for PR automation)

If extending workflows to create PRs:

1. Create a Personal Access Token at github.com/settings/tokens
2. Required scopes: `repo`
3. In n8n: Credentials > New > GitHub API
4. Add the token

## Security Best Practices

1. **Never commit API keys** to version control
2. **Use environment variables** instead of hardcoding
3. **Rotate keys periodically** (every 90 days recommended)
4. **Use separate keys** for development and production
5. **Limit key permissions** where possible

## Verifying Credentials

### Test ANTHROPIC_API_KEY

```bash
# From the n8n container or host
claude --version
# Should output version info if key is valid
```

### Test in n8n

1. Open the workflow in n8n editor
2. Click "Execute Workflow" with a simple test prompt
3. Check the execution output for errors

## Troubleshooting

### "Invalid API key"

- Verify the key is correctly copied (no extra spaces)
- Check the key hasn't been revoked
- Ensure you're using an API key, not an OAuth token

### "Environment variable not found"

- Restart n8n after setting environment variables
- Verify the variable is set in the correct environment
- Check for typos in variable names

### "Permission denied to project path"

- Ensure the path in ARGUSAI_PROJECT_PATH exists
- Check file system permissions
- For Docker: verify volume mount is correct
