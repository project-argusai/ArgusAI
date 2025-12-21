"""Pydantic schemas for AI service endpoints"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class AIUsageStatsResponse(BaseModel):
    """Response schema for GET /api/v1/ai/usage"""
    total_calls: int = Field(description="Total AI API calls in period")
    successful_calls: int = Field(description="Successful API calls")
    failed_calls: int = Field(description="Failed API calls")
    total_tokens: int = Field(description="Total tokens consumed")
    total_cost: float = Field(description="Total cost in USD")
    avg_response_time_ms: float = Field(description="Average response time in milliseconds")
    provider_breakdown: Dict[str, Dict[str, Any]] = Field(description="Per-provider statistics")

    class Config:
        json_schema_extra = {
            "example": {
                "total_calls": 150,
                "successful_calls": 148,
                "failed_calls": 2,
                "total_tokens": 45000,
                "total_cost": 0.68,
                "avg_response_time_ms": 1250.5,
                "provider_breakdown": {
                    "openai": {
                        "calls": 140,
                        "success_rate": 99.3,
                        "tokens": 42000,
                        "cost": 0.63
                    },
                    "claude": {
                        "calls": 8,
                        "success_rate": 100.0,
                        "tokens": 2400,
                        "cost": 0.04
                    },
                    "gemini": {
                        "calls": 2,
                        "success_rate": 50.0,
                        "tokens": 600,
                        "cost": 0.01
                    }
                }
            }
        }


class AIResultResponse(BaseModel):
    """Response schema for AI description generation (for testing/debugging)"""
    description: str = Field(description="Generated natural language description")
    confidence: int = Field(description="Confidence score 0-100", ge=0, le=100)
    objects_detected: List[str] = Field(description="Detected object types")
    provider: str = Field(description="AI provider used")
    tokens_used: int = Field(description="Total tokens consumed")
    response_time_ms: int = Field(description="Response time in milliseconds")
    cost_estimate: float = Field(description="Estimated cost in USD")
    success: bool = Field(description="Whether generation succeeded")
    error: Optional[str] = Field(None, description="Error message if failed")


class ProviderCapability(BaseModel):
    """Capability information for a single AI provider (Story P3-4.1)"""
    video: bool = Field(description="Whether provider supports native video input")
    max_video_duration: int = Field(description="Maximum video duration in seconds (0 if no video)")
    max_video_size_mb: int = Field(description="Maximum video file size in MB (0 if no video)")
    supported_formats: List[str] = Field(description="Supported video formats (empty if no video)")
    max_images: int = Field(description="Maximum images for multi-frame analysis")
    configured: bool = Field(description="Whether provider has an API key configured")


class AICapabilitiesResponse(BaseModel):
    """Response schema for GET /api/v1/ai/capabilities (Story P3-4.1)"""
    providers: Dict[str, ProviderCapability] = Field(
        description="Capability information for each AI provider"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "providers": {
                    "openai": {
                        "video": True,
                        "max_video_duration": 60,
                        "max_video_size_mb": 20,
                        "supported_formats": ["mp4", "mov", "webm"],
                        "max_images": 10,
                        "configured": True
                    },
                    "grok": {
                        "video": False,
                        "max_video_duration": 0,
                        "max_video_size_mb": 0,
                        "supported_formats": [],
                        "max_images": 10,
                        "configured": True
                    },
                    "claude": {
                        "video": False,
                        "max_video_duration": 0,
                        "max_video_size_mb": 0,
                        "supported_formats": [],
                        "max_images": 20,
                        "configured": False
                    },
                    "gemini": {
                        "video": True,
                        "max_video_duration": 60,
                        "max_video_size_mb": 20,
                        "supported_formats": ["mp4", "mov", "webm"],
                        "max_images": 16,
                        "configured": False
                    }
                }
            }
        }


# Story P8-3.3: AI-Assisted Prompt Refinement Schemas
class PromptRefinementRequest(BaseModel):
    """Request schema for POST /api/v1/ai/refine-prompt (Story P8-3.3)"""
    current_prompt: str = Field(
        description="The current AI description prompt to be refined"
    )
    include_feedback: bool = Field(
        default=True,
        description="Whether to include user feedback data in refinement"
    )
    max_feedback_samples: int = Field(
        default=50,
        ge=1,
        le=100,
        description="Maximum number of feedback samples to analyze"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "current_prompt": "Describe what you see in this image in one concise sentence. Focus on objects, people, and actions.",
                "include_feedback": True,
                "max_feedback_samples": 50
            }
        }


class PromptRefinementResponse(BaseModel):
    """Response schema for POST /api/v1/ai/refine-prompt (Story P8-3.3)"""
    suggested_prompt: str = Field(
        description="AI-suggested improved prompt"
    )
    changes_summary: str = Field(
        description="Summary of what was changed and why"
    )
    feedback_analyzed: int = Field(
        description="Total number of feedback samples analyzed"
    )
    positive_examples: int = Field(
        description="Number of positive (thumbs up) feedback samples"
    )
    negative_examples: int = Field(
        description="Number of negative (thumbs down) feedback samples"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "suggested_prompt": "You are analyzing a home security camera image. Describe:\n1. People present (count, appearance, actions)\n2. Vehicles (type, color, location)\n3. Packages or deliveries\n4. Any unusual or concerning activity\n\nBe specific and concise.",
                "changes_summary": "Added structured format with numbered sections. Incorporated feedback patterns: users prefer specific person counts and vehicle details. Emphasized package detection based on positive feedback.",
                "feedback_analyzed": 47,
                "positive_examples": 32,
                "negative_examples": 15
            }
        }
