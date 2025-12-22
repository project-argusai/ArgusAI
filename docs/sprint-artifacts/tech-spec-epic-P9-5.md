# Epic Technical Specification: Infrastructure & DevOps

Date: 2025-12-22
Author: Brent
Epic ID: P9-5
Status: Draft

---

## Overview

Epic P9-5 establishes secure connections and automated development pipelines. This epic delivers SSL/HTTPS support for production-ready security and n8n integration for 24/7 automated development capability using Claude Code and BMAD workflows.

The infrastructure improvements enable push notifications (which require HTTPS), secure camera connections, and trusted certificate management. The n8n pipeline creates an end-to-end automation system from story creation through code review and deployment.

## Objectives and Scope

**In Scope:**
- SSL/HTTPS support for backend server
- Let's Encrypt certificate automation
- Self-signed certificate generation option
- n8n instance deployment and configuration
- n8n integration with Claude Code CLI
- n8n integration with BMAD workflows
- Pipeline monitoring dashboard
- Human approval gates for PR merges

**Out of Scope:**
- Cloud deployment configurations (AWS, GCP, Azure)
- Kubernetes orchestration
- Load balancing / horizontal scaling
- Custom domain management (handled by user)
- Advanced CI/CD beyond n8n (GitHub Actions is separate)

## System Architecture Alignment

This epic introduces new infrastructure components to the existing system:

| Component | Files Affected | Changes |
|-----------|---------------|---------|
| Backend Server | `backend/main.py` | SSL configuration |
| Backend Config | `backend/app/core/config.py` | SSL settings |
| Install Script | `scripts/install.sh` | Certificate setup |
| n8n Setup | `scripts/setup-n8n.sh` | New script |
| n8n Workflows | `n8n/workflows/` | New directory |
| Docker Compose | `docker-compose.yml` | n8n service |
| Documentation | `docs/` | SSL & n8n guides |

### Architecture Diagram

```
                                    ┌─────────────────────────────────────┐
                                    │        ArgusAI Infrastructure       │
                                    └─────────────────────────────────────┘
                                                      │
                    ┌─────────────────────────────────┼─────────────────────────────────┐
                    │                                 │                                 │
           ┌────────▼────────┐               ┌───────▼───────┐               ┌─────────▼────────┐
           │   SSL/HTTPS     │               │    ArgusAI    │               │      n8n         │
           │   (Nginx/       │◄─────────────►│   Backend     │               │   Automation     │
           │   Uvicorn)      │  TLS 1.2+     │   (FastAPI)   │               │   (:5678)        │
           └─────────────────┘               └───────────────┘               └──────────────────┘
                    │                                 │                                 │
        ┌───────────┼───────────┐                    │                    ┌────────────┼────────────┐
        │           │           │                    │                    │            │            │
   ┌────▼────┐ ┌────▼────┐ ┌────▼────┐        ┌─────▼─────┐        ┌──────▼────┐ ┌─────▼────┐ ┌────▼─────┐
   │Let's    │ │Self-    │ │HTTP     │        │  Browser  │        │ Claude    │ │ BMAD     │ │ GitHub   │
   │Encrypt  │ │Signed   │ │Redirect │        │  Clients  │        │ Code CLI  │ │ Workflows│ │ Webhooks │
   └─────────┘ └─────────┘ └─────────┘        └───────────┘        └───────────┘ └──────────┘ └──────────┘
```

---

## Detailed Design

### Services and Modules

| Service/Module | Responsibility | Inputs | Outputs |
|---------------|----------------|--------|---------|
| SSL Configuration | TLS termination | Cert files | Secure connections |
| Certificate Manager | Cert generation/renewal | Domain, options | Certificates |
| n8n Service | Workflow orchestration | Triggers, data | Executed workflows |
| Claude Code Node | AI code generation | Prompts | Code changes |
| BMAD Node | Methodology execution | Workflow commands | Story artifacts |
| Approval Gate | Human review | PR details | Approve/reject |

