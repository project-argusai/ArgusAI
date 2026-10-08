"""
Entity reference galleries: list, enroll ("use as reference"), remove, reset.

A gallery is a set of small face or vehicle crops per entity that live
matching compares against (``entity_gallery_service``). Assigning an event
to an entity already enrolls its crop; these endpoints cover the cases that
need a choice (several crops on one event), clean-up, and re-enrollment.

All routes sit under ``/api/v1/context`` and need an authenticated user.
Changes need operator or admin; resetting a whole gallery needs admin.
"""
import logging
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import require_admin, require_operator_or_admin
from app.models.event import Event
from app.models.recognized_entity import RecognizedEntity
from app.services.entity_gallery_service import (
    FACE,
    VEHICLE,
    gallery_item_to_dict,
    get_entity_gallery_service,
    observation_to_dict,
    read_crop,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/context", tags=["context"])

_REQUIRE_ADMIN = [Depends(require_admin())]
_REQUIRE_OPERATOR = [Depends(require_operator_or_admin())]

# One Annotated alias per use; a shared Path() default would bind every
# parameter to the first one's name.
IdParam = Annotated[str, Path(min_length=1, max_length=128)]


class GalleryItem(BaseModel):
    id: str
    entity_id: str
    kind: str
    model_version: str
    dominant_color: Optional[str] = None
    source_event_id: Optional[str] = None
    source_observation_id: Optional[str] = None
    has_crop: bool
    created_at: Optional[str] = None


class GalleryResponse(BaseModel):
    entity_id: str
    items: list[GalleryItem]


class ObservationItem(BaseModel):
    id: str
    kind: str
    event_id: str
    bounding_box: Optional[dict] = None
    confidence: Optional[float] = None
    model_version: str
    dominant_color: Optional[str] = None
    vehicle_type: Optional[str] = None
    has_crop: bool
    created_at: Optional[str] = None


class ObservationsResponse(BaseModel):
    event_id: str
    observations: list[ObservationItem]


class EnrollRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=128)
    observation_id: Optional[str] = Field(
        default=None,
        max_length=128,
        description="A specific crop from GET /context/events/{event_id}/observations. "
        "Omit to let the server pick (refused as 'ambiguous' when several crops fit).",
    )


class EnrollResponse(BaseModel):
    status: str
    message: Optional[str] = None
    items: list[GalleryItem] = Field(default_factory=list)
    candidates: list[ObservationItem] = Field(default_factory=list)


class GalleryDeleteResponse(BaseModel):
    deleted_count: int


def _entity_or_404(db: Session, entity_id: str) -> RecognizedEntity:
    entity = db.query(RecognizedEntity).filter(RecognizedEntity.id == entity_id).first()
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


def _jpeg(data: Optional[bytes]) -> Response:
    if not data:
        raise HTTPException(status_code=404, detail="Crop not found")
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/entities/{entity_id}/gallery", response_model=GalleryResponse)
async def list_entity_gallery(entity_id: IdParam, db: Session = Depends(get_db)):
    """Reference crops enrolled for this entity, newest first."""
    _entity_or_404(db, entity_id)
    items = get_entity_gallery_service().list_items(db, entity_id)
    return GalleryResponse(entity_id=entity_id, items=[GalleryItem(**gallery_item_to_dict(i)) for i in items])


@router.post("/entities/{entity_id}/gallery", response_model=EnrollResponse, dependencies=_REQUIRE_OPERATOR)
async def enroll_entity_reference(
    request: EnrollRequest,
    entity_id: IdParam,
    db: Session = Depends(get_db),
):
    """Use an event's face or vehicle crop as a reference for this entity.

    Does not link the event to the entity (use ``POST /context/events/{id}/entity``
    for that, which also enrolls automatically).
    """
    entity = _entity_or_404(db, entity_id)
    event_id = request.event_id.strip()
    if db.query(Event.id).filter(Event.id == event_id).first() is None:
        raise HTTPException(status_code=404, detail="Event not found")
    result = await get_entity_gallery_service().enroll_from_event(
        db, entity, event_id, observation_id=(request.observation_id or None)
    )
    return EnrollResponse(
        status=result.status,
        message=result.message or None,
        items=[GalleryItem(**gallery_item_to_dict(i)) for i in result.items],
        candidates=[ObservationItem(**c) for c in result.candidates],
    )


@router.delete(
    "/entities/{entity_id}/gallery/{item_id}",
    response_model=GalleryDeleteResponse,
    dependencies=_REQUIRE_OPERATOR,
)
async def remove_entity_reference(item_id: IdParam, entity_id: IdParam, db: Session = Depends(get_db)):
    """Remove one reference crop (e.g. a wrong or blurry one)."""
    _entity_or_404(db, entity_id)
    if not get_entity_gallery_service().remove_item(db, entity_id, item_id):
        raise HTTPException(status_code=404, detail="Gallery item not found")
    return GalleryDeleteResponse(deleted_count=1)


@router.delete("/entities/{entity_id}/gallery", response_model=GalleryDeleteResponse, dependencies=_REQUIRE_ADMIN)
async def reset_entity_gallery(
    entity_id: IdParam,
    kind: Optional[Literal["face", "vehicle"]] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Remove every reference crop of an entity, to re-enroll it from scratch."""
    _entity_or_404(db, entity_id)
    count = get_entity_gallery_service().reset_entity(db, entity_id, kind)
    logger.info(
        "Entity gallery reset via API",
        extra={"event_type": "entity_gallery_reset", "entity_id": entity_id, "count": count},
    )
    return GalleryDeleteResponse(deleted_count=count)


@router.get("/entities/{entity_id}/gallery/{item_id}/crop")
async def get_entity_reference_crop(item_id: IdParam, entity_id: IdParam, db: Session = Depends(get_db)):
    from app.models.entity_gallery_item import EntityGalleryItem

    item = db.query(EntityGalleryItem).filter(
        EntityGalleryItem.entity_id == entity_id, EntityGalleryItem.id == item_id
    ).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Gallery item not found")
    return _jpeg(read_crop(item.crop_path))


@router.get("/events/{event_id}/observations", response_model=ObservationsResponse)
async def list_event_observations(event_id: IdParam, db: Session = Depends(get_db)):
    """Face and vehicle crops stored for an event (candidates for enrollment)."""
    if db.query(Event.id).filter(Event.id == event_id).first() is None:
        raise HTTPException(status_code=404, detail="Event not found")
    rows = get_entity_gallery_service().event_observations(db, event_id)
    return ObservationsResponse(
        event_id=event_id,
        observations=[ObservationItem(**observation_to_dict(r, k)) for k, r in rows],
    )


@router.get("/observations/{kind}/{observation_id}/crop")
async def get_observation_crop(
    kind: Literal["face", "vehicle"],
    observation_id: IdParam,
    db: Session = Depends(get_db),
):
    row = get_entity_gallery_service().get_observation(db, FACE if kind == "face" else VEHICLE, observation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Observation not found")
    return _jpeg(read_crop(row.crop_path))
