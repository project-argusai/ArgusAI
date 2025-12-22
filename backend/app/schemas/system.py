"""
System Settings Schemas

Pydantic schemas for system-level configuration and monitoring endpoints.
"""
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, Literal


class RetentionPolicyUpdate(BaseModel):
    """
    Schema for updating retention policy

    Attributes:
        retention_days: Number of days to retain events
            - -1 or 0: Keep forever
            - 7: Keep for 7 days
            - 30: Keep for 30 days
            - 90: Keep for 90 days
            - 365: Keep for 1 year

    Example:
        {
            "retention_days": 30
        }
    """
    retention_days: int = Field(
        ...,
        description="Number of days to retain events (-1 for forever, or 7/30/90/365)"
    )

    @field_validator('retention_days')
    @classmethod
    def validate_retention_days(cls, v):
        """Validate retention_days is one of the allowed values"""
        allowed_values = [-1, 0, 7, 30, 90, 365]
        if v not in allowed_values:
            raise ValueError(
                f"retention_days must be one of {allowed_values}. Got: {v}"
            )
        return v


class RetentionPolicyResponse(BaseModel):
    """
    Schema for retention policy response

    Attributes:
        retention_days: Current retention policy in days
        next_cleanup: When the next scheduled cleanup will run (ISO 8601)
        forever: Whether retention is set to forever (retention_days <= 0)

    Example:
        {
            "retention_days": 30,
            "next_cleanup": "2025-11-18T02:00:00Z",
            "forever": false
        }
    """
    retention_days: int = Field(..., description="Current retention policy in days")
    next_cleanup: Optional[str] = Field(None, description="Next scheduled cleanup time (ISO 8601)")
    forever: bool = Field(..., description="Whether events are kept forever")

    class Config:
        json_schema_extra = {
            "example": {
                "retention_days": 30,
                "next_cleanup": "2025-11-18T02:00:00Z",
                "forever": False
            }
        }


class StorageResponse(BaseModel):
    """
    Schema for storage monitoring response

    Attributes:
        database_mb: Database size in megabytes
        thumbnails_mb: Thumbnails directory size in megabytes
        total_mb: Total storage used in megabytes
        event_count: Number of events in database

    Example:
        {
            "database_mb": 15.2,
            "thumbnails_mb": 8.5,
            "total_mb": 23.7,
            "event_count": 1234
        }
    """
    database_mb: float = Field(..., description="Database size in MB")
    thumbnails_mb: float = Field(..., description="Thumbnails directory size in MB")
    total_mb: float = Field(..., description="Total storage used in MB")
    event_count: int = Field(..., description="Number of events stored")

    class Config:
        json_schema_extra = {
            "example": {
                "database_mb": 15.2,
                "thumbnails_mb": 8.5,
                "total_mb": 23.7,
                "event_count": 1234
            }
        }


class CleanupResponse(BaseModel):
    """
    Schema for manual cleanup response

    Attributes:
        deleted_count: Number of events deleted
        thumbnails_deleted: Number of thumbnail files deleted
        space_freed_mb: Amount of disk space freed in megabytes

    Example:
        {
            "deleted_count": 450,
            "thumbnails_deleted": 380,
            "space_freed_mb": 12.3
        }
    """
    deleted_count: int = Field(..., description="Number of events deleted")
    thumbnails_deleted: int = Field(..., description="Number of thumbnails deleted")
    space_freed_mb: float = Field(..., description="Disk space freed in MB")

    class Config:
        json_schema_extra = {
            "example": {
                "deleted_count": 450,
                "thumbnails_deleted": 380,
                "space_freed_mb": 12.3
            }
        }