### Data Models and Contracts

**SSL Configuration Settings:**
```python
class SSLSettings(BaseSettings):
    ssl_enabled: bool = False
    ssl_cert_file: Optional[str] = None  # Path to certificate
    ssl_key_file: Optional[str] = None   # Path to private key
    ssl_redirect_http: bool = True       # Redirect HTTP to HTTPS
    ssl_min_version: str = "TLSv1_2"     # Minimum TLS version

    class Config:
        env_prefix = "SSL_"
```

**n8n Workflow Execution Record:**
```json
{
  "execution_id": "uuid",
  "workflow_name": "create-story",
  "trigger": "github_webhook",
  "status": "running|completed|failed|waiting_approval",
  "started_at": "2025-12-22T10:00:00Z",
  "completed_at": null,
  "approval_status": "pending|approved|rejected",
  "approved_by": null,
  "output": {}
}
```

**Certificate Generation Options:**
```python
class CertificateOptions:
    method: str  # "letsencrypt", "self-signed", "none"
    domain: Optional[str]  # Required for Let's Encrypt
    email: Optional[str]   # For Let's Encrypt notifications
    auto_renew: bool = True
    cert_path: str = "data/certs/"
```

### APIs and Interfaces

**Internal SSL Configuration API:**

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/system/ssl-status` | Check SSL configuration status |

**SSL Status Response:**
```json
{
  "ssl_enabled": true,
  "certificate_valid": true,
  "certificate_expires": "2026-03-22T00:00:00Z",
  "certificate_issuer": "Let's Encrypt",
  "tls_version": "TLSv1.3"
}
```

**n8n Webhook Endpoints (in n8n):**

| Webhook | Trigger | Action |
|---------|---------|--------|
| `/webhook/github-issue` | New GitHub issue | Create story workflow |
| `/webhook/story-complete` | Story marked done | Code review workflow |
| `/webhook/pr-ready` | PR created | Approval gate |
| `/webhook/approve/{id}` | Human approval | Resume workflow |
| `/webhook/reject/{id}` | Human rejection | Cancel workflow |

### Workflows and Sequencing

**SSL Certificate Setup Flow:**
```
1. User runs install script
2. Script prompts for SSL option:
   - Let's Encrypt → Enter domain → Run certbot
   - Self-signed → Generate with openssl
   - Skip → HTTP only mode
3. Certificates stored in data/certs/
4. Environment variables set
5. Backend starts with SSL configuration
6. (Optional) Nginx configured for termination
```

**n8n Automated Development Pipeline:**
```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  GitHub Webhook │────►│  n8n Trigger    │────►│  Create Story   │
│  (New Issue)    │     │                 │     │  (BMAD)         │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                          │
                        ┌─────────────────┐     ┌─────────▼────────┐
                        │  Story Context  │◄────│  Draft Story     │
                        │  Assembly       │     │  Created         │
                        └────────┬────────┘     └──────────────────┘
                                 │
                        ┌────────▼────────┐     ┌─────────────────┐
                        │  Claude Code    │────►│  Code Changes   │
                        │  Implementation │     │  Generated      │
                        └────────┬────────┘     └──────────────────┘
                                 │
                        ┌────────▼────────┐     ┌─────────────────┐
                        │  Run Tests      │────►│  Test Results   │
                        │                 │     │                 │
                        └────────┬────────┘     └──────────────────┘
                                 │
                        ┌────────▼────────┐     ┌─────────────────┐
                        │  Code Review    │────►│  Review Notes   │
                        │  (Claude Code)  │     │                 │
                        └────────┬────────┘     └──────────────────┘
                                 │
                        ┌────────▼────────┐     ┌─────────────────┐
                        │  Create PR      │────►│  PR Created     │
                        │                 │     │                 │
                        └────────┬────────┘     └──────────────────┘
                                 │
                        ┌────────▼────────┐     ┌─────────────────┐
                        │  Approval Gate  │────►│  Notification   │
                        │  (Wait)         │     │  Sent           │
                        └────────┬────────┘     └──────────────────┘
                                 │
                        ┌────────▼────────┐     ┌─────────────────┐
                        │  Merge & Deploy │────►│  Complete       │
                        │                 │     │                 │
                        └─────────────────┘     └─────────────────┘
