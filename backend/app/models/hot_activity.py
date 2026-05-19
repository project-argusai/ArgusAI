"""Lightweight tables for persisting hot camera/entity activity (used by AIProcessingCoordinator)."""

from sqlalchemy import Column, String, Integer, Float
from app.core.database import Base


class HotCameraActivity(Base):
    __tablename__ = "hot_camera_activity"

    camera_id = Column(String, primary_key=True)
    count = Column(Integer, default=0, nullable=False)
    last_seen = Column(Float, nullable=False)  # unix timestamp


class HotEntityActivity(Base):
    __tablename__ = "hot_entity_activity"

    entity_id = Column(String, primary_key=True)
    name = Column(String, nullable=True)
    type = Column(String(20), nullable=True)  # person / vehicle / unknown
    count = Column(Integer, default=0, nullable=False)
    last_seen = Column(Float, nullable=False)  # unix timestamp
