"""Event SQLAlchemy ORM model for AI-generated semantic events"""
from sqlalchemy import Column, String, Integer, Text, DateTime, Boolean, ForeignKey, CheckConstraint, Index, Float
from sqlalchemy.orm import relationship
from app.core.database import Base
import uuid
from datetime import datetime, timezone


class Event(Base):
    """
    AI-generated semantic event model.

    Represents motion events enriched with AI vision analysis, including
    natural language descriptions and detected objects.

    Attributes:
        id: UUID primary key
        camera_id: Foreign key to cameras table
        timestamp: When event occurred (UTC with timezone, indexed)
        description: AI-generated natural language description (FTS5 indexed)
        confidence: AI confidence score (0-100, CHECK constraint)
        objects_detected: JSON array of detected objects ["person", "vehicle", etc.]
        thumbnail_path: Optional file path to thumbnail (filesystem mode)
        thumbnail_base64: Optional base64-encoded thumbnail (database mode)
        alert_triggered: Whether alert rules were triggered (Epic 5)
        source_type: Event source - 'rtsp', 'usb', or 'protect' (Phase 2)
        protect_event_id: UniFi Protect's native event ID (Phase 2)
        smart_detection_type: Protect smart detection type - person/vehicle/package/animal/motion (Phase 2)
        correlation_group_id: UUID linking correlated multi-camera events (Story P2-4.3)
        correlated_event_ids: JSON array of related event UUIDs (Story P2-4.3)
        provider_used: AI provider that generated the description - openai/grok/claude/gemini (Story P2-5.3)
        fallback_reason: Reason for fallback to snapshot analysis (Story P3-1.4) - e.g., "clip_download_failed"
        analysis_mode: Analysis mode used - "single_frame", "multi_frame", "video_native" (Story P3-2.6)
        frame_count_used: Number of frames sent to AI for multi-frame analysis (Story P3-2.6)
        audio_transcription: Transcribed speech from doorbell audio (Story P3-5.3)
        ai_confidence: AI self-reported confidence score (0-100) (Story P3-6.1)
        low_confidence: True if ai_confidence < 50 OR vague description, flagging uncertain descriptions (Story P3-6.1, P3-6.2)
        vague_reason: Human-readable explanation of why description was flagged as vague (Story P3-6.2)
        reanalyzed_at: Timestamp of last re-analysis (Story P3-6.4)
        reanalysis_count: Number of re-analyses performed for rate limiting (Story P3-6.4)
        ai_cost: Estimated cost in USD for AI analysis (Story P3-7.1)
        analysis_skipped_reason: Reason AI analysis was skipped - "cost_cap_daily"/"cost_cap_monthly" (Story P3-7.3)
        key_frames_base64: JSON array of base64-encoded frame thumbnails for gallery display (Story P3-7.5)
        frame_timestamps: JSON array of float seconds from video start for each frame (Story P3-7.5)
        audio_event_type: Detected audio event type - glass_break/gunshot/scream/doorbell/other (Story P6-3.2)
        audio_confidence: Confidence score (0.0-1.0) for audio event detection (Story P6-3.2)
        audio_duration_ms: Duration of detected audio event in milliseconds (Story P6-3.2)
        delivery_carrier: Detected delivery carrier - fedex/ups/usps/amazon/dhl (Story P7-2.1)
        video_path: Path to stored full motion video file (Story P8-3.2)
        created_at: Record creation timestamp (UTC with timezone)
    """

    __tablename__ = "events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    camera_id = Column(String, ForeignKey('cameras.id', ondelete='CASCADE'), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    description = Column(Text, nullable=False)  # AI-generated description
    confidence = Column(Integer, nullable=False)  # 0-100
    objects_detected = Column(Text, nullable=False)  # JSON array: ["person", "vehicle", "animal", "package", "unknown"]
    thumbnail_path = Column(String(500), nullable=True)  # Filesystem mode: relative path
    thumbnail_base64 = Column(Text, nullable=True)  # Database mode: base64 JPEG
    alert_triggered = Column(Boolean, nullable=False, default=False)  # Epic 5 feature
    alert_rule_ids = Column(Text, nullable=True)  # JSON array of triggered rule UUIDs (Epic 5)
    # Phase 2: UniFi Protect event source fields
    source_type = Column(String(20), nullable=False, default='rtsp')  # 'rtsp', 'usb', 'protect'
    protect_event_id = Column(String(100), nullable=True)  # Protect's native event ID (null for RTSP/USB)
    smart_detection_type = Column(String(20), nullable=True)  # person/vehicle/package/animal/motion/ring (null for RTSP/USB)
    is_doorbell_ring = Column(Boolean, nullable=False, default=False)  # True if event triggered by doorbell ring (Story P2-4.1)
    # Story P2-4.3: Multi-camera event correlation
    correlation_group_id = Column(String, nullable=True, index=True)  # UUID linking correlated events
    correlated_event_ids = Column(Text, nullable=True)  # JSON array: ["uuid1", "uuid2", ...]
    # Story P2-5.3: AI provider tracking
    provider_used = Column(String(20), nullable=True)  # openai/grok/claude/gemini (null for legacy events)
    # Story P2-6.3: Flag for events that need AI description retry
    description_retry_needed = Column(Boolean, nullable=False, default=False)  # True if all AI providers failed (AC13)
    # Story P3-1.4: Fallback reason tracking for video clip failures
    fallback_reason = Column(String(100), nullable=True)  # e.g., "clip_download_failed" (null = no fallback)
    # Story P3-2.6: Multi-frame analysis tracking
    analysis_mode = Column(String(20), nullable=True, index=True)  # "single_frame", "multi_frame", "video_native"
    frame_count_used = Column(Integer, nullable=True)  # Number of frames sent to AI (null for single-frame)
    # Story P3-5.3: Audio transcription for doorbell cameras
    audio_transcription = Column(Text, nullable=True)  # Transcribed speech from doorbell audio
    # Story P3-6.1: AI confidence scoring
    ai_confidence = Column(Integer, nullable=True)  # 0-100 AI self-reported confidence (null = not available)
    low_confidence = Column(Boolean, nullable=False, default=False)  # True if ai_confidence < 50 OR vague description
    # Story P3-6.2: Vagueness detection
    vague_reason = Column(Text, nullable=True)  # Human-readable reason if description flagged as vague (null = not vague)
    # Story P3-6.4: Re-analysis tracking
    reanalyzed_at = Column(DateTime(timezone=True), nullable=True)  # Timestamp of last re-analysis (null = never re-analyzed)
    reanalysis_count = Column(Integer, nullable=False, default=0)  # Number of re-analyses performed (for rate limiting)
    # Story P3-7.1: AI cost tracking
    ai_cost = Column(Float, nullable=True)  # Estimated cost in USD for AI analysis (null = not tracked)
    # Story P3-7.3: Cost cap enforcement - analysis skip reason
    analysis_skipped_reason = Column(String(50), nullable=True)  # "cost_cap_daily", "cost_cap_monthly" (null = not skipped)
    # Story P3-7.5: Key frames storage for event detail gallery
    key_frames_base64 = Column(Text, nullable=True)  # JSON array of base64-encoded frame thumbnails (null = not stored)
    frame_timestamps = Column(Text, nullable=True)  # JSON array of float seconds from video start (null = not stored)
    # Story P4-5.4: A/B testing - tracks which prompt variant was used
    prompt_variant = Column(String(20), nullable=True, index=True)  # 'control', 'experiment' (null = no A/B test active)
    # Story P4-7.2: Anomaly scoring
    anomaly_score = Column(Float, nullable=True)  # 0.0 (normal) to 1.0 (highly anomalous), null = not scored
    # Story P4-8.4: Named Entity Alerts - recognition status and enriched descriptions
    recognition_status = Column(String(20), nullable=True)  # 'known', 'stranger', 'unknown', null (no recognition)
    enriched_description = Column(Text, nullable=True)  # AI description with entity names included
    matched_entity_ids = Column(Text, nullable=True)  # JSON array of matched entity UUIDs
    # Story P6-3.2: Audio event detection fields
    audio_event_type = Column(String(30), nullable=True)  # 'glass_break', 'gunshot', 'scream', 'doorbell', 'other' (null = no audio event)
    audio_confidence = Column(Float, nullable=True)  # 0.0-1.0 confidence score for audio detection (null = not detected)
    audio_duration_ms = Column(Integer, nullable=True)  # Duration of audio event in milliseconds (null = not detected)
    # Story P7-2.1: Delivery carrier detection
    delivery_carrier = Column(String(32), nullable=True)  # 'fedex', 'ups', 'usps', 'amazon', 'dhl' (null = not detected)
    # Story P8-3.2: Full motion video storage
    video_path = Column(String(500), nullable=True)  # Path to stored video file (null = no video stored)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    camera = relationship("Camera", back_populates="events")
    embedding = relationship("EventEmbedding", back_populates="event", uselist=False, cascade="all, delete-orphan")
    feedback = relationship("EventFeedback", back_populates="event", uselist=False, cascade="all, delete-orphan")
    # Story P4-8.1: Face embeddings (one event can have multiple faces)
    face_embeddings = relationship("FaceEmbedding", back_populates="event", cascade="all, delete-orphan")
    # Story P4-8.3: Vehicle embeddings (one event can have multiple vehicles)
    vehicle_embeddings = relationship("VehicleEmbedding", back_populates="event", cascade="all, delete-orphan")
    # Story P8-2.1: Analysis frames (frames extracted for AI multi-frame analysis)
    frames = relationship("EventFrame", back_populates="event", cascade="all, delete-orphan")
    # Story P11-4.2: Per-frame embeddings for query-adaptive frame selection
    frame_embeddings = relationship("FrameEmbedding", back_populates="event", cascade="all, delete-orphan")
    # Story P14-2.2: Relationship to webhook logs for CASCADE delete
    webhook_logs = relationship("WebhookLog", back_populates="event", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint('confidence >= 0 AND confidence <= 100', name='check_confidence_range'),
        Index('idx_events_timestamp_desc', 'timestamp', postgresql_ops={'timestamp': 'DESC'}),
        Index('idx_events_camera_timestamp', 'camera_id', 'timestamp'),
    )

    def __repr__(self):
        return f"<Event(id={self.id}, camera_id={self.camera_id}, timestamp={self.timestamp}, confidence={self.confidence})>"
