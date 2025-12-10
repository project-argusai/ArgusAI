"""AI Usage model for tracking API calls and costs"""
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime
from app.core.database import Base


class AIUsage(Base):
    """
    Tracks AI API usage for monitoring and cost analysis.

    Each record represents a single AI API call with metadata about:
    - Provider used (openai, claude, gemini, grok)
    - Success/failure status
    - Token consumption and cost estimates
    - Response time for performance monitoring
    - Analysis mode (single_image, multi_frame) for Phase 3 multi-frame analysis
    - Whether token count is estimated vs actual (Story P3-2.5)
    """
    __tablename__ = "ai_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    provider = Column(String(50), nullable=False, index=True)  # openai, claude, gemini, grok
    success = Column(Boolean, nullable=False, index=True)
    tokens_used = Column(Integer, nullable=False, default=0)
    response_time_ms = Column(Integer, nullable=False, default=0)
    cost_estimate = Column(Float, nullable=False, default=0.0)
    error = Column(String(500), nullable=True)  # Error message if failed

    # Phase 3 Multi-Frame Analysis fields (Story P3-2.5)
    analysis_mode = Column(String(20), nullable=True, index=True)  # "single_image", "multi_frame"
    is_estimated = Column(Boolean, nullable=False, default=False)  # True if tokens are estimated

    # Phase 3 Cost Tracking fields (Story P3-7.1)
    image_count = Column(Integer, nullable=True)  # Number of images in multi-image requests

    def __repr__(self):
        return f"<AIUsage(provider='{self.provider}', success={self.success}, tokens={self.tokens_used}, mode={self.analysis_mode})>"