```

---

## Non-Functional Requirements

### Performance

| Metric | Target | Measurement |
|--------|--------|-------------|
| SSL handshake latency | <100ms | Network measurement |
| n8n workflow start | <5 seconds | From trigger to first node |
| Story creation workflow | <5 minutes | End-to-end BMAD |
| Implementation workflow | <30 minutes | Claude Code execution |
| Approval notification | <10 seconds | From PR to notification |

### Security

- SSL/TLS 1.2 minimum, TLS 1.3 preferred
- Let's Encrypt certificates auto-renew 30 days before expiration
- Self-signed certificates use 2048-bit RSA minimum
- Private keys stored with 600 permissions
- n8n credentials stored in encrypted format
- API keys never logged or exposed
- Approval gates require authenticated user

### Reliability/Availability

- Certificate renewal runs daily, retries on failure
- n8n workflows have automatic retry (3 attempts, exponential backoff)
- Failed workflows notify administrators
- Approval gates timeout after 7 days
- n8n data persisted to survive container restarts

### Observability

- Log all SSL certificate events (renewal, expiration warnings)
- Log all n8n workflow executions with duration and status
- Track approval gate wait times
- Monitor Claude Code API usage and costs
- Dashboard shows active workflows, success rates, queue depth

---

## Dependencies and Integrations

### Backend Dependencies (requirements.txt)

```
# Existing - no new dependencies for SSL
uvicorn>=0.30.0  # Already has SSL support
```

### System Dependencies

```bash
# Let's Encrypt
certbot>=2.0.0
python3-certbot-nginx  # Optional for nginx integration

