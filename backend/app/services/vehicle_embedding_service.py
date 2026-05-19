"""
Vehicle Embedding Service for Vehicle Recognition (Story P4-8.3)

This module orchestrates vehicle detection and embedding generation for
event thumbnails. It uses the VehicleDetectionService to find vehicles and
the existing EmbeddingService to generate CLIP embeddings of vehicle regions.

Architecture:
    - Coordinates VehicleDetectionService and EmbeddingService
    - Stores vehicle embeddings with bounding box metadata
    - Respects privacy settings (vehicle_recognition_enabled)
    - Processes vehicles asynchronously (non-blocking)

Privacy:
    - Only processes vehicles when vehicle_recognition_enabled is true
    - Vehicle data stored locally only
    - Users can delete all vehicle embeddings via API

# Migrated to @singleton as part of #450 (Lightweight DI Container).
"""
import asyncio
import json
import logging
from app.core.decorators import singleton
from typing import Optional

from sqlalchemy.orm import Session

from app.models.vehicle_embedding import VehicleEmbedding
from app.services.vehicle_detection_service import (
    VehicleDetectionService,
    get_vehicle_detection_service,
    VehicleDetection,
)
from app.services.embedding_service import EmbeddingService, get_embedding_service

logger = logging.getLogger(__name__)


