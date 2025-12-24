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