class SystemSettings(BaseModel):
    """
    Complete system settings schema

    Combines all configuration categories:
    - General settings (system name, timezone, date/time format)
    - AI model configuration (provider, API keys, prompts)
    - Motion detection parameters
    - Data retention and privacy settings
    """
    # General Settings
    system_name: str = Field(default="ArgusAI", max_length=100)
    timezone: str = Field(default="UTC")
    language: str = Field(default="English")
    date_format: Literal["MM/DD/YYYY", "DD/MM/YYYY", "YYYY-MM-DD"] = Field(default="MM/DD/YYYY")
    time_format: Literal["12h", "24h"] = Field(default="12h")

    # AI Models
    primary_model: Literal["gpt-4o-mini", "claude-3-haiku", "gemini-flash"] = Field(default="gpt-4o-mini")
    primary_api_key: str = Field(default="")  # Encrypted in storage
    fallback_model: Optional[Literal["gpt-4o-mini", "claude-3-haiku", "gemini-flash"]] = Field(default=None)
    description_prompt: str = Field(default="Describe what you see in this image in one concise sentence. Focus on objects, people, and actions.")
    multi_frame_description_prompt: str = Field(
        default="",
        description="Custom prompt appended to multi-frame analysis (Story P3-2.4). Leave empty to use system defaults."
    )

    # Story P9-3.5: Summary Prompt Customization
    summary_prompt: str = Field(
        default="""Generate a daily activity summary for {date}.
Summarize the {event_count} events detected across {camera_count} cameras.
Highlight any notable patterns or unusual activity.
Keep the summary concise (2-3 paragraphs).""",
        description="Custom prompt for generating activity summaries. Variables: {date}, {event_count}, {camera_count}"
    )

    # Motion Detection
    motion_sensitivity: int = Field(default=50, ge=0, le=100)
    detection_method: Literal["background_subtraction", "frame_difference"] = Field(default="background_subtraction")
    cooldown_period: int = Field(default=60, ge=30, le=300)
    min_motion_area: float = Field(default=5, ge=1, le=10)
    save_debug_images: bool = Field(default=False)

    # Data & Privacy
    retention_days: int = Field(default=30)  # -1 for forever
    thumbnail_storage: Literal["filesystem", "database"] = Field(default="filesystem")
    auto_cleanup: bool = Field(default=True)

    # Story P8-2.3: Configurable Frame Count Setting
    analysis_frame_count: Literal[5, 10, 15, 20] = Field(
        default=10, description="Number of frames to extract for AI analysis"
    )

    # Story P8-2.5: Frame Sampling Strategy Selection
    frame_sampling_strategy: Literal["uniform", "adaptive", "hybrid"] = Field(
        default="uniform",
        description="Frame sampling strategy: uniform (fixed interval), adaptive (content-aware), or hybrid (uniform + adaptive filter)"
    )

    # Story P8-3.2: Full Motion Video Storage
    store_motion_videos: bool = Field(
        default=False,
        description="Download and store full motion videos from Protect cameras"
    )
    video_retention_days: int = Field(
        default=30,
        ge=1,
        le=365,
        description="Number of days to retain stored videos (separate from event retention)"
    )

    # Story P9-3.2: OCR Frame Overlay Extraction
    attempt_ocr_extraction: bool = Field(
        default=False,
        description="Attempt to extract timestamp/camera name from video frame overlays using OCR (CPU intensive, requires tesseract)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "system_name": "ArgusAI",
                "timezone": "America/Los_Angeles",
                "language": "English",
                "date_format": "MM/DD/YYYY",
                "time_format": "12h",
                "primary_model": "gpt-4o-mini",
                "primary_api_key": "sk-...",
                "fallback_model": None,
                "description_prompt": "Describe what you see in this image in one concise sentence.",
                "multi_frame_description_prompt": "",
                "motion_sensitivity": 50,
                "detection_method": "background_subtraction",
                "cooldown_period": 60,
                "min_motion_area": 5,
                "save_debug_images": False,
                "retention_days": 30,
                "thumbnail_storage": "filesystem",
                "auto_cleanup": True
            }
        }


