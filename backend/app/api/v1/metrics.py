"""
Metrics API Endpoint

Exposes pipeline metrics for monitoring and observability.

Provides:
    - Queue depth (current events waiting)
    - Events processed (success/failure counts)
    - Processing time distribution (p50, p95, p99)
    - Pipeline errors by type
"""
from fastapi import APIRouter, HTTPException
from typing import Dict
import logging

from app.services.event_processor import get_event_processor

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/metrics",
    tags=["metrics"]
)


@router.get("", response_model=Dict)
async def get_metrics():
    """
    Get pipeline metrics

    Returns:
        JSON metrics data:
        {
            "queue_depth": int,
            "events_processed": {
                "success": int,
                "failure": int,
                "total": int
            },
            "processing_time_ms": {
                "p50": float,
                "p95": float,
                "p99": float
            },
            "pipeline_errors": {
                "error_type": count
            }
        }

    Example:
        GET /api/v1/metrics

        Response:
        {
            "queue_depth": 2,
            "events_processed": {
                "success": 142,
                "failure": 3,
                "total": 145
            },
            "processing_time_ms": {
                "p50": 2341.2,
                "p95": 4523.8,
                "p99": 4891.1
            },
            "pipeline_errors": {
                "ai_service_failed": 2,
                "event_storage_failed": 1
            }
        }
    """
    event_processor = get_event_processor()

    if event_processor is None:
        logger.warning("EventProcessor not initialized - returning zero metrics")
        return {
            "queue_depth": 0,
            "events_processed": {
                "success": 0,
                "failure": 0,
                "total": 0
            },
            "processing_time_ms": {
                "p50": 0.0,
                "p95": 0.0,
                "p99": 0.0
            },
            "pipeline_errors": {}
        }

    metrics = event_processor.get_metrics()

    logger.debug(f"Metrics requested: {metrics}")

    return metrics
