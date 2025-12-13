"""
Face Embedding Service for Person Recognition (Story P4-8.1)

This module orchestrates face detection and embedding generation for
event thumbnails. It uses the FaceDetectionService to find faces and
the existing EmbeddingService to generate CLIP embeddings of face regions.

Architecture:
    - Coordinates FaceDetectionService and EmbeddingService
    - Stores face embeddings with bounding box metadata
    - Respects privacy settings (face_recognition_enabled)
    - Processes faces asynchronously (non-blocking)

Privacy:
    - Only processes faces when face_recognition_enabled is true
    - Face data stored locally only
    - Users can delete all face embeddings via API
"""
import asyncio
import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.face_embedding import FaceEmbedding
from app.services.face_detection_service import (
    FaceDetectionService,
    get_face_detection_service,
    FaceDetection,
)
from app.services.embedding_service import EmbeddingService, get_embedding_service

logger = logging.getLogger(__name__)


class FaceEmbeddingService:
    """
    Generate and store face-specific embeddings.

    Combines face detection with CLIP embedding generation to create
    face embeddings for person recognition. Each detected face in an
    event thumbnail gets its own embedding stored in the database.

    Attributes:
        MODEL_VERSION: Version string for tracking embedding compatibility
    """

    MODEL_VERSION = "clip-ViT-B-32-face-v1"

    def __init__(
        self,
        face_detector: Optional[FaceDetectionService] = None,
        embedding_service: Optional[EmbeddingService] = None,
    ):
        """
        Initialize FaceEmbeddingService.

        Args:
            face_detector: Face detection service (uses singleton if None)
            embedding_service: Embedding service (uses singleton if None)
        """
        self._face_detector = face_detector or get_face_detection_service()
        self._embedding_service = embedding_service or get_embedding_service()

        logger.info(
            "FaceEmbeddingService initialized",
            extra={
                "event_type": "face_embedding_service_init",
                "model_version": self.MODEL_VERSION,
            }
        )

    async def process_event_faces(
        self,
        db: Session,
        event_id: str,
        thumbnail_bytes: bytes,
        confidence_threshold: Optional[float] = None,
    ) -> list[str]:
        """
        Detect faces, generate embeddings, and store them.

        Args:
            db: SQLAlchemy database session
            event_id: UUID of the event
            thumbnail_bytes: Raw thumbnail image bytes
            confidence_threshold: Optional confidence threshold for face detection

        Returns:
            List of created FaceEmbedding IDs

        Raises:
            ValueError: If thumbnail_bytes is empty
        """
        if not thumbnail_bytes:
            raise ValueError("thumbnail_bytes cannot be empty")

        # Step 1: Detect faces
        faces = await self._face_detector.detect_faces(
            thumbnail_bytes,
            confidence_threshold=confidence_threshold
        )

        if not faces:
            logger.debug(
                "No faces detected in event thumbnail",
                extra={"event_type": "no_faces_detected", "event_id": event_id}
            )
            return []

        logger.info(
            f"Detected {len(faces)} face(s) in event thumbnail",
            extra={
                "event_type": "faces_detected",
                "event_id": event_id,
                "face_count": len(faces),
                "confidences": [f.confidence for f in faces],
            }
        )

        # Step 2: Process each face
        face_embedding_ids = []

        for i, face in enumerate(faces):
            try:
                # Extract face region
                face_bytes = await self._face_detector.extract_face_region(
                    thumbnail_bytes,
                    face.bbox
                )

                # Generate embedding using CLIP on the cropped face
                embedding_vector = await self._embedding_service.generate_embedding(
                    face_bytes
                )

                # Store face embedding
                face_embedding = FaceEmbedding(
                    event_id=event_id,
                    embedding=json.dumps(embedding_vector),
                    bounding_box=json.dumps(face.bbox.to_dict()),
                    confidence=face.confidence,
                    model_version=self.MODEL_VERSION,
                )

                db.add(face_embedding)
                db.commit()
                db.refresh(face_embedding)

                face_embedding_ids.append(face_embedding.id)

                logger.debug(
                    f"Stored face embedding {i+1}/{len(faces)}",
                    extra={
                        "event_type": "face_embedding_stored",
                        "event_id": event_id,
                        "face_embedding_id": face_embedding.id,
                        "confidence": face.confidence,
                    }
                )

            except Exception as e:
                logger.error(
                    f"Failed to process face {i+1}/{len(faces)}: {e}",
                    exc_info=True,
                    extra={
                        "event_type": "face_embedding_error",
                        "event_id": event_id,
                        "face_index": i,
                        "error": str(e),
                    }
                )
                # Continue processing remaining faces

        logger.info(
            f"Processed {len(face_embedding_ids)}/{len(faces)} face embeddings for event",
            extra={
                "event_type": "face_embeddings_complete",
                "event_id": event_id,
                "success_count": len(face_embedding_ids),
                "total_faces": len(faces),
            }
        )

        return face_embedding_ids

    async def get_face_embeddings(
        self,
        db: Session,
        event_id: str,
    ) -> list[dict]:
        """
        Get all face embeddings for an event.

        Args:
            db: SQLAlchemy database session
            event_id: UUID of the event

        Returns:
            List of face embedding dictionaries with metadata
        """
        embeddings = db.query(FaceEmbedding).filter(
            FaceEmbedding.event_id == event_id
        ).order_by(FaceEmbedding.confidence.desc()).all()

        return [
            {
                "id": e.id,
                "event_id": e.event_id,
                "entity_id": e.entity_id,
                "bounding_box": json.loads(e.bounding_box),
                "confidence": e.confidence,
                "model_version": e.model_version,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in embeddings
        ]

    async def get_face_embedding_vector(
        self,
        db: Session,
        face_embedding_id: str,
    ) -> Optional[list[float]]:
        """
        Get the actual embedding vector for a face embedding.

        Args:
            db: SQLAlchemy database session
            face_embedding_id: UUID of the face embedding

        Returns:
            List of 512 floats, or None if not found
        """
        embedding = db.query(FaceEmbedding).filter(
            FaceEmbedding.id == face_embedding_id
        ).first()

        if embedding is None:
            return None

        return json.loads(embedding.embedding)

    async def delete_event_faces(
        self,
        db: Session,
        event_id: str,
    ) -> int:
        """
        Delete all face embeddings for an event.

        Args:
            db: SQLAlchemy database session
            event_id: UUID of the event

        Returns:
            Number of face embeddings deleted
        """
        count = db.query(FaceEmbedding).filter(
            FaceEmbedding.event_id == event_id
        ).delete()

        db.commit()

        logger.info(
            f"Deleted {count} face embedding(s) for event",
            extra={
                "event_type": "face_embeddings_deleted",
                "event_id": event_id,
                "count": count,
            }
        )

        return count

    async def delete_all_faces(self, db: Session) -> int:
        """
        Delete all face embeddings from the database.

        This is used for privacy controls - allowing users to clear
        all face data.

        Args:
            db: SQLAlchemy database session

        Returns:
            Number of face embeddings deleted
        """
        count = db.query(FaceEmbedding).delete()
        db.commit()

        logger.info(
            f"Deleted all face embeddings",
            extra={
                "event_type": "all_face_embeddings_deleted",
                "count": count,
            }
        )

        return count

    async def get_face_count(self, db: Session, event_id: str) -> int:
        """
        Get the count of face embeddings for an event.

        Args:
            db: SQLAlchemy database session
            event_id: UUID of the event

        Returns:
            Number of face embeddings
        """
        return db.query(FaceEmbedding).filter(
            FaceEmbedding.event_id == event_id
        ).count()

    async def get_total_face_count(self, db: Session) -> int:
        """
        Get the total count of all face embeddings.

        Args:
            db: SQLAlchemy database session

        Returns:
            Total number of face embeddings in database
        """
        return db.query(FaceEmbedding).count()

    def get_model_version(self) -> str:
        """Get the current model version string."""
        return self.MODEL_VERSION


# Global singleton instance
_face_embedding_service: Optional[FaceEmbeddingService] = None


def get_face_embedding_service() -> FaceEmbeddingService:
    """
    Get the global FaceEmbeddingService instance.

    Creates the instance on first call (lazy initialization).

    Returns:
        FaceEmbeddingService singleton instance
    """
    global _face_embedding_service

    if _face_embedding_service is None:
        _face_embedding_service = FaceEmbeddingService()
        logger.info(
            "Global FaceEmbeddingService instance created",
            extra={"event_type": "face_embedding_service_singleton_created"}
        )

    return _face_embedding_service