# n8n
node>=18.0.0  # For npm install
# OR
docker>=24.0.0  # For docker deployment
```

### n8n Dependencies (n8n custom nodes)

```json
{
  "n8n-nodes-base": "^1.0.0",
  "n8n-nodes-execute-command": "*"
}
```

### External Services

| Service | Purpose | Impact |
|---------|---------|--------|
| Let's Encrypt | Free certificates | HTTPS for public domains |
| Claude Code CLI | AI code generation | Core automation capability |
| GitHub API | PR creation, webhooks | Pipeline triggers |
| Slack/Discord | Notifications | Human approvals |

---

## Acceptance Criteria (Authoritative)

### P9-5.1: Add SSL/HTTPS Support to Backend

**AC-5.1.1:** Given SSL certificates are configured, when I access ArgusAI, then the connection is over HTTPS (TLS 1.2+)
**AC-5.1.2:** Given SSL is enabled, when I access ArgusAI, then the browser shows a secure connection indicator
**AC-5.1.3:** Given I access via HTTP, when HTTPS is enabled, then I am redirected to HTTPS
**AC-5.1.4:** Given certificates are not configured, when I start ArgusAI, then it runs on HTTP with a warning in logs
**AC-5.1.5:** Given certificates are not configured, when push notifications are enabled, then a warning appears about HTTPS requirement

### P9-5.2: Add Certificate Generation to Install Script

**AC-5.2.1:** Given I run the install script, when prompted for SSL, then I see options: Let's Encrypt, Self-signed, Skip
**AC-5.2.2:** Given I choose Let's Encrypt, when I provide my domain and email, then certbot obtains certificates
**AC-5.2.3:** Given Let's Encrypt succeeds, when setup completes, then auto-renewal is configured via cron/systemd
**AC-5.2.4:** Given I choose Self-signed, when generation runs, then a self-signed cert is created in data/certs/
**AC-5.2.5:** Given I choose Self-signed, when setup completes, then I'm warned about browser security warnings
**AC-5.2.6:** Given I choose Skip, when setup completes, then ArgusAI runs on HTTP only

### P9-5.3: Deploy n8n Instance

**AC-5.3.1:** Given I run the n8n setup script, when using Docker mode, then n8n container starts and persists data
**AC-5.3.2:** Given I run the n8n setup script, when using npm mode, then n8n service is installed and configured
**AC-5.3.3:** Given n8n is running, when I access port 5678, then the n8n UI is accessible
**AC-5.3.4:** Given n8n is running, when I create a workflow, then it persists after restart
**AC-5.3.5:** Given n8n setup completes, when viewing documentation, then webhook URL configuration is documented

### P9-5.4: Create n8n Claude Code Integration

**AC-5.4.1:** Given n8n workflow triggers, when Claude Code node executes, then it runs claude-code CLI with prompt
**AC-5.4.2:** Given Claude Code CLI runs, when code changes are made, then output is captured in workflow
**AC-5.4.3:** Given Claude Code makes file changes, when workflow continues, then git status shows modifications
**AC-5.4.4:** Given Claude Code fails, when error occurs, then workflow handles error gracefully with retry
**AC-5.4.5:** Given Claude Code succeeds, when output is returned, then subsequent nodes can access results

### P9-5.5: Create n8n BMAD Workflow Integration

**AC-5.5.1:** Given n8n receives story creation trigger, when BMAD node executes, then create-story skill is invoked
**AC-5.5.2:** Given BMAD workflow runs, when create-story completes, then story file path is extracted from output
**AC-5.5.3:** Given story is created, when story-context node runs, then context XML is generated
**AC-5.5.4:** Given context is ready, when dev-story node runs, then implementation begins
**AC-5.5.5:** Given BMAD workflow fails, when error occurs, then failure is logged and admin notified

### P9-5.6: Build n8n Monitoring Dashboard and Approval Gates

**AC-5.6.1:** Given n8n workflows are running, when I view dashboard, then I see active workflows and status
**AC-5.6.2:** Given dashboard is open, when I view metrics, then I see success rate and average duration
**AC-5.6.3:** Given workflow reaches approval gate, when human review needed, then notification is sent
**AC-5.6.4:** Given approval notification sent, when I click approve link, then workflow resumes
**AC-5.6.5:** Given approval notification sent, when I click reject link, then workflow is cancelled
**AC-5.6.6:** Given approval action taken, when workflow updates, then approval is logged with timestamp and approver

---

## Traceability Mapping

| AC | Spec Section | Component(s) | Test Idea |
|----|--------------|--------------|-----------|
| AC-5.1.1-5 | SSL Configuration | main.py, config.py | Connect with curl -v |
| AC-5.2.1-6 | Certificate Manager | install.sh | Run script in each mode |
| AC-5.3.1-5 | n8n Service | setup-n8n.sh, docker-compose | Deploy and verify UI |
| AC-5.4.1-5 | Claude Code Node | n8n workflow | Execute workflow, verify output |
| AC-5.5.1-5 | BMAD Node | n8n workflow | Create story, verify artifacts |
| AC-5.6.1-6 | Dashboard/Gates | n8n UI, webhooks | Trigger approval, verify notification |

---

## Risks, Assumptions, Open Questions

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Let's Encrypt rate limits | Low | Medium | Test on staging domain first |
| n8n workflow complexity | Medium | Medium | Start with simple workflows, iterate |
| Claude Code API costs | Medium | Medium | Add budget alerts and limits |
| Approval gate spam | Low | Low | Rate limit notifications |

### Assumptions

- Users have domain for Let's Encrypt (or accept self-signed)
- n8n can access Claude Code CLI on host system
- GitHub webhooks can reach n8n instance
- Notification service (Slack/Discord) is available

### Open Questions

- **Q1:** Should n8n run in Docker or native Node.js?
  - **A:** Support both options, Docker preferred for isolation

- **Q2:** What notification channels should we support initially?
  - **A:** Slack and Discord, with webhook fallback

- **Q3:** Should approval gates have auto-timeout (auto-reject)?
  - **A:** Yes, 7-day timeout with warning at 5 days

- **Q4:** Should we support nginx reverse proxy for SSL termination?
  - **A:** Document as optional advanced configuration

---

## Test Strategy Summary

### Test Levels

| Level | Scope | Tools | Coverage |
|-------|-------|-------|----------|
| Unit | SSL config parsing | pytest | Configuration validation |
| Integration | Certificate generation | certbot, openssl | Cert file creation |
| E2E | n8n workflows | n8n test mode | Full pipeline |
| Manual | SSL in browser | Chrome/Firefox | Visual verification |

### Test Cases by Story

**P9-5.1 (SSL Support):**
- Test: Start with SSL_ENABLED=true and valid certs
- Test: Start with missing certs (graceful fallback)
- Test: HTTP to HTTPS redirect
- Test: TLS version negotiation

**P9-5.2 (Certificate Generation):**
- Test: Let's Encrypt with valid domain
- Test: Let's Encrypt with invalid domain (error handling)
- Test: Self-signed certificate generation
- Test: Certificate file permissions

**P9-5.3 (n8n Deployment):**
- Test: Docker deployment script
- Test: npm deployment script
- Test: n8n persistence across restart
- Test: n8n webhook accessibility

**P9-5.4 (Claude Code Integration):**
- Test: Execute simple prompt
- Test: Execute with file modifications
- Test: Handle API timeout
- Test: Handle rate limiting

**P9-5.5 (BMAD Integration):**
- Test: Create story workflow
- Test: Story context generation
- Test: Dev story execution
- Test: Workflow chaining

**P9-5.6 (Dashboard/Gates):**
- Test: View active workflows
- Test: Send approval notification
- Test: Process approval
- Test: Process rejection
- Test: Timeout handling

### Edge Cases

- Certificate expiration during runtime
- n8n container crash mid-workflow
- Claude Code timeout during implementation
- GitHub webhook delivery failure
- Concurrent approval requests
- Network partition during workflow execution

---

## Implementation Details

### SSL Configuration Code

```python
# backend/app/core/config.py
class Settings(BaseSettings):
    # ... existing settings ...

    # SSL Settings
    ssl_enabled: bool = False
    ssl_cert_file: Optional[str] = None
    ssl_key_file: Optional[str] = None
    ssl_redirect_http: bool = True

    @validator("ssl_cert_file", "ssl_key_file")
    def validate_ssl_files(cls, v, values):
        if values.get("ssl_enabled") and v and not Path(v).exists():
            raise ValueError(f"SSL file not found: {v}")
        return v
