"""
AI Service API endpoints

Provides:
- GET /ai/usage - Usage statistics and cost tracking
- GET /ai/capabilities - Provider capability information (Story P3-4.1)
- POST /ai/refine-prompt - AI-assisted prompt refinement (Story P8-3.3)
- GET /ai/context-metrics - MCP context system metrics (Story P14-6.8)
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Query, Depends, HTTPException
from sqlalchemy.orm import Session
import logging

from app.core.database import get_db
from app.schemas.ai import (
    AIUsageStatsResponse,
    AICapabilitiesResponse,
    PromptRefinementRequest,
    PromptRefinementResponse
)
from app.services.ai_service import ai_service, AIService
from app.services.mcp_context import get_mcp_context_provider
from app.models.event_feedback import EventFeedback
from app.models.event import Event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/usage", response_model=AIUsageStatsResponse)
async def get_ai_usage_stats(
    start_date: Optional[str] = Query(
        None,
        description="Start date filter (ISO 8601 format: YYYY-MM-DD)"
    ),
    end_date: Optional[str] = Query(
        None,
        description="End date filter (ISO 8601 format: YYYY-MM-DD)"
    )
):
    """
    Get AI usage statistics and cost tracking.

    Returns aggregated statistics including:
    - Total API calls (successful and failed)
    - Token usage
    - Cost estimates
    - Average response time
    - Per-provider breakdown

    Supports optional date range filtering.

    Example:
        GET /api/v1/ai/usage
        GET /api/v1/ai/usage?start_date=2025-11-01&end_date=2025-11-16
    """
    # Parse dates if provided
    start_datetime = datetime.fromisoformat(start_date) if start_date else None
    end_datetime = datetime.fromisoformat(end_date) if end_date else None

    # Get stats from AI service
    stats = ai_service.get_usage_stats(start_datetime, end_datetime)

    logger.info(
        f"AI usage stats requested: {stats['total_calls']} calls, "
        f"${stats['total_cost']:.4f} cost"
    )

    return AIUsageStatsResponse(**stats)


@router.get("/capabilities", response_model=AICapabilitiesResponse)
async def get_ai_capabilities():
    """
    Get AI provider capabilities (Story P3-4.1).

    Returns capability information for all AI providers, including:
    - Whether provider supports native video input
    - Maximum video duration and file size limits
    - Supported video formats
    - Maximum images for multi-frame analysis
    - Whether provider has an API key configured

    This endpoint helps determine which analysis modes are available
    based on the current provider configuration.

    Example:
        GET /api/v1/ai/capabilities

    Response:
        {
            "providers": {
                "openai": {"video": true, "max_video_duration": 60, ...},
                "claude": {"video": false, ...},
                ...
            }
        }
    """
    # Get capabilities from AI service
    capabilities = ai_service.get_all_capabilities()

    # Count video-capable providers
    video_providers = [p for p, caps in capabilities.items() if caps.get("video")]
    configured_video_providers = [
        p for p, caps in capabilities.items()
        if caps.get("video") and caps.get("configured")
    ]

    logger.info(
        f"AI capabilities requested: {len(video_providers)} video-capable providers, "
        f"{len(configured_video_providers)} configured",
        extra={
            "video_capable_providers": video_providers,
            "configured_video_providers": configured_video_providers
        }
    )

    return AICapabilitiesResponse(providers=capabilities)


@router.post("/refine-prompt", response_model=PromptRefinementResponse)
async def refine_prompt(
    request: PromptRefinementRequest,
    db: Session = Depends(get_db)
):
    """
    Refine the AI description prompt using feedback data (Story P8-3.3).

    Analyzes user feedback (thumbs up/down, corrections) to suggest an improved
    AI description prompt. Uses the first configured AI provider in the fallback
    chain to generate suggestions.

    AC3.3: Processing indicator handled by frontend
    AC3.4: Returns suggested prompt in response
    AC3.5: Returns changes summary explaining improvements
    AC3.10: Returns 400 error if no feedback data available

    Args:
        request: PromptRefinementRequest with current prompt and options

    Returns:
        PromptRefinementResponse with suggested prompt and analysis stats

    Raises:
        HTTPException 400: No feedback data available for refinement
        HTTPException 503: No AI providers configured
    """
    logger.info(
        "Prompt refinement requested",
        extra={
            "current_prompt_length": len(request.current_prompt),
            "include_feedback": request.include_feedback,
            "max_samples": request.max_feedback_samples
        }
    )

    # Query feedback data from database
    feedback_query = (
        db.query(EventFeedback, Event)
        .join(Event, EventFeedback.event_id == Event.id)
        .order_by(EventFeedback.created_at.desc())
        .limit(request.max_feedback_samples)
    )

    feedback_records = feedback_query.all()

    # AC3.10: Check if we have any feedback data
    if not feedback_records:
        logger.warning("No feedback data available for prompt refinement")
        raise HTTPException(
            status_code=400,
            detail="No feedback data available for refinement. Rate some event descriptions first to enable AI-assisted prompt improvement."
        )

    # Separate positive and negative feedback
    positive_examples = []
    negative_examples = []

    for feedback, event in feedback_records:
        example = {
            "description": event.description or "",
            "rating": feedback.rating,
            "correction": feedback.correction
        }
        if feedback.rating == "helpful":
            positive_examples.append(example)
        else:
            negative_examples.append(example)

    # Build the meta-prompt for AI refinement
    meta_prompt = _build_refinement_meta_prompt(
        current_prompt=request.current_prompt,
        positive_examples=positive_examples,
        negative_examples=negative_examples
    )

    # Initialize AI service and load keys
    refinement_service = AIService()
    await refinement_service.load_api_keys_from_db(db)

    # Get first configured provider
    provider_order = refinement_service._get_provider_order()
    configured_providers = [
        p for p in provider_order
        if refinement_service.providers.get(p) is not None
    ]

    if not configured_providers:
        logger.error("No AI providers configured for prompt refinement")
        raise HTTPException(
            status_code=503,
            detail="No AI providers configured. Please add an API key in Settings."
        )

    # Use first configured provider for text-only refinement
    provider_enum = configured_providers[0]
    provider = refinement_service.providers[provider_enum]

    logger.info(
        f"Using {provider_enum.value} for prompt refinement",
        extra={
            "positive_count": len(positive_examples),
            "negative_count": len(negative_examples)
        }
    )

    # Call the AI provider with text-only request
    try:
        result = await _call_provider_for_refinement(provider, provider_enum, meta_prompt)

        logger.info(
            "Prompt refinement completed successfully",
            extra={
                "provider": provider_enum.value,
                "suggested_prompt_length": len(result["suggested_prompt"]),
                "feedback_analyzed": len(feedback_records)
            }
        )

        # Get friendly provider name for display (Story P9-1.6)
        provider_display_names = {
            "openai": "OpenAI GPT-4o",
            "xai": "xAI Grok 2 Vision",
            "anthropic": "Anthropic Claude 3 Haiku",
            "google": "Google Gemini Flash"
        }
        provider_name = provider_display_names.get(
            provider_enum.value,
            provider_enum.value.title()
        )

        return PromptRefinementResponse(
            suggested_prompt=result["suggested_prompt"],
            changes_summary=result["changes_summary"],
            feedback_analyzed=len(feedback_records),
            positive_examples=len(positive_examples),
            negative_examples=len(negative_examples),
            provider_used=provider_name
        )

    except Exception as e:
        logger.error(f"Prompt refinement failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate prompt refinement: {str(e)}"
        )


def _build_refinement_meta_prompt(
    current_prompt: str,
    positive_examples: list,
    negative_examples: list
) -> str:
    """
    Build the meta-prompt for AI-assisted prompt refinement.

    Args:
        current_prompt: The current AI description prompt
        positive_examples: List of descriptions users liked
        negative_examples: List of descriptions users disliked with corrections

    Returns:
        Meta-prompt string to send to AI provider
    """
    prompt_parts = [
        "You are helping improve a prompt used for home security camera image descriptions.",
        "",
        "CURRENT PROMPT:",
        current_prompt,
        "",
    ]

    # Add positive examples
    if positive_examples:
        prompt_parts.append("POSITIVE FEEDBACK (descriptions users liked):")
        for ex in positive_examples[:10]:  # Limit to 10 examples
            if ex["description"]:
                prompt_parts.append(f'- "{ex["description"][:200]}"')
        prompt_parts.append("")

    # Add negative examples with corrections
    if negative_examples:
        prompt_parts.append("NEGATIVE FEEDBACK (descriptions users disliked):")
        for ex in negative_examples[:10]:  # Limit to 10 examples
            desc = ex["description"][:150] if ex["description"] else "N/A"
            correction = ex["correction"] or "No correction provided"
            prompt_parts.append(f'- Description: "{desc}"')
            prompt_parts.append(f'  User correction: "{correction}"')
        prompt_parts.append("")

    prompt_parts.extend([
        "Based on these feedback patterns, suggest an improved version of the prompt that:",
        "1. Maintains the home security context",
        "2. Addresses issues seen in negative feedback",
        "3. Builds on patterns that worked in positive feedback",
        "4. Keeps the prompt concise but comprehensive",
        "",
        "Respond in this exact format:",
        "SUGGESTED_PROMPT:",
        "[Your improved prompt here]",
        "",
        "CHANGES_SUMMARY:",
        "[Brief explanation of what you changed and why, 2-3 sentences]"
    ])

    return "\n".join(prompt_parts)


async def _call_provider_for_refinement(provider, provider_enum, meta_prompt: str) -> dict:
    """
    Call an AI provider with a text-only refinement request.

    Different providers have different APIs, so we handle each one.

    Args:
        provider: The AI provider instance
        provider_enum: The AIProvider enum value
        meta_prompt: The meta-prompt for refinement

    Returns:
        Dict with suggested_prompt and changes_summary
    """
    import openai
    import anthropic
    import google.generativeai as genai
    from app.services.ai_service import AIProvider

    response_text = ""

    if provider_enum == AIProvider.OPENAI:
        # OpenAI text-only request
        response = await provider.client.chat.completions.create(
            model=provider.model,
            messages=[
                {"role": "system", "content": "You are an expert at writing effective AI prompts for image description tasks."},
                {"role": "user", "content": meta_prompt}
            ],
            max_tokens=1000,
            temperature=0.7
        )
        response_text = response.choices[0].message.content

    elif provider_enum == AIProvider.GROK:
        # Grok uses OpenAI-compatible API
        response = await provider.client.chat.completions.create(
            model="grok-2-vision-1212",
            messages=[
                {"role": "system", "content": "You are an expert at writing effective AI prompts for image description tasks."},
                {"role": "user", "content": meta_prompt}
            ],
            max_tokens=1000,
            temperature=0.7
        )
        response_text = response.choices[0].message.content

    elif provider_enum == AIProvider.CLAUDE:
        # Claude text-only request
        response = await provider.client.messages.create(
            model=provider.model,
            max_tokens=1000,
            messages=[
                {"role": "user", "content": meta_prompt}
            ]
        )
        response_text = response.content[0].text

    elif provider_enum == AIProvider.GEMINI:
        # Gemini text-only request
        import asyncio
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: provider.model.generate_content(meta_prompt)
        )
        response_text = response.text

    else:
        raise ValueError(f"Unsupported provider: {provider_enum}")

    # Parse the response to extract prompt and summary
    return _parse_refinement_response(response_text)


def _parse_refinement_response(response_text: str) -> dict:
    """
    Parse the AI response to extract the suggested prompt and changes summary.

    Args:
        response_text: Raw response from AI provider

    Returns:
        Dict with suggested_prompt and changes_summary
    """
    suggested_prompt = ""
    changes_summary = ""

    # Try to find SUGGESTED_PROMPT: section
    if "SUGGESTED_PROMPT:" in response_text:
        parts = response_text.split("SUGGESTED_PROMPT:", 1)
        if len(parts) > 1:
            remaining = parts[1]
            # Find where CHANGES_SUMMARY starts
            if "CHANGES_SUMMARY:" in remaining:
                prompt_part, summary_part = remaining.split("CHANGES_SUMMARY:", 1)
                suggested_prompt = prompt_part.strip()
                changes_summary = summary_part.strip()
            else:
                suggested_prompt = remaining.strip()
    else:
        # If the format isn't followed, use the whole response as the prompt
        # and generate a generic summary
        suggested_prompt = response_text.strip()
        changes_summary = "AI provided an improved prompt based on your feedback patterns."

    # Clean up any leading/trailing markers or quotes
    suggested_prompt = suggested_prompt.strip('`"\n ')
    changes_summary = changes_summary.strip('`"\n ')

    return {
        "suggested_prompt": suggested_prompt,
        "changes_summary": changes_summary
    }


@router.get("/context-metrics")
async def get_context_metrics():
    """
    Get MCP context system metrics for dashboard (Story P14-6.8).

    Returns metrics about the MCP context provider performance:
    - Cache hit rate
    - Total requests and cache statistics
    - Timeout count
    - Cache TTL and size

    Example:
        GET /api/v1/ai/context-metrics

    Response:
        {
            "cache_hit_rate": 0.75,
            "total_requests": 1000,
            "cache_hits": 750,
            "cache_misses": 250,
            "timeouts": 2,
            "cache_ttl_seconds": 30,
            "timeout_threshold_ms": 80,
            "cache_size": 5
        }
    """
    try:
        provider = get_mcp_context_provider()
        metrics = provider.get_metrics()

        logger.info(
            "MCP context metrics requested",
            extra={
                "cache_hit_rate": metrics.get("cache_hit_rate", 0),
                "total_requests": metrics.get("total_requests", 0),
                "timeouts": metrics.get("timeouts", 0)
            }
        )

        return metrics
    except Exception as e:
        logger.error(f"Failed to get context metrics: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve context metrics: {str(e)}"
        )
