# n8n Integration for ArgusAI

This directory contains n8n workflow templates and configuration for integrating Claude Code CLI with the ArgusAI automation system.

## Overview

The n8n integration enables automated code generation and modification through Claude Code CLI, triggered by webhooks or scheduled events. This allows for:

- Automated story implementation
- Code review automation
- Documentation generation
- Refactoring tasks
- Bug fixes from issue descriptions

## Directory Structure

```
n8n/
├── README.md                    # This file
├── workflows/
│   ├── README.md               # Workflow documentation
│   ├── claude-code-basic.json  # Basic prompt execution
│   └── claude-code-with-git.json # With git status tracking
└── credentials/
    └── README.md               # Credentials setup guide
```

## Quick Start

### 1. Prerequisites

- n8n instance running (see Story P9-5.3)
- Claude Code CLI installed: `npm install -g @anthropic-ai/claude-code`
- Valid ANTHROPIC_API_KEY

### 2. Set Environment Variables

```bash
export ANTHROPIC_API_KEY=sk-ant-api03-xxxxx
export ARGUSAI_PROJECT_PATH=/path/to/argusai
```

### 3. Import Workflows

1. Open n8n UI
2. Import workflows from `workflows/` directory
3. Activate the workflows

### 4. Test

```bash
curl -X POST http://localhost:5678/webhook/claude-code \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Create a test file"}'
```

## Available Workflows

| Workflow | Endpoint | Description |
|----------|----------|-------------|
| claude-code-basic.json | `/webhook/claude-code` | Simple prompt execution |
| claude-code-with-git.json | `/webhook/claude-code-git` | Execution with git status tracking |
| github-webhook.json | `/webhook/github-webhook` | GitHub event handling and automation triggers |
| bmad-create-story.json | `/webhook/bmad-create-story` | Create story from epic |
| bmad-story-context.json | `/webhook/bmad-story-context` | Generate story context XML |
| bmad-dev-story.json | `/webhook/bmad-dev-story` | Implement story with git tracking |
| bmad-pipeline.json | `/webhook/bmad-pipeline` | Full BMAD pipeline orchestration |
| bmad-pipeline-with-approval.json | `/webhook/bmad-pipeline-approval` | Pipeline with human approval gate |
| monitoring-dashboard.json | `/webhook/dashboard-metrics` | Workflow execution metrics |

See [workflows/README.md](workflows/README.md) for detailed documentation.

## Architecture

```
External Trigger (webhook/schedule)
         │
         ▼
┌─────────────────┐
│   n8n Workflow  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Claude Code    │
│     CLI         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  ArgusAI        │
│  Codebase       │
└─────────────────┘
```

## Integration with BMAD Workflows

These n8n workflows can be used to automate BMAD Method development:

1. **Story Implementation**: Trigger Claude Code with story requirements
2. **Code Review**: Run automated reviews on completed stories
3. **Documentation**: Generate or update documentation

Example integration:
```bash
# Trigger from BMAD workflow
curl -X POST http://n8n:5678/webhook/claude-code-git \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Implement Story P9-5.5 following the acceptance criteria in docs/sprint-artifacts/p9-5-5-story.md"
  }'
```

## Security Considerations

1. **API Keys**: Store securely as environment variables, never in workflow JSON
2. **Network Access**: Restrict webhook access to trusted sources
3. **Project Path**: Ensure n8n has appropriate file system permissions
4. **Audit Logging**: n8n logs all workflow executions

## Troubleshooting

See [workflows/README.md](workflows/README.md#troubleshooting) for common issues and solutions.

## Related Stories

- **P9-5.3**: Deploy n8n instance (prerequisite)
- **P9-5.4**: Create n8n Claude Code integration (this implementation)
- **P9-5.5**: Build prompt generation system
- **P9-5.6**: Implement git commit/PR automation
- **P13-5.1**: Add n8n service to Docker Compose
- **P13-5.2**: Create GitHub Webhook Integration Workflow
- **P13-5.3**: BMAD Workflow Integration (covered by bmad-pipeline.json)
- **P13-5.4**: Notification Workflow (covered by Slack/Discord support)
- **P13-5.5**: Pipeline Dashboard (covered by monitoring-dashboard.json)