```

```python
# backend/main.py
if settings.ssl_enabled and settings.ssl_cert_file and settings.ssl_key_file:
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=443,
        ssl_certfile=settings.ssl_cert_file,
        ssl_keyfile=settings.ssl_key_file,
    )
else:
    logger.warning("SSL not configured, running on HTTP")
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
```

### n8n Setup Script

```bash
#!/bin/bash
# scripts/setup-n8n.sh

N8N_DATA_DIR="${DATA_DIR:-./data}/n8n"
N8N_PORT="${N8N_PORT:-5678}"

echo "Setting up n8n automation..."

# Create data directory
mkdir -p "$N8N_DATA_DIR"

# Check for Docker
if command -v docker &> /dev/null; then
    echo "Using Docker deployment..."
    docker run -d \
        --name argusai-n8n \
        --restart unless-stopped \
        -p "$N8N_PORT:5678" \
        -v "$N8N_DATA_DIR:/home/node/.n8n" \
        -e N8N_BASIC_AUTH_ACTIVE=true \
        -e N8N_BASIC_AUTH_USER="${N8N_USER:-admin}" \
        -e N8N_BASIC_AUTH_PASSWORD="${N8N_PASSWORD}" \
        n8nio/n8n
else
    echo "Docker not found, using npm installation..."
    npm install -g n8n

    # Create systemd service
    cat > /etc/systemd/system/n8n.service << EOF
