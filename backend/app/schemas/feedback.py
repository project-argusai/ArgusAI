"""Pydantic schemas for event feedback API

Story P4-5.1: Feedback Collection UI
Story P4-5.2: Feedback Storage & API - Added statistics schemas
Story P9-3.3: Package False Positive Feedback - Added correction_type
Story P9-3.4: Add Summary Feedback Buttons - Added summary feedback schemas
"""
from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict, List
from datetime import datetime
from datetime import date as date_type


class FeedbackCreate(BaseModel):
    """Schema for creating new feedback on an event."""
    rating: Literal['helpful', 'not_helpful'] = Field(
        ...,
        description="User's rating of the AI description"
    )
    correction: Optional[str] = Field(
        None,
        max_length=500,
        description="Optional correction text (max 500 characters)"
    )
    # Story P9-3.3: Correction type for specific feedback
    correction_type: Optional[Literal['not_package']] = Field(
        None,
        description="Type of correction (e.g., 'not_package' for package false positives)"
    )


class FeedbackUpdate(BaseModel):
    """Schema for updating existing feedback."""
    rating: Optional[Literal['helpful', 'not_helpful']] = Field(
        None,
        description="Updated rating (optional)"
    )
    correction: Optional[str] = Field(
        None,
        max_length=500,
        description="Updated correction text (max 500 characters)"
    )
    # Story P9-3.3: Correction type for specific feedback
    correction_type: Optional[Literal['not_package']] = Field(
        None,
        description="Type of correction (e.g., 'not_package' for package false positives)"
    )


class FeedbackResponse(BaseModel):
    """Schema for feedback response."""
    id: str
    event_id: str
    camera_id: Optional[str] = None  # Story P4-5.2: Added camera_id
    rating: str
    correction: Optional[str] = None
    correction_type: Optional[str] = None  # Story P9-3.3: Correction type
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ============================================================================
# Story P4-5.2: Feedback Statistics Schemas
# ============================================================================

class CameraFeedbackStats(BaseModel):
    """Per-camera feedback statistics for accuracy tracking."""
    camera_id: str = Field(..., description="Camera UUID")
    camera_name: str = Field(..., description="Human-readable camera name")
    helpful_count: int = Field(..., description="Number of helpful ratings")
    not_helpful_count: int = Field(..., description="Number of not helpful ratings")
    accuracy_rate: float = Field(
        ...,
        ge=0,
        le=100,
        description="Accuracy rate as percentage (helpful / total * 100)"
    )

    model_config = {"from_attributes": True}


class DailyFeedbackStats(BaseModel):
    """Daily feedback counts for trend analysis."""
    date: date_type = Field(..., description="Date (YYYY-MM-DD)")
    helpful_count: int = Field(..., description="Number of helpful ratings on this day")
    not_helpful_count: int = Field(..., description="Number of not helpful ratings on this day")

    model_config = {"from_attributes": True}


class CorrectionSummary(BaseModel):
    """Summary of common correction patterns."""
    correction_text: str = Field(..., description="Correction text provided by users")
    count: int = Field(..., description="Number of times this correction was submitted")

    model_config = {"from_attributes": True}


class FeedbackStatsResponse(BaseModel):
    """
    Aggregate feedback statistics response.

    Provides overall accuracy metrics, per-camera breakdown, daily trends,
    and common correction patterns for AI description quality monitoring.
    """
    total_count: int = Field(..., description="Total number of feedback submissions")
    helpful_count: int = Field(..., description="Total helpful ratings")
    not_helpful_count: int = Field(..., description="Total not helpful ratings")
    accuracy_rate: float = Field(
        ...,
        ge=0,
        le=100,
        description="Overall accuracy rate as percentage (helpful / total * 100)"
    )
    feedback_by_camera: Dict[str, CameraFeedbackStats] = Field(
        default_factory=dict,
        description="Feedback statistics grouped by camera ID"
    )
    daily_trend: List[DailyFeedbackStats] = Field(
        default_factory=list,
        description="Daily feedback counts for trend analysis (last 30 days or specified range)"
    )
    top_corrections: List[CorrectionSummary] = Field(
        default_factory=list,
        description="Most common correction patterns (top 10)"
    )

    model_config = {"from_attributes": True}


# ============================================================================
# Story P9-3.4: Summary Feedback Schemas
# ============================================================================

class SummaryFeedbackCreate(BaseModel):
    """Schema for creating new feedback on a summary."""
    rating: Literal['positive', 'negative'] = Field(
        ...,
        description="User's rating of the summary"
    )
    correction_text: Optional[str] = Field(
        None,
        max_length=500,
        description="Optional correction text (max 500 characters)"
    )


class SummaryFeedbackUpdate(BaseModel):
    """Schema for updating existing summary feedback."""
    rating: Optional[Literal['positive', 'negative']] = Field(
        None,
        description="Updated rating (optional)"
    )
    correction_text: Optional[str] = Field(
        None,
        max_length=500,
        description="Updated correction text (max 500 characters)"
    )


class SummaryFeedbackResponse(BaseModel):
    """Schema for summary feedback response."""
    id: str
    summary_id: str
    rating: str
    correction_text: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
