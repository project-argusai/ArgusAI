"""AI Usage model for tracking API calls and costs"""
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime
from app.core.database import Base


class AIUsage(Base):
    """
    Tracks AI API usage for monitoring and cost analysis.

    Each record represents a single AI API call with metadata about:
    - Provider used (openai, claude, gemini)
    - Success/failure status
    - Token consumption and cost estimates
    - Response time for performance monitoring
    """
    __tablename__ = "ai_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    provider = Column(String(50), nullable=False, index=True)  # openai, claude, gemini
    success = Column(Boolean, nullable=False, index=True)
    tokens_used = Column(Integer, nullable=False, default=0)
    response_time_ms = Column(Integer, nullable=False, default=0)
    cost_estimate = Column(Float, nullable=False, default=0.0)
    error = Column(String(500), nullable=True)  # Error message if failed

    def __repr__(self):
        return f"<AIUsage(provider='{self.provider}', success={self.success}, tokens={self.tokens_used})>"