[Unit]
Description=n8n Workflow Automation
After=network.target

[Service]
Type=simple
User=$USER
Environment=N8N_PORT=$N8N_PORT
Environment=N8N_USER_FOLDER=$N8N_DATA_DIR
ExecStart=$(which n8n)
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable n8n
    systemctl start n8n
fi

echo "n8n is running at http://localhost:$N8N_PORT"
```

### n8n Workflow: Story Creation

```json
{
  "name": "BMAD Story Creation",
  "nodes": [
    {
      "name": "GitHub Webhook",
      "type": "n8n-nodes-base.webhook",
      "parameters": {
        "path": "github-issue",
        "httpMethod": "POST"
      }
    },
    {
      "name": "Create Story",
      "type": "n8n-nodes-base.executeCommand",
      "parameters": {
        "command": "cd /path/to/argusai && claude --skill bmad:bmm:workflows:create-story --prompt '{{$json.issue.title}}'"
      }
    },
    {
      "name": "Extract Story Path",
      "type": "n8n-nodes-base.code",
      "parameters": {
        "jsCode": "const output = $input.first().json.stdout;\nconst match = output.match(/Created: (.*\\.md)/);\nreturn [{ storyPath: match ? match[1] : null }];"
      }
    },
    {
      "name": "Generate Context",
      "type": "n8n-nodes-base.executeCommand",
      "parameters": {
        "command": "cd /path/to/argusai && claude --skill bmad:bmm:workflows:story-context"
      }
    },
    {
      "name": "Implement Story",
      "type": "n8n-nodes-base.executeCommand",
      "parameters": {
        "command": "cd /path/to/argusai && claude --skill bmad:bmm:workflows:dev-story"
      },
      "continueOnFail": true
    },
    {
      "name": "Run Tests",
      "type": "n8n-nodes-base.executeCommand",
      "parameters": {
        "command": "cd /path/to/argusai && npm test && pytest backend/tests/"
      }
    },
    {
      "name": "Create PR",
      "type": "n8n-nodes-base.executeCommand",
      "parameters": {
        "command": "cd /path/to/argusai && gh pr create --title '{{$json.issue.title}}' --body 'Automated implementation'"
      }
    },
    {
      "name": "Send Approval Request",
      "type": "n8n-nodes-base.slack",
      "parameters": {
        "channel": "#dev-approvals",
        "text": "PR ready for review: {{$json.pr_url}}\n\nApprove: {{$env.N8N_URL}}/webhook/approve/{{$executionId}}\nReject: {{$env.N8N_URL}}/webhook/reject/{{$executionId}}"
      }
    },
    {
      "name": "Wait for Approval",
      "type": "n8n-nodes-base.wait",
      "parameters": {
        "resume": "webhook",
        "webhookSuffix": "={{$executionId}}"
      }
    },
    {
      "name": "Merge PR",
      "type": "n8n-nodes-base.executeCommand",
      "parameters": {
        "command": "gh pr merge {{$json.pr_number}} --squash"
      }
    }
  ]
}
```

### Certificate Generation Commands

```bash
# Let's Encrypt (certbot)
certbot certonly --standalone \
  -d yourdomain.com \
  --email your@email.com \
  --agree-tos \
  --non-interactive \
  --cert-path /path/to/argusai/data/certs/

# Self-signed certificate
openssl req -x509 \
  -newkey rsa:2048 \
  -keyout data/certs/key.pem \
  -out data/certs/cert.pem \
  -days 365 \
  -nodes \
  -subj "/CN=localhost"
```

---

_Generated by BMAD Epic Tech Context Workflow_
_Date: 2025-12-22_
_For: Brent_
