"""Tests for MotionEvent model"""
import pytest
from datetime import datetime, timezone
from app.models.motion_event import MotionEvent
from app.models.camera import Camera
import json


class TestMotionEventModel:
    """Test MotionEvent SQLAlchemy model"""

    def test_create_motion_event(self, db_session):
        """Test creating motion event with all fields"""
        # Create camera first
        camera = Camera(
            name="Test Camera",
            type="usb",
            device_index=0
        )
        db_session.add(camera)
        db_session.commit()

        # Create motion event
        event = MotionEvent(
            camera_id=camera.id,
            timestamp=datetime.now(timezone.utc),
            confidence=0.85,
            motion_intensity=15.5,
            algorithm_used="mog2",
            bounding_box=json.dumps({"x": 100, "y": 50, "width": 200, "height": 300}),
            frame_thumbnail="base64encodedimage..."
        )

        db_session.add(event)
        db_session.commit()
        db_session.refresh(event)

        assert event.id is not None
        assert event.camera_id == camera.id
        assert event.confidence == 0.85
        assert event.algorithm_used == "mog2"
        assert event.frame_thumbnail == "base64encodedimage..."

    def test_motion_event_relationship(self, db_session):
        """Test relationship between MotionEvent and Camera"""
        camera = Camera(name="Test Camera", type="usb", device_index=0)
        db_session.add(camera)
        db_session.commit()

        event = MotionEvent(
            camera_id=camera.id,
            timestamp=datetime.now(timezone.utc),
            confidence=0.9,
            algorithm_used="knn"
        )
        db_session.add(event)
        db_session.commit()

        # Test relationship
        assert event.camera == camera
        assert camera.motion_events[0] == event

    def test_confidence_check_constraint(self, db_session):
        """Test confidence must be between 0.0 and 1.0"""
        camera = Camera(name="Test Camera", type="usb", device_index=0)
        db_session.add(camera)
        db_session.commit()

        # This should fail with confidence > 1.0
        event = MotionEvent(
            camera_id=camera.id,
            timestamp=datetime.now(timezone.utc),
            confidence=1.5,  # Invalid
            algorithm_used="mog2"
        )
        db_session.add(event)

        with pytest.raises(Exception):  # SQLAlchemy will raise integrity error
            db_session.commit()

        db_session.rollback()

    def test_cascade_delete(self, db_session):
        """Test that deleting camera deletes motion events"""
        camera = Camera(name="Test Camera", type="usb", device_index=0)
        db_session.add(camera)
        db_session.commit()

        event = MotionEvent(
            camera_id=camera.id,
            timestamp=datetime.now(timezone.utc),
            confidence=0.8,
            algorithm_used="frame_diff"
        )
        db_session.add(event)
        db_session.commit()

        event_id = event.id

        # Delete camera
        db_session.delete(camera)
        db_session.commit()

        # Event should also be deleted (cascade)
        deleted_event = db_session.query(MotionEvent).filter(MotionEvent.id == event_id).first()
        assert deleted_event is None
