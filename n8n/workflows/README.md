# n8n Workflow Templates

This directory contains n8n workflow templates for integrating Claude Code CLI with the ArgusAI automation system.

## Available Workflows

### claude-code-basic.json

Basic Claude Code execution workflow with minimal setup.

**Flow:**
```
Webhook → Execute Claude Code → Parse Output → Check Success → Response
```

**Features:**
- Webhook trigger for external invocation
- Claude Code CLI execution with prompt
- Output parsing for success/failure detection
- JSON response with execution results

**Webhook Endpoint:** `POST /webhook/claude-code`

**Request Body:**
```json
{
  "prompt": "Your prompt for Claude Code"
}
```

**Success Response (200):**
```json
{
  "success": true,
  "output": "Claude Code output...",
  "filesModified": ["path/to/file.ts"],
  "executedAt": "2025-12-24T12:00:00.000Z"
}
```

**Error Response (500):**
```json
{
  "success": false,
  "error": "Error message...",
  "exitCode": 1,
  "executedAt": "2025-12-24T12:00:00.000Z"
}
```

### claude-code-with-git.json

Extended workflow that captures git status before and after Claude Code execution.

**Flow:**
```
Webhook → Git Status Before → Store Status → Execute Claude Code → Git Status After → Compare Status → Check Success → Response
```

**Features:**
- All features from basic workflow
- Git status capture before execution
- Git status capture after execution
- File change detection (new, modified, deleted)
- Retry logic (3 attempts, 30s between retries)

**Webhook Endpoint:** `POST /webhook/claude-code-git`

**Request Body:**
```json
{
  "prompt": "Your prompt for Claude Code"
}
```

**Success Response (200):**
```json
{
  "success": true,
  "output": "Claude Code output...",
  "hasChanges": true,
  "changedFiles": [
    { "status": "M", "file": "src/app.ts" },
    { "status": "??", "file": "src/new-file.ts" }
  ],
  "executedAt": "2025-12-24T12:00:00.000Z"
}
```

**Git Status Codes:**
- `M` - Modified
- `A` - Added (staged)
- `??` - Untracked (new file)
- `D` - Deleted
- `R` - Renamed

---

## GitHub Webhook Integration

### github-webhook.json

Receives and processes GitHub webhook events, routing them to appropriate handlers for automation and notifications.

**Story:** P13-5.2

**Flow:**
```
GitHub Webhook → Validate → Parse Event → Route by Type → Handle Event → Notify/Trigger → Response
                                              ↓
                              ┌───────────────┼───────────────┐───────────────┐
                              ▼               ▼               ▼               ▼
                           Push         Pull Request      Issues         Workflow Run
                              ↓               ↓               ↓               ↓
                        (main only)      (merged?)      (labeled?)      (failed?)
                              ↓               ↓               ↓               ↓
                          Notify          Notify      BMAD Pipeline      Notify
```

**Webhook Endpoint:** `POST /webhook/github-webhook`

**Supported GitHub Events:**
| Event | Actions | Behavior |
|-------|---------|----------|
| `push` | - | Notifies on pushes to main branch |
| `pull_request` | `closed` (merged) | Notifies on PR merges |
| `issues` | `labeled` | Triggers BMAD pipeline if labeled with `automate`, `bmad-pipeline`, or `auto-implement` |
| `workflow_run` | `completed` (failure) | Notifies on CI/CD failures |
| `issue_comment` | - | Logs for monitoring |
| `release` | - | Logs for monitoring |
| `create`/`delete` | - | Logs for monitoring |

**Label-Based Automation:**
When an issue is labeled with one of the following labels, the BMAD pipeline is automatically triggered:
- `automate`
- `bmad-pipeline`
- `auto-implement`

The workflow extracts epic/story IDs from issue titles using patterns like:
- `P13-5.1: Story title...`
- `[P13-5] Epic description...`
- `P13-5: Epic title...`

**Success Response (200):**
```json
{
  "success": true,
  "eventType": "issues",
  "action": "labeled",
  "processed": true
}
```

**Environment Variables:**
| Variable | Description | Required |
|----------|-------------|----------|
| `WEBHOOK_URL` | n8n instance URL for internal webhook calls | Yes |
| `NOTIFICATION_WEBHOOK_URL` | Slack/Discord webhook for notifications | No |
| `GITHUB_TOKEN` | GitHub token for API access | No |

**GitHub Webhook Setup:**
1. Go to your GitHub repository → Settings → Webhooks
2. Click "Add webhook"
3. Payload URL: `https://your-n8n-url/webhook/github-webhook`
4. Content type: `application/json`
5. Select events: `Push`, `Pull requests`, `Issues`, `Workflow runs`
6. Enable the webhook

---

## BMAD Workflow Integration

These workflows execute BMAD (Big Mad Agile Development) methodology workflows for automated story creation, context generation, and implementation.