@singleton
class VehicleEmbeddingService:
    """
    Generate and store vehicle-specific embeddings.

    Combines vehicle detection with CLIP embedding generation to create
    vehicle embeddings for vehicle recognition. Each detected vehicle in an
    event thumbnail gets its own embedding stored in the database.

    Attributes:
        MODEL_VERSION: Version string for tracking embedding compatibility
    """

    MODEL_VERSION = "clip-ViT-B-32-vehicle-v1"

    def __init__(
        self,
        vehicle_detector: Optional[VehicleDetectionService] = None,
        embedding_service: Optional[EmbeddingService] = None,
    ):
        """
        Initialize VehicleEmbeddingService.

        Args:
            vehicle_detector: Vehicle detection service (uses singleton if None)
            embedding_service: Embedding service (uses singleton if None)
        """
        self._vehicle_detector = vehicle_detector or get_vehicle_detection_service()
        self._embedding_service = embedding_service or get_embedding_service()

        logger.info(
            "VehicleEmbeddingService initialized",
            extra={
                "event_type": "vehicle_embedding_service_init",
                "model_version": self.MODEL_VERSION,
            }
        )

    async def process_event_vehicles(
        self,
        db: Session,
        event_id: str,
        thumbnail_bytes: bytes,
        confidence_threshold: Optional[float] = None,
    ) -> list[str]:
        """
        Detect vehicles, generate embeddings, and store them.

        Args:
            db: SQLAlchemy database session
            event_id: UUID of the event
            thumbnail_bytes: Raw thumbnail image bytes
            confidence_threshold: Optional confidence threshold for vehicle detection

        Returns:
            List of created VehicleEmbedding IDs

        Raises:
            ValueError: If thumbnail_bytes is empty
        """
        if not thumbnail_bytes:
            raise ValueError("thumbnail_bytes cannot be empty")

        # Step 1: Detect vehicles
        vehicles = await self._vehicle_detector.detect_vehicles(
            thumbnail_bytes,
            confidence_threshold=confidence_threshold
        )

        if not vehicles:
            logger.debug(
                "No vehicles detected in event thumbnail",
                extra={"event_type": "no_vehicles_detected", "event_id": event_id}
            )
            return []

        logger.info(
            f"Detected {len(vehicles)} vehicle(s) in event thumbnail",
            extra={
                "event_type": "vehicles_detected",
                "event_id": event_id,
                "vehicle_count": len(vehicles),
                "confidences": [v.confidence for v in vehicles],
                "vehicle_types": [v.vehicle_type for v in vehicles],
            }
        )

        # Step 2: Process each vehicle
        vehicle_embedding_ids = []

        for i, vehicle in enumerate(vehicles):
            try:
                # Extract vehicle region
                vehicle_bytes = self._vehicle_detector.crop_vehicle(
                    thumbnail_bytes,
                    vehicle.bbox
                )

                # Generate embedding using CLIP on the cropped vehicle
                embedding_vector = await self._embedding_service.generate_embedding(
                    vehicle_bytes
                )

                # Store vehicle embedding
                vehicle_embedding = VehicleEmbedding(
                    event_id=event_id,
                    embedding=json.dumps(embedding_vector),
                    bounding_box=json.dumps(vehicle.bbox.to_dict()),
                    confidence=vehicle.confidence,
                    vehicle_type=vehicle.vehicle_type,
                    model_version=self.MODEL_VERSION,
                )

                db.add(vehicle_embedding)
                db.commit()
                db.refresh(vehicle_embedding)

                vehicle_embedding_ids.append(vehicle_embedding.id)

                logger.debug(
                    f"Stored vehicle embedding {i+1}/{len(vehicles)}",
                    extra={
                        "event_type": "vehicle_embedding_stored",
                        "event_id": event_id,
                        "vehicle_embedding_id": vehicle_embedding.id,
                        "confidence": vehicle.confidence,
                        "vehicle_type": vehicle.vehicle_type,
                    }
                )

            except Exception as e:
                logger.error(
                    f"Failed to process vehicle {i+1}/{len(vehicles)}: {e}",
                    exc_info=True,
                    extra={
                        "event_type": "vehicle_embedding_error",
                        "event_id": event_id,
                        "vehicle_index": i,
                        "error": str(e),
                    }
                )
                # Continue processing remaining vehicles

        logger.info(
            f"Processed {len(vehicle_embedding_ids)}/{len(vehicles)} vehicle embeddings for event",
            extra={
                "event_type": "vehicle_embeddings_complete",
                "event_id": event_id,
                "success_count": len(vehicle_embedding_ids),
                "total_vehicles": len(vehicles),
            }
        )

        return vehicle_embedding_ids

    async def get_vehicle_embeddings(
        self,
        db: Session,
        event_id: str,
    ) -> list[dict]:
        """
        Get all vehicle embeddings for an event.

        Args:
            db: SQLAlchemy database session
            event_id: UUID of the event

        Returns:
            List of vehicle embedding dictionaries with metadata
        """
        embeddings = db.query(VehicleEmbedding).filter(
            VehicleEmbedding.event_id == event_id
        ).order_by(VehicleEmbedding.confidence.desc()).all()

        return [
            {
                "id": e.id,
                "event_id": e.event_id,
                "entity_id": e.entity_id,
                "bounding_box": json.loads(e.bounding_box),
                "confidence": e.confidence,
                "vehicle_type": e.vehicle_type,
                "model_version": e.model_version,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in embeddings
        ]

    async def get_vehicle_embedding_vector(
        self,
        db: Session,
        vehicle_embedding_id: str,
    ) -> Optional[list[float]]:
        """
        Get the actual embedding vector for a vehicle embedding.

        Args:
            db: SQLAlchemy database session
            vehicle_embedding_id: UUID of the vehicle embedding

        Returns:
            List of 512 floats, or None if not found
        """
        embedding = db.query(VehicleEmbedding).filter(
            VehicleEmbedding.id == vehicle_embedding_id
        ).first()

        if embedding is None:
            return None

        return json.loads(embedding.embedding)

    async def delete_event_vehicles(
        self,
        db: Session,
        event_id: str,
    ) -> int:
        """
        Delete all vehicle embeddings for an event.

        Args:
            db: SQLAlchemy database session
            event_id: UUID of the event

        Returns:
            Number of vehicle embeddings deleted
        """
        count = db.query(VehicleEmbedding).filter(
            VehicleEmbedding.event_id == event_id
        ).delete()

        db.commit()

        logger.info(
            f"Deleted {count} vehicle embedding(s) for event",
            extra={
                "event_type": "vehicle_embeddings_deleted",
                "event_id": event_id,
                "count": count,
            }
        )

        return count

    async def delete_all_vehicles(self, db: Session) -> int:
        """
        Delete all vehicle embeddings from the database.

        This is used for privacy controls - allowing users to clear
        all vehicle data.

        Args:
            db: SQLAlchemy database session

        Returns:
            Number of vehicle embeddings deleted
        """
        count = db.query(VehicleEmbedding).delete()
        db.commit()

        logger.info(
            f"Deleted all vehicle embeddings",
            extra={
                "event_type": "all_vehicle_embeddings_deleted",
                "count": count,
            }
        )

        return count

    async def get_vehicle_count(self, db: Session, event_id: str) -> int:
        """
        Get the count of vehicle embeddings for an event.

        Args:
            db: SQLAlchemy database session
            event_id: UUID of the event

        Returns:
            Number of vehicle embeddings
        """
        return db.query(VehicleEmbedding).filter(
            VehicleEmbedding.event_id == event_id
        ).count()

    async def get_total_vehicle_count(self, db: Session) -> int:
        """
        Get the total count of all vehicle embeddings.

        Args:
            db: SQLAlchemy database session

        Returns:
            Total number of vehicle embeddings in database
        """
        return db.query(VehicleEmbedding).count()

    def get_model_version(self) -> str:
        """Get the current model version string."""
        return self.MODEL_VERSION


# Backward compatible thin getter (delegates to @singleton decorator)
def get_vehicle_embedding_service() -> VehicleEmbeddingService:
    """
    Get the global VehicleEmbeddingService instance.

    Note: This is now a thin backward-compatible wrapper.
          New code should prefer VehicleEmbeddingService() directly.
    """
    return VehicleEmbeddingService()


def reset_vehicle_embedding_service() -> None:
    """Reset the global VehicleEmbeddingService instance (for testing)."""
    VehicleEmbeddingService._reset_instance()

    return _vehicle_embedding_service


def reset_vehicle_embedding_service() -> None:
    """Reset the global VehicleEmbeddingService instance (for testing)."""
    VehicleEmbeddingService._reset_instance()
