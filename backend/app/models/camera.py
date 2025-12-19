"""Camera SQLAlchemy ORM model"""
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, CheckConstraint, ForeignKey, Float
from sqlalchemy.orm import validates, relationship
from app.core.database import Base
from app.utils.encryption import encrypt_password, decrypt_password
import uuid
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class Camera(Base):
    """
    Camera model representing RTSP, USB, or UniFi Protect camera configuration

    Attributes:
        id: UUID primary key
        name: User-friendly camera name (e.g., "Front Door")
        type: Camera type - 'rtsp' or 'usb'
        rtsp_url: Full RTSP URL (e.g., rtsp://192.168.1.50:554/stream1)
        username: RTSP authentication username (nullable)
        password: Encrypted password (Fernet AES-256, nullable)
        device_index: USB camera device index (0, 1, 2..., nullable for RTSP)
        frame_rate: Target frames per second (1-30)
        is_enabled: Whether camera capture is active
        motion_enabled: Whether motion detection is active (default True)
        motion_sensitivity: Motion detection sensitivity ('low', 'medium', 'high')
        motion_cooldown: Seconds between motion triggers (0-300)
        motion_algorithm: Motion detection algorithm ('mog2', 'knn', 'frame_diff')
        detection_zones: JSON array of detection zone objects (nullable)
        detection_schedule: JSON object for detection schedule (nullable)
        source_type: Camera source - 'rtsp', 'usb', or 'protect' (Phase 2)
        protect_controller_id: Foreign key to protect_controllers (Phase 2)
        protect_camera_id: Native Protect camera ID (Phase 2)
        protect_camera_type: Protect camera type - 'camera' or 'doorbell' (Phase 2)
        smart_detection_types: JSON array of smart detection types (Phase 2)
        is_doorbell: Whether camera is a doorbell (Phase 2)
        analysis_mode: AI analysis mode - 'single_frame', 'multi_frame', or 'video_native' (Phase 3)
            - single_frame: Fast, low cost - uses single snapshot
            - multi_frame: Balanced - extracts multiple frames from video clip
            - video_native: Best quality, highest cost - sends video directly to AI
        audio_enabled: Whether audio stream extraction is enabled (Phase 6)
        audio_codec: Detected audio codec from RTSP stream ('aac', 'pcmu', 'opus', etc.) (Phase 6)
        homekit_stream_quality: HomeKit streaming quality - 'low', 'medium', or 'high' (Phase 7)
            - low: 640x480, 15fps, 500kbps
            - medium: 1280x720, 25fps, 1500kbps
            - high: 1920x1080, 30fps, 3000kbps
        created_at: Record creation timestamp (UTC)
        updated_at: Last modification timestamp (UTC)
    """
    
    __tablename__ = "cameras"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    type = Column(String(10), nullable=False)  # 'rtsp' or 'usb'
    rtsp_url = Column(String(500), nullable=True)
    username = Column(String(100), nullable=True)
    password = Column(String(500), nullable=True)  # Encrypted with Fernet
    device_index = Column(Integer, nullable=True)
    frame_rate = Column(Integer, default=5, nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)
    motion_enabled = Column(Boolean, default=True, nullable=False)
    motion_sensitivity = Column(String(20), default='medium', nullable=False)
    motion_cooldown = Column(Integer, default=60, nullable=False)
    motion_algorithm = Column(String(20), default='mog2', nullable=False)
    detection_zones = Column(Text, nullable=True)  # JSON array of DetectionZone objects
    detection_schedule = Column(Text, nullable=True)  # JSON object: DetectionSchedule schema
    # Phase 2: UniFi Protect integration columns
    source_type = Column(String(20), default='rtsp', nullable=False)  # 'rtsp', 'usb', 'protect'
    protect_controller_id = Column(String, ForeignKey('protect_controllers.id', ondelete='SET NULL'), nullable=True)
    protect_camera_id = Column(String(100), nullable=True)  # Native Protect camera ID
    protect_camera_type = Column(String(20), nullable=True)  # 'camera', 'doorbell'
    smart_detection_types = Column(Text, nullable=True)  # JSON array: ["person", "vehicle", "package", "animal"]
    is_doorbell = Column(Boolean, default=False, nullable=False)
    # Phase 3: Analysis mode for AI processing
    analysis_mode = Column(String(20), default='single_frame', nullable=False, index=True)
    # Phase 4 (P4-5.4): Per-camera custom prompt override based on feedback analysis
    prompt_override = Column(Text, nullable=True)
    # Phase 6 (P6-3.1): Audio stream extraction configuration
    audio_enabled = Column(Boolean, default=False, nullable=False)
    audio_codec = Column(String(20), nullable=True)  # Detected codec: 'aac', 'pcmu', 'opus', etc.
    # Phase 7 (P7-3.1): HomeKit stream quality configuration
    homekit_stream_quality = Column(String(20), default='medium', nullable=False)  # 'low', 'medium', 'high'
    # Phase 6 (P6-3.3): Per-camera audio event settings
    audio_event_types = Column(Text, nullable=True)  # JSON array: ["glass_break", "gunshot", "scream", "doorbell"]
    audio_threshold = Column(Float, nullable=True)  # Per-camera threshold override (0.0-1.0), null = use global
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    motion_events = relationship("MotionEvent", back_populates="camera", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="camera", cascade="all, delete-orphan")
    protect_controller = relationship("ProtectController", back_populates="cameras")
    homekit_accessories = relationship("HomeKitAccessory", back_populates="camera", cascade="all, delete-orphan")
    
    __table_args__ = (
        CheckConstraint("type IN ('rtsp', 'usb')", name='check_camera_type'),
        CheckConstraint("frame_rate >= 1 AND frame_rate <= 30", name='check_frame_rate'),
        CheckConstraint("motion_sensitivity IN ('low', 'medium', 'high')", name='check_sensitivity'),
        CheckConstraint("motion_cooldown >= 0 AND motion_cooldown <= 300", name='check_cooldown'),
        CheckConstraint("analysis_mode IN ('single_frame', 'multi_frame', 'video_native')", name='check_analysis_mode'),
        CheckConstraint("homekit_stream_quality IN ('low', 'medium', 'high')", name='check_homekit_stream_quality'),
    )
    
    @validates('password')
    def encrypt_password_validator(self, key, value):
        """
        Automatically encrypt password before storing in database
        
        Validator runs on:
        - Model instantiation: Camera(password="plain")
        - Attribute assignment: camera.password = "plain"
        
        Args:
            key: Column name ('password')
            value: Password value to validate/encrypt
            
        Returns:
            Encrypted password with 'encrypted:' prefix
        """
        if not value:
            return None
        
        # Avoid double encryption
        if value.startswith('encrypted:'):
            return value
        
        try:
            encrypted = encrypt_password(value)
            logger.debug(f"Password encrypted for camera {getattr(self, 'id', 'new')}")
            return encrypted
        except Exception as e:
            logger.error(f"Password encryption failed: {e}")
            raise ValueError("Failed to encrypt password")
    
    def get_decrypted_password(self) -> str:
        """
        Decrypt password for use in RTSP connection string
        
        Returns:
            Plain text password or None if not set
            
        Example:
            >>> camera = db.query(Camera).first()
            >>> password = camera.get_decrypted_password()
            >>> rtsp_url = f"rtsp://{camera.username}:{password}@{host}:{port}/path"
        """
        if not self.password:
            return None
        
        try:
            return decrypt_password(self.password)
        except Exception as e:
            logger.error(f"Password decryption failed for camera {self.id}: {e}")
            raise ValueError("Failed to decrypt password")
    
    def __repr__(self):
        return f"<Camera(id={self.id}, name={self.name}, type={self.type}, enabled={self.is_enabled})>"