class SystemSettingsUpdate(BaseModel):
    """
    Partial update schema for system settings
    All fields are optional to support partial updates
    """
    # General Settings
    system_name: Optional[str] = Field(None, max_length=100)
    timezone: Optional[str] = None
    language: Optional[str] = None
    date_format: Optional[Literal["MM/DD/YYYY", "DD/MM/YYYY", "YYYY-MM-DD"]] = None
    time_format: Optional[Literal["12h", "24h"]] = None

    # AI Models (legacy)
    primary_model: Optional[Literal["gpt-4o-mini", "claude-3-haiku", "gemini-flash"]] = None
    primary_api_key: Optional[str] = None
    fallback_model: Optional[Literal["gpt-4o-mini", "claude-3-haiku", "gemini-flash"]] = None
    description_prompt: Optional[str] = None
    multi_frame_description_prompt: Optional[str] = Field(
        None,
        description="Custom prompt appended to multi-frame analysis (Story P3-2.4). Leave empty to use system defaults."
    )

    # Story P9-3.5: Summary Prompt Customization
    summary_prompt: Optional[str] = Field(
        None,
        max_length=2000,
        description="Custom prompt for generating activity summaries. Variables: {date}, {event_count}, {camera_count}"
    )

    # AI Provider API Keys (Story P2-5.2, P2-5.3)
    ai_api_key_openai: Optional[str] = None
    ai_api_key_grok: Optional[str] = None
    ai_api_key_claude: Optional[str] = None
    ai_api_key_gemini: Optional[str] = None
    ai_provider_order: Optional[str] = None  # JSON array of provider order

    # Motion Detection
    motion_sensitivity: Optional[int] = Field(None, ge=0, le=100)
    detection_method: Optional[Literal["background_subtraction", "frame_difference"]] = None
    cooldown_period: Optional[int] = Field(None, ge=30, le=300)
    min_motion_area: Optional[float] = Field(None, ge=1, le=10)
    save_debug_images: Optional[bool] = None

    # Data & Privacy
    retention_days: Optional[int] = None
    thumbnail_storage: Optional[Literal["filesystem", "database"]] = None
    auto_cleanup: Optional[bool] = None

    # Story P3-7.3: Cost Cap Settings
    ai_daily_cost_cap: Optional[float] = Field(None, ge=0, description="Daily cost cap in USD (null = no limit)")
    ai_monthly_cost_cap: Optional[float] = Field(None, ge=0, description="Monthly cost cap in USD (null = no limit)")

    # Story P3-7.5: Key Frames Storage Setting
    store_analysis_frames: Optional[bool] = Field(None, description="Store key frames used for AI analysis (default: true)")

    # Story P4-3.4: Context-Enhanced AI Prompts Settings
    enable_context_enhanced_prompts: Optional[bool] = Field(
        None, description="Enable historical context in AI prompts (default: true)"
    )
    context_ab_test_percentage: Optional[int] = Field(
        None, ge=0, le=100, description="Percentage of events to skip context for A/B testing (0 = disabled)"
    )
    context_similarity_threshold: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Minimum similarity threshold for context inclusion (default: 0.7)"
    )
    context_time_window_days: Optional[int] = Field(
        None, ge=1, le=365, description="Days of history to use for context (default: 30)"
    )

    # Story P4-7.3: Anomaly Detection Settings
    anomaly_low_threshold: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Threshold for low/medium anomaly classification (default: 0.3)"
    )
    anomaly_high_threshold: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Threshold for medium/high anomaly classification (default: 0.6)"
    )
    anomaly_enabled: Optional[bool] = Field(
        None, description="Enable anomaly scoring for events (default: true)"
    )

    # Story P4-8.1: Face Recognition Privacy Settings
    face_recognition_enabled: Optional[bool] = Field(
        None, description="Enable face detection and embedding storage (default: false, opt-in)"
    )

    # Story P4-8.2: Person Matching Settings
    person_match_threshold: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Similarity threshold for face-to-person matching (default: 0.70)"
    )
    auto_create_persons: Optional[bool] = Field(
        None, description="Automatically create new person when no match found (default: true)"
    )
    update_appearance_on_high_match: Optional[bool] = Field(
        None, description="Update reference embedding on high-confidence matches (default: true)"
    )

    # Story P4-8.3: Vehicle Recognition Settings
    vehicle_recognition_enabled: Optional[bool] = Field(
        None, description="Enable vehicle detection and embedding storage (default: false, opt-in)"
    )
    vehicle_match_threshold: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Similarity threshold for vehicle matching (default: 0.65)"
    )
    auto_create_vehicles: Optional[bool] = Field(
        None, description="Automatically create new vehicle when no match found (default: true)"
    )

    # Story P8-2.3: Configurable Frame Count Setting
    analysis_frame_count: Optional[Literal[5, 10, 15, 20]] = Field(
        None, description="Number of frames to extract for AI analysis (default: 10)"
    )

    # Story P8-2.5: Frame Sampling Strategy Selection
    frame_sampling_strategy: Optional[Literal["uniform", "adaptive", "hybrid"]] = Field(
        None, description="Frame sampling strategy: uniform (default), adaptive, or hybrid"
    )

    # Story P8-3.2: Full Motion Video Storage
    store_motion_videos: Optional[bool] = Field(
        None, description="Download and store full motion videos from Protect cameras (default: false)"
    )
    video_retention_days: Optional[int] = Field(
        None, ge=1, le=365, description="Number of days to retain stored videos (default: 30)"
    )

    # Story P9-3.2: OCR Frame Overlay Extraction
    attempt_ocr_extraction: Optional[bool] = Field(
        None, description="Attempt to extract timestamp/camera name from video frame overlays using OCR (default: false)"
    )


# Story P3-7.1: AI Usage Response Schemas for Cost Tracking

class AIUsageByDate(BaseModel):
    """Daily usage aggregation."""
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    cost: float = Field(..., description="Total cost for the date in USD")
    requests: int = Field(..., description="Number of AI requests")


