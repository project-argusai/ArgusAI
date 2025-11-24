"""Unit tests for CleanupService"""
import pytest
import os
import tempfile
import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.event import Event
from app.services.cleanup_service import CleanupService


class TestCleanupService:
    """Test suite for CleanupService"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test database and cleanup service for each test"""
        # Create temporary database file
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.db_fd)

        # Create engine and session
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

        # Create temporary thumbnail directory
        self.thumbnail_dir = tempfile.mkdtemp()

        # Initialize CleanupService with test session factory and thumbnail directory
        self.cleanup_service = CleanupService(session_factory=self.SessionLocal)
        self.cleanup_service.thumbnail_base_dir = self.thumbnail_dir

        yield

        # Cleanup
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

        # Cleanup thumbnails
        import shutil
        if os.path.exists(self.thumbnail_dir):
            shutil.rmtree(self.thumbnail_dir)

    def _create_test_event(
        self,
        event_id: str,
        timestamp: datetime,
        create_thumbnail: bool = False
    ) -> Event:
        """Helper to create test event"""
        thumbnail_path = None

        if create_thumbnail:
            # Create thumbnail file
            date_str = timestamp.strftime('%Y-%m-%d')
            date_dir = os.path.join(self.thumbnail_dir, date_str)
            os.makedirs(date_dir, exist_ok=True)

            thumbnail_filename = f"event_{event_id}.jpg"
            thumbnail_path = os.path.join(date_dir, thumbnail_filename)

            # Write dummy thumbnail data
            with open(thumbnail_path, 'wb') as f:
                f.write(b"fake_jpeg_data_" * 100)  # ~1.5KB

            # Store relative path
            thumbnail_path = f"thumbnails/{date_str}/{thumbnail_filename}"

        event = Event(
            id=event_id,
            camera_id="test-camera-id",
            timestamp=timestamp,
            description="Test event",
            confidence=85,
            objects_detected='["person"]',
            thumbnail_path=thumbnail_path,
            alert_triggered=False
        )

        return event

    @pytest.mark.asyncio
    async def test_cleanup_old_events_basic(self):
        """Test basic cleanup of old events"""
        # Override SessionLocal in cleanup_service module
        import app.services.cleanup_service as cleanup_module
        original_session = cleanup_module.SessionLocal
        cleanup_module.SessionLocal = self.SessionLocal

        db = self.SessionLocal()

        try:
            # Create events at different ages
            now = datetime.now(timezone.utc)

            # Old events (45 days ago) - should be deleted
            old_events = [
                self._create_test_event(
                    f"old-{i}",
                    now - timedelta(days=45),
                    create_thumbnail=True
                )
                for i in range(5)
            ]

            # Recent events (15 days ago) - should NOT be deleted
            recent_events = [
                self._create_test_event(
                    f"recent-{i}",
                    now - timedelta(days=15),
                    create_thumbnail=True
                )
                for i in range(3)
            ]

            # Add all events
            db.add_all(old_events + recent_events)
            db.commit()

            # Verify initial count
            assert db.query(Event).count() == 8

            # Run cleanup with 30-day retention
            stats = await self.cleanup_service.cleanup_old_events(retention_days=30)

            # Verify stats
            assert stats["events_deleted"] == 5
            assert stats["thumbnails_deleted"] == 5
            assert stats["space_freed_mb"] > 0
            assert stats["batches_processed"] == 1

            # Verify only recent events remain
            remaining_events = db.query(Event).all()
            assert len(remaining_events) == 3
            assert all(event.id.startswith("recent-") for event in remaining_events)

        finally:
            db.close()
            cleanup_module.SessionLocal = original_session

    @pytest.mark.asyncio
    async def test_cleanup_batch_processing(self):
        """Test batch processing with large event count"""
        # Override SessionLocal
        import app.services.cleanup_service as cleanup_module
        original_session = cleanup_module.SessionLocal
        cleanup_module.SessionLocal = self.SessionLocal

        db = self.SessionLocal()

        try:
            # Create 2500 old events (should process in 3 batches of 1000)
            now = datetime.now(timezone.utc)
            old_timestamp = now - timedelta(days=45)

            old_events = [
                self._create_test_event(f"old-{i}", old_timestamp, create_thumbnail=False)
                for i in range(2500)
            ]

            db.add_all(old_events)
            db.commit()

            # Verify initial count
            assert db.query(Event).count() == 2500

            # Run cleanup with smaller batch size
            stats = await self.cleanup_service.cleanup_old_events(
                retention_days=30,
                batch_size=1000
            )

            # Verify stats
            assert stats["events_deleted"] == 2500
            assert stats["batches_processed"] == 3

            # Verify all events deleted
            assert db.query(Event).count() == 0

        finally:
            db.close()
            cleanup_module.SessionLocal = original_session

    @pytest.mark.asyncio
    async def test_cleanup_missing_thumbnails(self):
        """Test cleanup handles missing thumbnail files gracefully"""
        # Override SessionLocal
        import app.services.cleanup_service as cleanup_module
        original_session = cleanup_module.SessionLocal
        cleanup_module.SessionLocal = self.SessionLocal

        db = self.SessionLocal()

        try:
            now = datetime.now(timezone.utc)
            old_timestamp = now - timedelta(days=45)

            # Create event with thumbnail path that doesn't exist
            event = self._create_test_event("test-1", old_timestamp, create_thumbnail=False)
            event.thumbnail_path = "thumbnails/2025-01-01/nonexistent.jpg"

            db.add(event)
            db.commit()

            # Run cleanup (should not fail)
            stats = await self.cleanup_service.cleanup_old_events(retention_days=30)

            # Verify event deleted despite missing thumbnail
            assert stats["events_deleted"] == 1
            assert stats["thumbnails_deleted"] == 0
            assert stats["thumbnails_failed"] == 1

        finally:
            db.close()
            cleanup_module.SessionLocal = original_session

    @pytest.mark.asyncio
    async def test_cleanup_no_events_to_delete(self):
        """Test cleanup when no events need deletion"""
        db = self.SessionLocal()

        try:
            # Create only recent events
            now = datetime.now(timezone.utc)
            recent_events = [
                self._create_test_event(f"recent-{i}", now - timedelta(days=5))
                for i in range(3)
            ]

            db.add_all(recent_events)
            db.commit()

            # Run cleanup
            stats = await self.cleanup_service.cleanup_old_events(retention_days=30)

            # Verify no deletions
            assert stats["events_deleted"] == 0
            assert stats["thumbnails_deleted"] == 0
            assert stats["batches_processed"] == 0

            # Verify all events remain
            assert db.query(Event).count() == 3

        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_get_database_size(self):
        """Test database size calculation"""
        db = self.SessionLocal()

        try:
            # Add some events to increase database size
            now = datetime.now(timezone.utc)
            events = [
                self._create_test_event(f"event-{i}", now)
                for i in range(100)
            ]

            db.add_all(events)
            db.commit()

            # Get database size
            # Note: We need to pass the test database path to the cleanup service
            from app.core.database import SessionLocal as OriginalSessionLocal
            from app.core import database
            import app.services.cleanup_service as cleanup_module

            # Temporarily override SessionLocal
            original_session = cleanup_module.SessionLocal
            cleanup_module.SessionLocal = self.SessionLocal

            try:
                size_mb = await self.cleanup_service.get_database_size()

                # Verify size is reasonable (should be > 0 with 100 events)
                assert size_mb > 0
                assert size_mb < 10  # Should be less than 10MB for 100 events

            finally:
                # Restore original SessionLocal
                cleanup_module.SessionLocal = original_session

        finally:
            db.close()

    def test_get_thumbnails_size(self):
        """Test thumbnail directory size calculation"""
        # Create some thumbnail files
        date_str = datetime.now().strftime('%Y-%m-%d')
        date_dir = os.path.join(self.thumbnail_dir, date_str)
        os.makedirs(date_dir, exist_ok=True)

        # Create 10 thumbnail files (each ~1.5KB)
        for i in range(10):
            thumbnail_path = os.path.join(date_dir, f"test_{i}.jpg")
            with open(thumbnail_path, 'wb') as f:
                f.write(b"fake_jpeg_data_" * 100)

        # Get thumbnails size
        size_mb = self.cleanup_service.get_thumbnails_size()

        # Verify size is reasonable (~0.015 MB for 10 files)
        assert size_mb > 0
        assert size_mb < 1

    def test_get_thumbnails_size_empty_directory(self):
        """Test thumbnail size with empty directory"""
        size_mb = self.cleanup_service.get_thumbnails_size()
        assert size_mb == 0.0

    def test_get_thumbnails_size_nonexistent_directory(self):
        """Test thumbnail size with nonexistent directory"""
        self.cleanup_service.thumbnail_base_dir = "/path/does/not/exist"
        size_mb = self.cleanup_service.get_thumbnails_size()
        assert size_mb == 0.0

    @pytest.mark.asyncio
    async def test_get_storage_info(self):
        """Test comprehensive storage info"""
        db = self.SessionLocal()

        try:
            # Create events with thumbnails
            now = datetime.now(timezone.utc)
            events = [
                self._create_test_event(f"event-{i}", now, create_thumbnail=True)
                for i in range(10)
            ]

            db.add_all(events)
            db.commit()

            # Override SessionLocal temporarily
            import app.services.cleanup_service as cleanup_module
            original_session = cleanup_module.SessionLocal
            cleanup_module.SessionLocal = self.SessionLocal

            try:
                # Get storage info
                storage_info = await self.cleanup_service.get_storage_info()

                # Verify structure
                assert "database_mb" in storage_info
                assert "thumbnails_mb" in storage_info
                assert "total_mb" in storage_info
                assert "event_count" in storage_info

                # Verify values
                assert storage_info["database_mb"] > 0
                assert storage_info["thumbnails_mb"] > 0
                assert storage_info["total_mb"] == storage_info["database_mb"] + storage_info["thumbnails_mb"]
                assert storage_info["event_count"] == 10

            finally:
                cleanup_module.SessionLocal = original_session

        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_cleanup_performance(self):
        """Test cleanup performance with 10K+ events"""
        # Override SessionLocal
        import app.services.cleanup_service as cleanup_module
        original_session = cleanup_module.SessionLocal
        cleanup_module.SessionLocal = self.SessionLocal

        db = self.SessionLocal()

        try:
            # Create 10,000 old events
            now = datetime.now(timezone.utc)
            old_timestamp = now - timedelta(days=45)

            # Use batch inserts for performance
            batch_size = 1000
            for batch_num in range(10):
                events = [
                    self._create_test_event(
                        f"perf-{batch_num}-{i}",
                        old_timestamp,
                        create_thumbnail=False
                    )
                    for i in range(batch_size)
                ]
                db.add_all(events)
                db.commit()

            # Verify initial count
            assert db.query(Event).count() == 10000

            # Measure cleanup time
            import time
            start_time = time.time()

            stats = await self.cleanup_service.cleanup_old_events(
                retention_days=30,
                batch_size=1000
            )

            elapsed_time = time.time() - start_time

            # Verify stats
            assert stats["events_deleted"] == 10000
            assert stats["batches_processed"] == 10

            # Verify performance (should complete in reasonable time)
            # For 10K events in 10 batches, should be < 5 seconds
            assert elapsed_time < 5.0

            # Verify all events deleted
            assert db.query(Event).count() == 0

        finally:
            db.close()
            cleanup_module.SessionLocal = original_session
