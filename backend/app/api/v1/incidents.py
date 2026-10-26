"""Read-only incident API: combined result for a multi-camera group."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.incident import Incident
from app.schemas.event import IncidentResponse
from app.services.incident_service import serialize_incident

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("/{incident_id}", response_model=IncidentResponse)
def get_incident(incident_id: str, db: Session = Depends(get_db)) -> IncidentResponse:
    """Incident by id (equals the members' correlation_group_id)."""
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return IncidentResponse(**serialize_incident(db, incident))
