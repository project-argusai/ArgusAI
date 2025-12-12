"""Pydantic schemas for prompt insights API - Story P4-5.4

Defines request/response models for:
- Prompt improvement suggestions
- Camera-specific insights
- A/B test results
- Prompt history tracking
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime
from enum import Enum


class CorrectionCategory(str, Enum):
    """Categories for classifying user corrections."""
    OBJECT_MISID = "object_misidentification"
    ACTION_WRONG = "action_wrong"
    MISSING_DETAIL = "missing_detail"
    CONTEXT_ERROR = "context_error"
    GENERAL = "general"


class PromptSuggestion(BaseModel):
    """A suggested improvement to the AI description prompt."""
    id: str = Field(..., description="Unique suggestion identifier")
    category: CorrectionCategory = Field(..., description="Category of correction pattern")
    suggestion_text: str = Field(..., description="Suggested prompt improvement text")
    example_corrections: List[str] = Field(
        default_factory=list,
        description="Example user corrections that led to this suggestion"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in the suggestion (0.0 to 1.0)"
    )
    impact_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Expected impact score based on frequency (0.0 to 1.0)"
    )
    camera_id: Optional[str] = Field(
        None,
        description="Camera ID if this is a camera-specific suggestion"
    )

    model_config = {"from_attributes": True}


class CameraInsight(BaseModel):
    """Per-camera analysis results."""
    camera_id: str = Field(..., description="Camera UUID")
    camera_name: str = Field(..., description="Human-readable camera name")
    accuracy_rate: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Accuracy rate as percentage"
    )
    sample_count: int = Field(..., description="Number of feedback samples")
    top_categories: List[CorrectionCategory] = Field(
        default_factory=list,
        description="Most common correction categories for this camera"
    )
    suggestions: List[PromptSuggestion] = Field(
        default_factory=list,
        description="Camera-specific suggestions (if accuracy is low)"
    )

    model_config = {"from_attributes": True}


class PromptInsightsResponse(BaseModel):
    """Response for GET /api/v1/feedback/prompt-insights."""
    suggestions: List[PromptSuggestion] = Field(
        default_factory=list,
        description="Global prompt improvement suggestions"
    )
    camera_insights: Dict[str, CameraInsight] = Field(
        default_factory=dict,
        description="Per-camera analysis insights keyed by camera ID"
    )
    sample_count: int = Field(
        ...,
        description="Total number of feedback corrections analyzed"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Overall confidence in the analysis"
    )
    min_samples_met: bool = Field(
        ...,
        description="Whether minimum sample threshold (10) was met"
    )

    model_config = {"from_attributes": True}


class ApplySuggestionRequest(BaseModel):
    """Request body for POST /api/v1/feedback/prompt-insights/apply."""
    suggestion_id: str = Field(..., description="ID of suggestion to apply")
    camera_id: Optional[str] = Field(
        None,
        description="Camera ID for camera-specific prompt (optional)"
    )


class ApplySuggestionResponse(BaseModel):
    """Response for POST /api/v1/feedback/prompt-insights/apply."""
    success: bool = Field(..., description="Whether the suggestion was applied")
    new_prompt: str = Field(..., description="The updated prompt text")
    prompt_version: int = Field(..., description="Version number of the new prompt")
    message: str = Field(..., description="Status message")

    model_config = {"from_attributes": True}


class ABTestAccuracyStats(BaseModel):
    """Accuracy statistics for an A/B test variant."""
    variant: str = Field(..., description="Variant name: 'control' or 'experiment'")
    event_count: int = Field(..., description="Number of events in this variant")
    helpful_count: int = Field(..., description="Number of helpful ratings")
    not_helpful_count: int = Field(..., description="Number of not helpful ratings")
    accuracy_rate: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Accuracy rate as percentage"
    )

    model_config = {"from_attributes": True}


class ABTestResultsResponse(BaseModel):
    """Response for GET /api/v1/feedback/ab-test/results."""
    control: ABTestAccuracyStats = Field(..., description="Control group statistics")
    experiment: ABTestAccuracyStats = Field(..., description="Experiment group statistics")
    winner: Optional[str] = Field(
        None,
        description="Winner variant ('control', 'experiment', or None if inconclusive)"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Statistical confidence in the winner determination"
    )
    is_significant: bool = Field(
        ...,
        description="Whether the difference is statistically significant"
    )
    message: str = Field(..., description="Summary message about A/B test results")

    model_config = {"from_attributes": True}


class PromptHistoryEntry(BaseModel):
    """A record of prompt evolution."""
    id: str = Field(..., description="History entry UUID")
    prompt_version: int = Field(..., description="Version number")
    prompt_text: str = Field(..., description="Full prompt text")
    source: str = Field(..., description="Source: 'manual', 'suggestion', 'ab_test'")
    applied_suggestions: Optional[List[str]] = Field(
        None,
        description="List of suggestion IDs that were applied"
    )
    accuracy_before: Optional[float] = Field(
        None,
        description="Accuracy rate before this prompt was applied"
    )
    accuracy_after: Optional[float] = Field(
        None,
        description="Accuracy rate after this prompt was applied"
    )
    camera_id: Optional[str] = Field(
        None,
        description="Camera ID if this is a camera-specific prompt"
    )
    created_at: datetime = Field(..., description="When this version was created")

    model_config = {"from_attributes": True}


class PromptHistoryResponse(BaseModel):
    """Response for GET /api/v1/feedback/prompt-history."""
    entries: List[PromptHistoryEntry] = Field(
        default_factory=list,
        description="Prompt history entries, newest first"
    )
    current_version: int = Field(..., description="Current active prompt version")
    total_count: int = Field(..., description="Total number of prompt versions")

    model_config = {"from_attributes": True}
