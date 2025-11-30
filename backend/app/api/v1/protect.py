"""
UniFi Protect Controller CRUD API endpoints

Provides REST API for Protect controller configuration management:
- POST /protect/controllers - Add new controller
- GET /protect/controllers - List all controllers
- GET /protect/controllers/{id} - Get single controller
- PUT /protect/controllers/{id} - Update controller
- DELETE /protect/controllers/{id} - Delete controller
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import logging
import uuid
from datetime import datetime, timezone

from app.core.database import get_db
from app.models.protect_controller import ProtectController
from app.schemas.protect import (
    ProtectControllerCreate,
    ProtectControllerUpdate,
    ProtectControllerResponse,
    ProtectControllerSingleResponse,
    ProtectControllerListResponse,
    ProtectControllerDeleteResponse,
    MetaResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/protect", tags=["protect"])


def create_meta(count: int = None) -> MetaResponse:
    """Create a standard meta response object"""
    return MetaResponse(
        request_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        count=count
    )


@router.post("/controllers", response_model=ProtectControllerSingleResponse, status_code=status.HTTP_201_CREATED)
def create_controller(
    controller_data: ProtectControllerCreate,
    db: Session = Depends(get_db)
):
    """
    Add a new UniFi Protect controller

    Args:
        controller_data: Controller configuration from request body
        db: Database session

    Returns:
        Created controller object with { data, meta } format

    Raises:
        409: Controller with same name already exists
    """
    try:
        # Check for duplicate name
        existing = db.query(ProtectController).filter(ProtectController.name == controller_data.name).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Controller with name '{controller_data.name}' already exists"
            )

        # Create controller model (password will be auto-encrypted by model)
        controller = ProtectController(
            name=controller_data.name,
            host=controller_data.host,
            port=controller_data.port,
            username=controller_data.username,
            password=controller_data.password,
            verify_ssl=controller_data.verify_ssl,
        )

        # Save to database
        db.add(controller)
        db.commit()
        db.refresh(controller)

        logger.info(f"Protect controller created: {controller.id} ({controller.name})")

        return ProtectControllerSingleResponse(
            data=ProtectControllerResponse.model_validate(controller),
            meta=create_meta()
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create controller: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create controller"
        )


@router.get("/controllers", response_model=ProtectControllerListResponse)
def list_controllers(db: Session = Depends(get_db)):
    """
    List all UniFi Protect controllers

    Returns:
        List of all controllers with { data, meta } format
    """
    try:
        controllers = db.query(ProtectController).order_by(ProtectController.created_at.desc()).all()

        return ProtectControllerListResponse(
            data=[ProtectControllerResponse.model_validate(c) for c in controllers],
            meta=create_meta(count=len(controllers))
        )

    except Exception as e:
        logger.error(f"Failed to list controllers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve controllers"
        )


@router.get("/controllers/{controller_id}", response_model=ProtectControllerSingleResponse)
def get_controller(controller_id: str, db: Session = Depends(get_db)):
    """
    Get a single UniFi Protect controller by ID

    Args:
        controller_id: Controller UUID
        db: Database session

    Returns:
        Controller object with { data, meta } format

    Raises:
        404: Controller not found
    """
    try:
        controller = db.query(ProtectController).filter(ProtectController.id == controller_id).first()

        if not controller:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Controller with id '{controller_id}' not found"
            )

        return ProtectControllerSingleResponse(
            data=ProtectControllerResponse.model_validate(controller),
            meta=create_meta()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get controller {controller_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve controller"
        )


@router.put("/controllers/{controller_id}", response_model=ProtectControllerSingleResponse)
def update_controller(
    controller_id: str,
    controller_data: ProtectControllerUpdate,
    db: Session = Depends(get_db)
):
    """
    Update an existing UniFi Protect controller

    Args:
        controller_id: Controller UUID
        controller_data: Partial controller data to update
        db: Database session

    Returns:
        Updated controller object with { data, meta } format

    Raises:
        404: Controller not found
        409: New name conflicts with existing controller
    """
    try:
        controller = db.query(ProtectController).filter(ProtectController.id == controller_id).first()

        if not controller:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Controller with id '{controller_id}' not found"
            )

        # Check for name conflict if name is being updated
        if controller_data.name and controller_data.name != controller.name:
            existing = db.query(ProtectController).filter(
                ProtectController.name == controller_data.name,
                ProtectController.id != controller_id
            ).first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Controller with name '{controller_data.name}' already exists"
                )

        # Update only provided fields
        update_data = controller_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(controller, field, value)

        db.commit()
        db.refresh(controller)

        logger.info(f"Protect controller updated: {controller.id} ({controller.name})")

        return ProtectControllerSingleResponse(
            data=ProtectControllerResponse.model_validate(controller),
            meta=create_meta()
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update controller {controller_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update controller"
        )


@router.delete("/controllers/{controller_id}", response_model=ProtectControllerDeleteResponse)
def delete_controller(controller_id: str, db: Session = Depends(get_db)):
    """
    Delete a UniFi Protect controller

    This will also remove any cameras associated with this controller
    via the cascade delete relationship.

    Args:
        controller_id: Controller UUID
        db: Database session

    Returns:
        Delete confirmation with { data: { deleted: true }, meta } format

    Raises:
        404: Controller not found
    """
    try:
        controller = db.query(ProtectController).filter(ProtectController.id == controller_id).first()

        if not controller:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Controller with id '{controller_id}' not found"
            )

        controller_name = controller.name
        db.delete(controller)
        db.commit()

        logger.info(f"Protect controller deleted: {controller_id} ({controller_name})")

        return ProtectControllerDeleteResponse(
            data={"deleted": True},
            meta=create_meta()
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete controller {controller_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete controller"
        )