### bmad-create-story.json

Executes the BMAD create-story workflow to generate a new story file.

**Flow:**
```
Webhook → Execute Create Story → Parse Output → Check Success → Response
```

**Webhook Endpoint:** `POST /webhook/bmad-create-story`

**Success Response (200):**
```json
{
  "success": true,
  "storyPath": "docs/sprint-artifacts/story-name.md",
  "storyTitle": "Story Title",
  "epicId": "P9-5",
  "storyId": "5.5",
  "executedAt": "2025-12-24T12:00:00.000Z"
}
```

### bmad-story-context.json

Generates story context XML from an existing story file.

**Flow:**
```
Webhook → Validate Input → Execute Story Context → Parse Output → Check Success → Response
```

**Webhook Endpoint:** `POST /webhook/bmad-story-context`

**Request Body (optional):**
```json
{
  "storyPath": "docs/sprint-artifacts/story-name.md"
}
```

**Success Response (200):**
```json
{
  "success": true,
  "contextPath": "docs/sprint-artifacts/story-name.context.xml",
  "executedAt": "2025-12-24T12:00:00.000Z"
}
```

### bmad-dev-story.json

Implements a story using the BMAD dev-story workflow with git change tracking.

**Flow:**
```
Webhook → Git Status Before → Store Status → Execute Dev Story → Git Status After → Compare Status → Check Success → Response
```

**Webhook Endpoint:** `POST /webhook/bmad-dev-story`

**Timeout:** 30 minutes (1,800,000ms) for complex implementations

**Success Response (200):**
```json
{
  "success": true,
  "storyStatus": "completed",
  "hasChanges": true,
  "changedFiles": [
    { "status": "M", "file": "src/app.ts" },
    { "status": "??", "file": "src/new-feature.ts" }
  ],
  "tasksCompleted": 5,
  "executedAt": "2025-12-24T12:00:00.000Z"
}
```

### bmad-pipeline.json

Master orchestration workflow that chains all BMAD workflows together.

**Flow:**
```
Webhook → Validate Input → Create Story → Parse → Story Context → Parse → Dev Story → Parse → Success/Failure
                                      ↓                       ↓                    ↓
                                  (on fail) ─────────────────────────────────► Notify → Failure Response
```

**Webhook Endpoint:** `POST /webhook/bmad-pipeline`

**Request Body:**
```json
{
  "epicId": "P9-5",
  "storyId": "5.6",
  "autoImplement": true,
  "notifyOnFailure": true
}
```

**Options:**
- `autoImplement` (default: true): If false, stops after story-context generation
- `notifyOnFailure` (default: true): Sends notification webhook on pipeline failure

**Success Response (200):**
```json
{
  "success": true,
  "stage": "dev-story",
  "storyPath": "docs/sprint-artifacts/p9-5-6-story.md",
  "contextPath": "docs/sprint-artifacts/p9-5-6-story.context.xml",
  "pipelineStartedAt": "2025-12-24T12:00:00.000Z",
  "pipelineCompletedAt": "2025-12-24T12:30:00.000Z"
}
```

### BMAD Environment Variables

Additional environment variables for BMAD workflows:

| Variable | Description | Required |
|----------|-------------|----------|
| `NOTIFICATION_WEBHOOK_URL` | URL for failure notifications (Slack/Discord) | No |

---

## Approval Gates & Monitoring

### bmad-pipeline-with-approval.json

Full BMAD pipeline with human approval gate before PR merge.

**Flow:**
```
Webhook → Create Story → Story Context → Dev Story → Git Push → Create PR → Approval Gate → Merge PR
                                                                      ↓
                                                              (notification sent)
                                                                      ↓
                                                              Wait for approval/reject webhook
```

**Webhook Endpoint:** `POST /webhook/bmad-pipeline-approval`

**Request Body:**
```json
{
  "epicId": "P9-5",
  "storyId": "5.6",
  "autoImplement": true,
  "requireApproval": true,
  "notifyOnFailure": true
}
```

**Options:**
- `requireApproval` (default: true): If false, auto-merges without human approval
- `autoImplement` (default: true): If false, stops after story-context generation
- `notifyOnFailure` (default: true): Sends notification on pipeline failure

**Approval Endpoints:**
- `POST /webhook/approve/{executionId}` - Approves and resumes workflow
- `POST /webhook/reject/{executionId}` - Rejects and cancels workflow

**Approval Request Body (optional):**
```json
{
  "approver": "username",
  "reason": "Looks good to merge"
}
```

**Approval Timeout:** 7 days (604,800 seconds)

### monitoring-dashboard.json

Provides workflow execution metrics and status monitoring.

**Webhook Endpoint:** `GET /webhook/dashboard-metrics`

