"""Camera SQLAlchemy ORM model"""
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, CheckConstraint
from sqlalchemy.orm import validates, relationship
from app.core.database import Base
from app.utils.encryption import encrypt_password, decrypt_password
import uuid
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class Camera(Base):
    """
    Camera model representing RTSP or USB camera configuration
    
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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    motion_events = relationship("MotionEvent", back_populates="camera", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="camera", cascade="all, delete-orphan")
    
    __table_args__ = (
        CheckConstraint("type IN ('rtsp', 'usb')", name='check_camera_type'),
        CheckConstraint("frame_rate >= 1 AND frame_rate <= 30", name='check_frame_rate'),
        CheckConstraint("motion_sensitivity IN ('low', 'medium', 'high')", name='check_sensitivity'),
        CheckConstraint("motion_cooldown >= 0 AND motion_cooldown <= 300", name='check_cooldown'),
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
