"""
Licence plates on saved vehicles: status, list, add, remove.

Plates are stored only as keyed hashes (``entity_plate_service``); these
routes never return a plate or its hash. The plate in ``POST`` is hashed as
soon as it arrives and is not logged (it is a ``SecretStr``, so it is masked
in validation errors and reprs too).

All routes sit under ``/api/v1/context`` and need an authenticated user.
Adding or removing one plate needs operator or admin; clearing a vehicle's
plates, or every saved plate, needs admin.
"""
import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import require_admin, require_operator_or_admin
from app.models.recognized_entity import RecognizedEntity
from app.services import entity_plate_service as plates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/context", tags=["context"])

_REQUIRE_ADMIN = [Depends(require_admin())]
_REQUIRE_OPERATOR = [Depends(require_operator_or_admin())]

IdParam = Annotated[str, Path(min_length=1, max_length=128)]


class PlateItem(BaseModel):
    id: str
    entity_id: str
    source: str
    source_event_id: Optional[str] = None
    usable: bool = Field(description="False when saved with an older PLATE_HASH_SALT (cannot match)")
    created_at: Optional[str] = None


class PlatesResponse(BaseModel):
    entity_id: str
    plates: list[PlateItem]


class SetPlateRequest(BaseModel):
    plate: SecretStr = Field(
        min_length=2,
        max_length=20,
        description="The plate as written (spaces and dashes are ignored). Hashed at once; never stored or returned.",
    )


class SetPlateResponse(BaseModel):
    status: str
    plate: Optional[PlateItem] = None


class PlateStatusResponse(BaseModel):
    enabled: bool
    salt_configured: bool
    active: bool
    model_state: str
    veto_enabled: bool
    vehicles_with_plates: int
    saved_plates: int
    unusable_plates: int


class PlateDeleteResponse(BaseModel):
    deleted_count: int


def _vehicle_or_404(db: Session, entity_id: str) -> RecognizedEntity:
    entity = db.query(RecognizedEntity).filter(RecognizedEntity.id == entity_id).first()
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    if entity.entity_type != "vehicle":
        raise HTTPException(status_code=400, detail="Plates can only be saved on vehicles")
    return entity


@router.get("/plates/status", response_model=PlateStatusResponse)
async def get_plate_status(db: Session = Depends(get_db)):
    """Whether plate matching is configured and active (no plate data)."""
    return PlateStatusResponse(**plates.plate_status(db))


@router.get("/entities/{entity_id}/plates", response_model=PlatesResponse)
async def list_entity_plates(entity_id: IdParam, db: Session = Depends(get_db)):
    _vehicle_or_404(db, entity_id)
    rows = plates.list_plates(db, entity_id)
    return PlatesResponse(entity_id=entity_id, plates=[PlateItem(**plates.plate_to_dict(r)) for r in rows])


@router.post("/entities/{entity_id}/plates", response_model=SetPlateResponse, dependencies=_REQUIRE_OPERATOR)
async def add_entity_plate(request: SetPlateRequest, entity_id: IdParam, db: Session = Depends(get_db)):
    """Save a plate on this vehicle (stored as a keyed hash only)."""
    entity = _vehicle_or_404(db, entity_id)
    result = plates.set_plate(db, entity, request.plate.get_secret_value())
    if result.status == "invalid":
        raise HTTPException(status_code=422, detail=result.message)
    if result.status == "disabled":
        raise HTTPException(status_code=409, detail=result.message)
    if result.status not in ("enrolled", "already_enrolled"):
        raise HTTPException(status_code=400, detail=result.message or "Plate not saved")
    return SetPlateResponse(status=result.status, plate=PlateItem(**plates.plate_to_dict(result.plate)))


@router.delete(
    "/entities/{entity_id}/plates/{plate_id}",
    response_model=PlateDeleteResponse,
    dependencies=_REQUIRE_OPERATOR,
)
async def remove_entity_plate(plate_id: IdParam, entity_id: IdParam, db: Session = Depends(get_db)):
    _vehicle_or_404(db, entity_id)
    if not plates.remove_plate(db, entity_id, plate_id):
        raise HTTPException(status_code=404, detail="Plate not found")
    return PlateDeleteResponse(deleted_count=1)


@router.delete("/entities/{entity_id}/plates", response_model=PlateDeleteResponse, dependencies=_REQUIRE_ADMIN)
async def clear_entity_plates(entity_id: IdParam, db: Session = Depends(get_db)):
    _vehicle_or_404(db, entity_id)
    count = plates.clear_plates(db, entity_id)
    logger.info("Vehicle plates cleared via API", extra={"event_type": "entity_plates_cleared", "entity_id": entity_id, "count": count})
    return PlateDeleteResponse(deleted_count=count)


@router.delete("/plates", response_model=PlateDeleteResponse, dependencies=_REQUIRE_ADMIN)
async def delete_all_plates(db: Session = Depends(get_db)):
    """Privacy control: delete every saved plate hash."""
    count = plates.clear_plates(db, None)
    logger.info("All saved plates deleted via API", extra={"event_type": "entity_plates_deleted_all", "count": count})
    return PlateDeleteResponse(deleted_count=count)