**Response:**
```json
{
  "timestamp": "2025-12-24T12:00:00.000Z",
  "metrics": {
    "activeWorkflows": 2,
    "queueDepth": 1,
    "totalExecutions": {
      "last24h": 15,
      "last7d": 87,
      "last30d": 342
    },
    "successRate": {
      "last24h": 93,
      "last7d": 89,
      "last30d": 91
    },
    "avgDurationSeconds": {
      "last24h": 245,
      "last7d": 312,
      "last30d": 298
    },
    "statusCounts": {
      "success": 310,
      "error": 25,
      "running": 2,
      "waiting": 1
    }
  },
  "failedWorkflows": [
    {
      "id": "exec-123",
      "workflowName": "BMAD Pipeline",
      "startedAt": "2025-12-24T11:30:00.000Z",
      "error": "Command failed: exit code 1"
    }
  ],
  "waitingWorkflows": [
    {
      "id": "exec-456",
      "workflowName": "BMAD Pipeline with Approval",
      "startedAt": "2025-12-24T10:00:00.000Z"
    }
  ]
}
```

**Note:** Requires n8n API authentication. Configure `httpHeaderAuth` credentials with your n8n API key.

### Approval Gate Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `N8N_URL` | Base URL of n8n instance (for webhook URLs) | Yes |
| `NOTIFICATION_WEBHOOK_URL` | Slack/Discord webhook for notifications | Yes |

---

## Importing Workflows

### Via n8n UI

1. Open your n8n instance
2. Click "Add workflow" or use the menu
3. Select "Import from file"
4. Choose the desired `.json` file from this directory
5. Click "Import"
6. Configure environment variables (see below)
7. Activate the workflow

### Via n8n CLI

```bash
n8n import:workflow --input=n8n/workflows/claude-code-basic.json
n8n import:workflow --input=n8n/workflows/claude-code-with-git.json
```

## Environment Variables

These workflows require the following environment variables to be set in your n8n instance:

| Variable | Description | Required |
|----------|-------------|----------|
| `ANTHROPIC_API_KEY` | API key for Claude Code CLI | Yes |
| `ARGUSAI_PROJECT_PATH` | Path to ArgusAI project root | Yes |

### Setting Environment Variables

**Docker:**
```bash
docker run -e ANTHROPIC_API_KEY=your-key -e ARGUSAI_PROJECT_PATH=/app/argusai ...
```

**systemd Service:**
```ini
[Service]
Environment="ANTHROPIC_API_KEY=your-key"
Environment="ARGUSAI_PROJECT_PATH=/path/to/argusai"
```

**n8n Cloud:**
Use the Settings > Environment Variables section in the n8n UI.

## Prerequisites

1. **n8n Instance**: Running and accessible (see Story P9-5.3)
2. **Claude Code CLI**: Installed globally
   ```bash
   npm install -g @anthropic-ai/claude-code
   ```
3. **ANTHROPIC_API_KEY**: Valid API key from Anthropic
4. **Git**: Available in PATH for git status workflows

## Testing Workflows

### Test Basic Workflow

```bash
curl -X POST http://your-n8n-url/webhook/claude-code \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Create a simple hello.txt file with the text Hello World"}'
```

### Test Git Status Workflow

```bash
curl -X POST http://your-n8n-url/webhook/claude-code-git \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Add a comment to the main.py file explaining its purpose"}'
```

## Timeout Configuration

Both workflows have a 10-minute (600,000ms) timeout configured for the Claude Code execution node. This allows for complex tasks that may take longer to complete.

To modify the timeout:
1. Open the workflow in n8n
2. Select the "Execute Claude Code" node
3. Under "Options", modify the "Timeout" value
4. Save the workflow

## Error Handling

### Retry Logic (claude-code-with-git.json)

The git-enhanced workflow includes automatic retry:
- **Max Retries:** 3 attempts
- **Wait Between Retries:** 30 seconds
- **Continue on Fail:** Enabled (workflow continues to capture errors)

### Error Detection

Errors are detected by:
1. Non-zero exit code from Claude Code CLI
2. Presence of "Error:" in stderr
3. Presence of "error:" in output

## Customization

### Adding Notifications

To add Slack/email notifications on failure:
1. Add a notification node after the "Check Success" node
2. Connect it to the "false" output
3. Configure your notification credentials

### Chaining Workflows

To trigger another workflow after Claude Code:
1. Add an "Execute Workflow" node
2. Connect it after the success response
3. Pass relevant data to the next workflow

## Troubleshooting

### "Command not found: claude"

Ensure Claude Code CLI is installed and in PATH:
```bash
which claude
# Should output: /usr/local/bin/claude or similar
```

### "ANTHROPIC_API_KEY not set"

Verify the environment variable is set:
```bash
echo $ANTHROPIC_API_KEY
```

### "Permission denied"

Ensure the n8n process has write access to the project directory.

### "Timeout exceeded"

Increase the timeout in the Execute Command node options, or simplify the prompt.
