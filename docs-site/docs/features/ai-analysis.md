---
sidebar_position: 2
---

# AI Analysis

ArgusAI uses advanced AI to analyze video events and generate natural language descriptions.

## Multi-Provider Support

Choose from multiple AI providers with automatic fallback:

| Provider | Model | Best For |
|----------|-------|----------|
| OpenAI | GPT-4o mini | General accuracy, low cost |
| xAI Grok | Grok 2 Vision | Fast responses |
| Anthropic | Claude 3 Haiku | Detailed analysis |
| Google | Gemini Flash | Speed, multi-language |

## Analysis Modes

### Single Frame
Traditional snapshot-based analysis. Fastest and lowest cost.

### Multi-Frame
Extract 3-5 key frames from video clips for better context. Balanced approach.

### Video Native
Send full video clips to providers that support it (OpenAI, Gemini). Highest accuracy.

## Frame Extraction

ArgusAI uses intelligent frame selection:

### Similarity Filtering
Removes nearly identical frames to focus on unique moments.

### Motion Scoring
Prioritizes frames with high activity using optical flow analysis.

### Adaptive Sampling
Combines similarity and motion scoring for optimal frame selection.

## Context Enhancement

AI prompts include contextual information:

- **Camera Name**: Location context (e.g., "Front Door", "Driveway")
- **Time of Day**: Temporal context (morning, afternoon, evening)
- **Date**: Seasonal and schedule context

Example enhanced prompt:
```
This footage is from the Front Door camera at 7:15 AM on December 23, 2025.
Describe what you see in these security camera frames.
```

## Confidence Scoring

Each AI description includes a confidence score (0-100):

- **90-100**: High confidence, clear detection
- **70-89**: Good confidence, likely accurate
- **50-69**: Moderate confidence, may need verification
- **Below 50**: Low confidence, consider re-analysis

## Custom Prompts

Customize the AI prompt in **Settings > AI Models**:

1. Edit the **Analysis Prompt** text area
2. Use the **Refine Prompt** button for AI-assisted improvements
3. Save changes

### Prompt Variables

Available placeholders:
- `{camera_name}` - Camera friendly name
- `{timestamp}` - Event time
- `{date}` - Event date

## Re-Analysis

To re-analyze an event with updated settings:

1. Open the event detail view
2. Click **Re-analyse**
3. Wait for new description
4. Compare with previous description

## Cost Tracking

Monitor AI usage in **Settings > AI Costs**:

- Per-provider token usage
- Daily/monthly cost estimates
- Cost cap configuration