class AIUsageByCamera(BaseModel):
    """Per-camera usage aggregation."""
    camera_id: str = Field(..., description="Camera identifier")
    camera_name: str = Field(..., description="Camera display name")
    cost: float = Field(..., description="Total cost for the camera in USD")
    requests: int = Field(..., description="Number of AI requests")


class AIUsageByProvider(BaseModel):
    """Per-provider usage aggregation."""
    provider: str = Field(..., description="AI provider name (openai, grok, claude, gemini)")
    cost: float = Field(..., description="Total cost for the provider in USD")
    requests: int = Field(..., description="Number of AI requests")


class AIUsageByMode(BaseModel):
    """Per-analysis-mode usage aggregation."""
    mode: str = Field(..., description="Analysis mode (single_image, multi_frame, video_native)")
    cost: float = Field(..., description="Total cost for the mode in USD")
    requests: int = Field(..., description="Number of AI requests")


class AIUsagePeriod(BaseModel):
    """Period for usage aggregation."""
    start: str = Field(..., description="Start date in ISO 8601 format")
    end: str = Field(..., description="End date in ISO 8601 format")


class AIUsageResponse(BaseModel):
    """
    Response schema for AI usage aggregation endpoint.

    Provides comprehensive cost and usage breakdown by various dimensions.
    Story P3-7.1: Implement Cost Tracking Service.

    Attributes:
        total_cost: Total cost across all requests in USD
        total_requests: Total number of AI requests
        period: Date range for the aggregation
        by_date: Daily usage breakdown
        by_camera: Per-camera usage breakdown
        by_provider: Per-provider usage breakdown
        by_mode: Per-analysis-mode usage breakdown
    """
    total_cost: float = Field(..., description="Total cost in USD")
    total_requests: int = Field(..., description="Total number of AI requests")
    period: AIUsagePeriod = Field(..., description="Date range for aggregation")
    by_date: list[AIUsageByDate] = Field(default_factory=list, description="Usage by date")
    by_camera: list[AIUsageByCamera] = Field(default_factory=list, description="Usage by camera")
    by_provider: list[AIUsageByProvider] = Field(default_factory=list, description="Usage by provider")
    by_mode: list[AIUsageByMode] = Field(default_factory=list, description="Usage by analysis mode")

    class Config:
        json_schema_extra = {
            "example": {
                "total_cost": 0.0523,
                "total_requests": 142,
                "period": {
                    "start": "2025-11-09T00:00:00Z",
                    "end": "2025-12-09T23:59:59Z"
                },
                "by_date": [
                    {"date": "2025-12-09", "cost": 0.0123, "requests": 45},
                    {"date": "2025-12-08", "cost": 0.0098, "requests": 32}
                ],
                "by_camera": [
                    {"camera_id": "1", "camera_name": "Front Door", "cost": 0.0234, "requests": 67}
                ],
                "by_provider": [
                    {"provider": "openai", "cost": 0.0456, "requests": 120},
                    {"provider": "claude", "cost": 0.0067, "requests": 22}
                ],
                "by_mode": [
                    {"mode": "single_image", "cost": 0.0234, "requests": 89},
                    {"mode": "multi_frame", "cost": 0.0289, "requests": 53}
                ]
            }
        }


# Story P3-7.3: Cost Cap Status Schema

class CostCapStatus(BaseModel):
    """
    Response schema for cost cap status endpoint.

    Story P3-7.3: Implement Daily/Monthly Cost Caps.

    Provides current cost usage and cap status for enforcement and UI display.
    """
    daily_cost: float = Field(..., description="Current day's total cost in USD")
    daily_cap: Optional[float] = Field(None, description="Daily cap in USD (null = no limit)")
    daily_percent: float = Field(..., description="Percentage of daily cap used (0 if no cap)")
    monthly_cost: float = Field(..., description="Current month's total cost in USD")
    monthly_cap: Optional[float] = Field(None, description="Monthly cap in USD (null = no limit)")
    monthly_percent: float = Field(..., description="Percentage of monthly cap used (0 if no cap)")
    is_paused: bool = Field(..., description="True if AI analysis is paused due to cap")
    pause_reason: Optional[Literal["cost_cap_daily", "cost_cap_monthly"]] = Field(
        None, description="Reason for pause (null if not paused)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "daily_cost": 0.75,
                "daily_cap": 1.00,
                "daily_percent": 75.0,
                "monthly_cost": 12.50,
                "monthly_cap": 20.00,
                "monthly_percent": 62.5,
                "is_paused": False,
                "pause_reason": None
            }
        }
