"""
Embedding Service for Temporal Context Engine (Story P4-3.1, P11-4.1)

This module provides image and text embedding generation using CLIP ViT-B/32 model
via sentence-transformers for finding similar events, recognizing recurring
visitors/vehicles, and query-adaptive frame selection.

Architecture:
    - Lazy model loading on first embedding request
    - 512-dimensional embeddings (CLIP ViT-B/32 output)
    - Target inference time: <200ms per image, <50ms per text query
    - SQLite-compatible JSON storage (no pgvector required)
    - Graceful fallback if embedding generation fails

Flow (Image):
    Event Created → EventProcessor → EmbeddingService.generate_embedding()
                                              ↓
                                      CLIP Model (ViT-B/32)
                                              ↓
                                      EventEmbedding (DB)

Flow (Text - Story P11-4.1):
    User Query → EmbeddingService.encode_text() → Query Embedding
                                                        ↓
                            Compare with Frame Embeddings (cosine similarity)

Migrated to @singleton as part of #450 (Lightweight DI Container).
"""
import asyncio
import base64
import io
import json
import logging
from app.core.decorators import singleton
import time
from typing import Optional

from PIL import Image
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@singleton
class EmbeddingService:
    """
    Generate image embeddings using CLIP ViT-B/32 model.

    The service uses lazy loading - the CLIP model is only loaded
    on the first embedding request to minimize startup time.

    Attributes:
        MODEL_NAME: sentence-transformers model identifier
        MODEL_VERSION: Version string stored in database for compatibility
        EMBEDDING_DIM: Output embedding dimension (512 for CLIP ViT-B/32)
    """

    MODEL_NAME = "clip-ViT-B-32"
    MODEL_VERSION = "clip-ViT-B-32-v1"
    EMBEDDING_DIM = 512

    def __init__(self):
        """Initialize EmbeddingService with lazy model loading."""
        self._model = None
        self._model_lock = asyncio.Lock()
        logger.info(
            "EmbeddingService initialized",
            extra={
                "event_type": "embedding_service_init",
                "model_name": self.MODEL_NAME,
                "model_version": self.MODEL_VERSION,
                "embedding_dim": self.EMBEDDING_DIM,
            }
        )

    @property
    def model(self):
        """
        Get the CLIP model, loading it lazily on first access.

        Note: This is a synchronous property. For async contexts,
        use _ensure_model_loaded() instead.

        Returns:
            SentenceTransformer model instance
        """
        if self._model is None:
            self._load_model()
        return self._model

    def _load_model(self) -> None:
        """
        Load the CLIP model synchronously.

        This is called internally when the model is first needed.
        Loading takes ~2-3 seconds and downloads ~350MB on first use.
        """
        start_time = time.time()
        logger.info(
            "Loading CLIP model (this may take a few seconds on first use)...",
            extra={"event_type": "embedding_model_loading", "model_name": self.MODEL_NAME}
        )

        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.MODEL_NAME)

            load_time_ms = (time.time() - start_time) * 1000
            logger.info(
                "CLIP model loaded successfully",
                extra={
                    "event_type": "embedding_model_loaded",
                    "model_name": self.MODEL_NAME,
                    "load_time_ms": load_time_ms,
                }
            )
        except Exception as e:
            logger.error(
                f"Failed to load CLIP model: {e}",
                exc_info=True,
                extra={"event_type": "embedding_model_load_error", "error": str(e)}
            )
            raise

    async def _ensure_model_loaded(self) -> None:
        """
        Ensure the model is loaded in an async-safe manner.

        Uses a lock to prevent multiple concurrent model loads.
        """
        if self._model is None:
            async with self._model_lock:
                if self._model is None:
                    # Run model loading in thread pool to avoid blocking
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, self._load_model)

    async def generate_embedding(self, image_bytes: bytes) -> list[float]:
        """
        Generate a 512-dimensional embedding from image bytes.

        Args:
            image_bytes: Raw image bytes (JPEG, PNG, etc.)

        Returns:
            List of 512 floats representing the image embedding

        Raises:
            ValueError: If image_bytes is empty or invalid
            Exception: If embedding generation fails
        """
        if not image_bytes:
            raise ValueError("image_bytes cannot be empty")

        start_time = time.time()

        # Ensure model is loaded
        await self._ensure_model_loaded()

        try:
            # Convert bytes to PIL Image
            image = Image.open(io.BytesIO(image_bytes))

            # Convert to RGB if necessary (CLIP expects RGB)
            if image.mode != "RGB":
                image = image.convert("RGB")

            # Generate embedding in thread pool (CPU-bound operation)
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(
                None,
                lambda: self._model.encode(image, convert_to_numpy=True)
            )

            # Convert to list for JSON serialization
            embedding_list = embedding.tolist()

            inference_time_ms = (time.time() - start_time) * 1000
            logger.debug(
                "Embedding generated",
                extra={
                    "event_type": "embedding_generated",
                    "inference_time_ms": inference_time_ms,
                    "embedding_dim": len(embedding_list),
                }
            )

            return embedding_list

        except Exception as e:
            inference_time_ms = (time.time() - start_time) * 1000
            logger.error(
                f"Embedding generation failed: {e}",
                exc_info=True,
                extra={
                    "event_type": "embedding_generation_error",
                    "inference_time_ms": inference_time_ms,
                    "error": str(e),
                }
            )
            raise

    async def generate_embedding_from_base64(self, base64_str: str) -> list[float]:
        """
        Generate embedding from a base64-encoded image string.

        Args:
            base64_str: Base64-encoded image (with or without data URI prefix)

        Returns:
            List of 512 floats representing the image embedding
        """
        # Strip data URI prefix if present (e.g., "data:image/jpeg;base64,")
        if base64_str.startswith("data:"):
            comma_idx = base64_str.find(",")
            if comma_idx != -1:
                base64_str = base64_str[comma_idx + 1:]

        image_bytes = base64.b64decode(base64_str)
        return await self.generate_embedding(image_bytes)

    async def generate_embedding_from_file(self, file_path: str) -> list[float]:
        """
        Generate embedding from an image file path.

        Args:
            file_path: Path to the image file

        Returns:
            List of 512 floats representing the image embedding
        """
        loop = asyncio.get_event_loop()

        def read_file():
            with open(file_path, "rb") as f:
                return f.read()

        image_bytes = await loop.run_in_executor(None, read_file)
        return await self.generate_embedding(image_bytes)

    async def encode_text(self, query: str) -> list[float]:
        """
        Encode a text query into a 512-dimensional embedding (Story P11-4.1).

        This method enables query-adaptive frame selection by encoding text
        queries into the same embedding space as images. The resulting embedding
        can be compared with image embeddings using cosine similarity.

        Args:
            query: Natural language query (e.g., "package delivery", "Was there a dog?")

        Returns:
            List of 512 floats representing the text embedding

        Raises:
            ValueError: If query is empty or contains only whitespace

        Example:
            >>> embedding = await service.encode_text("package on doorstep")
            >>> len(embedding)
            512
        """
        start_time = time.time()

        # Preprocess query (AC-4.1.4)
        query = query.strip().lower()

        if not query:
            raise ValueError("Query cannot be empty")

        logger.debug(
            "Encoding text query",
            extra={
                "event_type": "text_encoding_start",
                "query_length": len(query),
            }
        )

        # Ensure model is loaded (AC-4.1.2)
        await self._ensure_model_loaded()

        # Format query for CLIP (AC-4.1.5)
        formatted_query = self._format_query_for_clip(query)

        try:
            # Generate embedding in thread pool (CPU-bound operation)
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(
                None,
                lambda: self._model.encode(formatted_query, convert_to_numpy=True)
            )

            # Convert to list for JSON serialization (AC-4.1.3)
            embedding_list = embedding.tolist()

            inference_time_ms = (time.time() - start_time) * 1000
            logger.debug(
                "Text embedding generated",
                extra={
                    "event_type": "text_embedding_generated",
                    "inference_time_ms": inference_time_ms,
                    "embedding_dim": len(embedding_list),
                    "query_formatted": formatted_query != query,
                }
            )

            return embedding_list

        except Exception as e:
            inference_time_ms = (time.time() - start_time) * 1000
            logger.error(
                f"Text embedding generation failed: {e}",
                exc_info=True,
                extra={
                    "event_type": "text_embedding_error",
                    "inference_time_ms": inference_time_ms,
                    "error": str(e),
                }
            )
            raise

    def _format_query_for_clip(self, query: str) -> str:
        """
        Format a query for optimal CLIP text encoding (AC-4.1.5).

        CLIP was trained with "a photo of {object}" format, so short queries
        (3 words or fewer) benefit from this prefix. Longer queries that are
        already sentence-like are passed through unchanged.

        Args:
            query: Preprocessed (lowercase, trimmed) query string

        Returns:
            Formatted query string
        """
        word_count = len(query.split())

        # Short queries benefit from "a photo of" prefix
        if word_count <= 3:
            return f"a photo of {query}"

        # Longer queries are likely already descriptive
        return query

    async def store_embedding(
        self,
        db: Session,
        event_id: str,
        embedding: list[float],
    ) -> str:
        """
        Store an embedding in the database.

        Args:
            db: SQLAlchemy database session
            event_id: UUID of the associated event
            embedding: List of 512 floats

        Returns:
            ID of the created EventEmbedding record
        """
        from app.models.event_embedding import EventEmbedding

        # Serialize embedding to JSON
        embedding_json = json.dumps(embedding)

        event_embedding = EventEmbedding(
            event_id=event_id,
            embedding=embedding_json,
            model_version=self.MODEL_VERSION,
        )

        db.add(event_embedding)
        db.commit()
        db.refresh(event_embedding)

        logger.debug(
            "Embedding stored",
            extra={
                "event_type": "embedding_stored",
                "event_id": event_id,
                "embedding_id": event_embedding.id,
                "model_version": self.MODEL_VERSION,
            }
        )

        return event_embedding.id

    async def get_embedding(self, db: Session, event_id: str) -> Optional[dict]:
        """
        Get embedding metadata for an event.

        Args:
            db: SQLAlchemy database session
            event_id: UUID of the event

        Returns:
            Dict with embedding metadata, or None if not found
        """
        from app.models.event_embedding import EventEmbedding

        embedding = db.query(EventEmbedding).filter(
            EventEmbedding.event_id == event_id
        ).first()

        if embedding is None:
            return None

        return {
            "id": embedding.id,
            "event_id": embedding.event_id,
            "exists": True,
            "model_version": embedding.model_version,
            "created_at": embedding.created_at.isoformat() if embedding.created_at else None,
        }

    async def get_embedding_vector(self, db: Session, event_id: str) -> Optional[list[float]]:
        """
        Get the actual embedding vector for an event.

        Args:
            db: SQLAlchemy database session
            event_id: UUID of the event

        Returns:
            List of 512 floats, or None if not found
        """
        from app.models.event_embedding import EventEmbedding

        embedding = db.query(EventEmbedding).filter(
            EventEmbedding.event_id == event_id
        ).first()

        if embedding is None:
            return None

        return json.loads(embedding.embedding)

    def get_model_version(self) -> str:
        """Get the current model version string."""
        return self.MODEL_VERSION

    def get_embedding_dimension(self) -> int:
        """Get the embedding dimension (512 for CLIP ViT-B/32)."""
        return self.EMBEDDING_DIM

    # =========================================================================
    # Frame Embedding Methods (Story P11-4.2)
    # =========================================================================

    async def store_frame_embedding(
        self,
        db: Session,
        event_id: str,
        frame_index: int,
        embedding: list[float],
    ) -> str:
        """
        Store a single frame embedding in the database (Story P11-4.2).

        Args:
            db: SQLAlchemy database session
            event_id: UUID of the associated event
            frame_index: Index of the frame (0, 1, 2, ...)
            embedding: List of 512 floats

        Returns:
            ID of the created FrameEmbedding record
        """
        from app.models.frame_embedding import FrameEmbedding

        # Serialize embedding to JSON
        embedding_json = json.dumps(embedding)

        frame_embedding = FrameEmbedding(
            event_id=event_id,
            frame_index=frame_index,
            embedding=embedding_json,
            model_version=self.MODEL_VERSION,
        )

        db.add(frame_embedding)
        db.commit()
        db.refresh(frame_embedding)

        logger.debug(
            "Frame embedding stored",
            extra={
                "event_type": "frame_embedding_stored",
                "event_id": event_id,
                "frame_index": frame_index,
                "embedding_id": frame_embedding.id,
                "model_version": self.MODEL_VERSION,
            }
        )

        return frame_embedding.id

    async def store_frame_embeddings_batch(
        self,
        db: Session,
        event_id: str,
        embeddings: list[list[float]],
    ) -> list[str]:
        """
        Store multiple frame embeddings in a single transaction (Story P11-4.2).

        Args:
            db: SQLAlchemy database session
            event_id: UUID of the associated event
            embeddings: List of embeddings (index in list = frame_index)

        Returns:
            List of IDs of the created FrameEmbedding records
        """
        from app.models.frame_embedding import FrameEmbedding

        start_time = time.time()
        frame_embedding_ids = []

        for frame_index, embedding in enumerate(embeddings):
            embedding_json = json.dumps(embedding)

            frame_embedding = FrameEmbedding(
                event_id=event_id,
                frame_index=frame_index,
                embedding=embedding_json,
                model_version=self.MODEL_VERSION,
            )

            db.add(frame_embedding)
            frame_embedding_ids.append(frame_embedding.id)

        db.commit()

        duration_ms = (time.time() - start_time) * 1000
        logger.debug(
            "Frame embeddings batch stored",
            extra={
                "event_type": "frame_embeddings_batch_stored",
                "event_id": event_id,
                "frame_count": len(embeddings),
                "duration_ms": duration_ms,
                "model_version": self.MODEL_VERSION,
            }
        )

        return frame_embedding_ids

    async def get_frame_embeddings(
        self,
        db: Session,
        event_id: str,
    ) -> list[dict]:
        """
        Get all frame embeddings for an event (Story P11-4.2).

        Args:
            db: SQLAlchemy database session
            event_id: UUID of the event

        Returns:
            List of dicts with frame_index and embedding vector, sorted by frame_index
        """
        from app.models.frame_embedding import FrameEmbedding

        embeddings = db.query(FrameEmbedding).filter(
            FrameEmbedding.event_id == event_id
        ).order_by(FrameEmbedding.frame_index).all()

        return [
            {
                "id": emb.id,
                "frame_index": emb.frame_index,
                "embedding": json.loads(emb.embedding),
                "model_version": emb.model_version,
            }
            for emb in embeddings
        ]

    async def delete_frame_embeddings(
        self,
        db: Session,
        event_id: str,
    ) -> int:
        """
        Delete all frame embeddings for an event (Story P11-4.2).

        Useful for regenerating embeddings after model upgrade.

        Args:
            db: SQLAlchemy database session
            event_id: UUID of the event

        Returns:
            Number of embeddings deleted
        """
        from app.models.frame_embedding import FrameEmbedding

        count = db.query(FrameEmbedding).filter(
            FrameEmbedding.event_id == event_id
        ).delete()

        db.commit()

        logger.debug(
            "Frame embeddings deleted",
            extra={
                "event_type": "frame_embeddings_deleted",
                "event_id": event_id,
                "deleted_count": count,
            }
        )

        return count


# Backward compatible thin getter (delegates to @singleton decorator)
def get_embedding_service() -> EmbeddingService:
    """
    Get the global EmbeddingService instance.

    Note: This is now a thin backward-compatible wrapper.
          New code should prefer EmbeddingService() directly.
    """
    return EmbeddingService()


def reset_embedding_service() -> None:
    """Reset the global EmbeddingService instance (for testing)."""
    EmbeddingService._reset_instance()


async def initialize_embedding_service() -> EmbeddingService:
    """
    Initialize the embedding service and optionally preload the model.

    This can be called during application startup to preload the CLIP model,
    reducing latency on the first embedding request.

    Returns:
        EmbeddingService instance
    """
    service = get_embedding_service()

    # Optionally preload the model (uncomment if desired)
    # await service._ensure_model_loaded()
    # logger.info("Embedding service model preloaded")

    return service
