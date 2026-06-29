"""
Voice Query API endpoints (Story P4-6.3)

Provides natural language query interface for voice assistants.
"""
import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.camera import Camera
from app.schemas.types import iso_utc
from app.services.voice_query_service import VoiceQueryService
from app.services.service_container import container

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


class VoiceQueryRequest(BaseModel):
    """Request model for voice query endpoint."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Natural language query",
        examples=["What's happening at the front door?", "Any activity this morning?"],
    )
    camera_id: Optional[str] = Field(
        default=None,
        description="Optional camera ID to filter results",
    )


class TimeRangeResponse(BaseModel):
    """Time range information in response."""

    start: str = Field(..., description="Start time ISO format")
    end: str = Field(..., description="End time ISO format")
    description: str = Field(..., description="Human-readable time description")


class VoiceQueryResponse(BaseModel):
    """Response model for voice query endpoint."""

    response: str = Field(
        ...,
        description="Natural language response optimized for TTS",
    )
    events_found: int = Field(
        ...,
        description="Number of events matching the query",
    )
    time_range: TimeRangeResponse = Field(
        ...,
        description="Parsed time range from query",
    )
    cameras_involved: list[str] = Field(
        default_factory=list,
        description="Names of cameras with matching events",
    )


class VoiceQueryError(BaseModel):
    """Error response model."""

    error: str = Field(..., description="Error message in spoken format")
    suggestion: Optional[str] = Field(
        default=None,
        description="Suggestion for how to rephrase the query",
    )


@router.post(
    "/query",
    response_model=VoiceQueryResponse,
    responses={
        400: {"model": VoiceQueryError, "description": "Invalid query"},
        500: {"model": VoiceQueryError, "description": "Server error"},
    },
    summary="Process natural language query",
    description="""
    Process a natural language query about security events and return
    a TTS-friendly spoken response.

    **Example queries:**
    - "What's happening at the front door?"
    - "Any activity this morning?"
    - "Was there anyone at the back yard in the last hour?"
    - "What did the cameras see today?"

    **Time expressions supported:**
    - today, yesterday
    - this morning, this afternoon, this evening, tonight
    - last hour, last 2 hours, last 30 minutes
    - recently, just now

    **Camera matching:**
    - Cameras are matched by name (case-insensitive)
    - Synonyms supported: "front door" matches "Front Door Camera"
    - Use "all cameras" for no filter
    """,
)
async def voice_query(
    request: VoiceQueryRequest,
    db: Session = Depends(get_db),
) -> VoiceQueryResponse:
    """
    Process a natural language voice query about security events.

    Parses the query to extract time range and camera filter,
    fetches matching events, and generates a spoken response.
    """
    service = container.voice_query_service

    try:
        # Validate query
        query = request.query.strip()
        if not query:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Please ask a question about your cameras.",
                    "suggestion": "Try asking 'What happened today?' or 'Any activity at the front door?'",
                },
            )

        # Get available cameras
        cameras = db.query(Camera).filter(Camera.is_enabled == True).all()

        # If specific camera_id provided, validate it
        if request.camera_id:
            camera = db.query(Camera).filter(Camera.id == request.camera_id).first()
            if not camera:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "I couldn't find that camera.",
                        "suggestion": "Please check the camera ID and try again.",
                    },
                )

        # Parse the query
        parsed = service.parse_query(query, cameras)

        # Override camera filter if explicitly provided
        if request.camera_id:
            camera = db.query(Camera).filter(Camera.id == request.camera_id).first()
            parsed.camera_filter = request.camera_id
            parsed.camera_name = camera.name if camera else None

        # Execute the query
        result = service.execute_query(db, parsed)

        # Generate response
        response_text = service.generate_response(parsed, result)

        logger.info(
            f"Voice query processed: '{query[:50]}...' -> {result.count} events",
            extra={
                "query": query,
                "events_found": result.count,
                "time_range": parsed.time_range.description,
                "camera_filter": parsed.camera_name,
            },
        )

        return VoiceQueryResponse(
            response=response_text,
            events_found=result.count,
            time_range=TimeRangeResponse(
                start=iso_utc(parsed.time_range.start),
                end=iso_utc(parsed.time_range.end),
                description=parsed.time_range.description,
            ),
            cameras_involved=result.cameras_involved,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Voice query error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Sorry, I had trouble processing that request.",
                "suggestion": "Please try again in a moment.",
            },
        )


@router.get(
    "/help",
    response_model=Dict[str, Any],
    summary="Get voice query help",
    description="Returns help information about supported queries.",
)
async def voice_query_help() -> Dict[str, Any]:
    """
    Get help information about supported voice queries.

    Returns example queries and supported time expressions.
    """
    return {
        "example_queries": [
            "What's happening at the front door?",
            "Any activity this morning?",
            "Was there anyone at the back yard in the last hour?",
            "What did the cameras see today?",
            "Any packages delivered yesterday?",
        ],
        "time_expressions": {
            "today": "Since midnight",
            "yesterday": "Previous day",
            "this morning": "6 AM to 12 PM",
            "this afternoon": "12 PM to 6 PM",
            "this evening": "6 PM to 10 PM",
            "tonight": "6 PM to midnight",
            "last hour": "Past 60 minutes",
            "last N hours": "Past N hours (e.g., 'last 2 hours')",
            "last N minutes": "Past N minutes (e.g., 'last 30 minutes')",
        },
        "camera_matching": {
            "description": "Cameras are matched by name (case-insensitive)",
            "synonyms": [
                "'front door' matches 'Front Door Camera'",
                "'back yard' matches 'Backyard Camera'",
                "'garage' matches 'Garage Camera'",
            ],
        },
        "tips": [
            "Be specific about time to get more relevant results",
            "Mention camera name for filtered results",
            "Ask 'all cameras' to see everything",
        ],
    }
