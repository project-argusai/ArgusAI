"""
UniFi Protect Controller CRUD API endpoints

Provides REST API for Protect controller configuration management:
- POST /protect/controllers - Add new controller
- GET /protect/controllers - List all controllers
- GET /protect/controllers/{id} - Get single controller
- PUT /protect/controllers/{id} - Update controller
- DELETE /protect/controllers/{id} - Delete controller
- POST /protect/controllers/test - Test connection with new credentials (Story P2-1.2)
- POST /protect/controllers/{id}/test - Test connection with existing controller (Story P2-1.2)
- POST /protect/controllers/{id}/connect - Connect to controller (Story P2-1.4)
- POST /protect/controllers/{id}/disconnect - Disconnect from controller (Story P2-1.4)
- GET /protect/controllers/{id}/cameras - Discover cameras from controller (Story P2-2.1)
- POST /protect/controllers/{id}/cameras/{camera_id}/enable - Enable camera for AI (Story P2-2.2)
- POST /protect/controllers/{id}/cameras/{camera_id}/disable - Disable camera for AI (Story P2-2.2)
- PUT /protect/controllers/{id}/cameras/{camera_id}/filters - Update camera filters (Story P2-2.3)
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import logging
import uuid
from datetime import datetime, timezone

from app.core.database import get_db
from app.models.protect_controller import ProtectController
from app.models.camera import Camera
from app.schemas.protect import (
    ProtectControllerCreate,
    ProtectControllerUpdate,
    ProtectControllerResponse,
    ProtectControllerSingleResponse,
    ProtectControllerListResponse,
    ProtectControllerDeleteResponse,
    ProtectControllerTest,
    ProtectTestResultData,
    ProtectTestResponse,
    ProtectConnectionStatusData,
    ProtectConnectionResponse,
    ProtectDiscoveredCamera,
    ProtectCameraDiscoveryMeta,
    ProtectCamerasResponse,
    ProtectCameraEnableRequest,
    ProtectCameraEnableData,
    ProtectCameraEnableResponse,
    ProtectCameraDisableData,
    ProtectCameraDisableResponse,
    ProtectCameraFiltersRequest,
    ProtectCameraFiltersData,
    ProtectCameraFiltersResponse,
    MetaResponse,
)
from app.services.protect_service import get_protect_service

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
async def update_controller(
    controller_id: str,
    controller_data: ProtectControllerUpdate,
    db: Session = Depends(get_db)
):
    """
    Update an existing UniFi Protect controller (Story P2-1.5)

    Supports partial updates - only provided fields are modified.
    If connection-related fields change (host, port, username, password, verify_ssl),
    the WebSocket connection is automatically reconnected.

    Args:
        controller_id: Controller UUID
        controller_data: Partial controller data to update (all fields optional)
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

        # Track if reconnection needed (connection-related fields changed)
        connection_fields = {"host", "port", "username", "password", "verify_ssl"}
        needs_reconnect = False
        was_connected = controller.is_connected

        # Update only provided fields (exclude_unset=True means None fields not in request are ignored)
        update_data = controller_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            # Check if this is a connection field that changed
            if field in connection_fields:
                current_value = getattr(controller, field)
                # For password, we need special handling since stored value is encrypted
                if field == "password":
                    # Password is provided - always trigger reconnect
                    needs_reconnect = True
                elif current_value != value:
                    needs_reconnect = True
            setattr(controller, field, value)

        db.commit()
        db.refresh(controller)

        logger.info(f"Protect controller updated: {controller.id} ({controller.name})")

        # Reconnect if connection-related fields changed and was previously connected
        if needs_reconnect and was_connected:
            logger.info(f"Connection fields changed, reconnecting controller {controller_id}")
            protect_service = get_protect_service()
            try:
                await protect_service.disconnect(controller_id)
                await protect_service.connect(controller)
            except Exception as e:
                logger.error(f"Failed to reconnect controller {controller_id}: {e}")
                # Update succeeded, but reconnect failed - don't fail the request
                # The connection status will reflect the error

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
async def delete_controller(controller_id: str, db: Session = Depends(get_db)):
    """
    Delete a UniFi Protect controller (Story P2-1.5)

    This will:
    1. Disconnect the WebSocket connection
    2. Disassociate Protect cameras (sets protect_controller_id = NULL)
    3. Delete the controller record

    Note: Cameras are disassociated rather than deleted to preserve historical events,
    as Event.camera_id has a NOT NULL constraint with CASCADE delete.

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

        # Step 1: Disconnect WebSocket first
        protect_service = get_protect_service()
        try:
            await protect_service.disconnect(controller_id)
            logger.info(f"Disconnected controller {controller_id} before deletion")
        except Exception as e:
            logger.warning(f"Failed to disconnect controller {controller_id}: {e}")
            # Continue with deletion even if disconnect fails

        # Step 2: Disassociate cameras from this controller
        # Note: We disassociate rather than delete to preserve historical events
        # (Event.camera_id is NOT NULL with CASCADE delete)
        camera_count = db.query(Camera).filter(
            Camera.protect_controller_id == controller_id
        ).update(
            {Camera.protect_controller_id: None},
            synchronize_session='fetch'
        )
        if camera_count > 0:
            logger.info(f"Disassociated {camera_count} cameras from controller {controller_id}")

        # Step 3: Delete the controller
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


# Story P2-1.2: Connection Test Endpoints

@router.post("/controllers/test", response_model=ProtectTestResponse)
async def test_controller_connection(test_data: ProtectControllerTest):
    """
    Test connection to a UniFi Protect controller with provided credentials.

    This endpoint does NOT save any data - it's a test-only operation.
    Use this before saving a new controller to verify connectivity.

    Args:
        test_data: Connection parameters (host, port, username, password, verify_ssl)

    Returns:
        Test result with success status, message, firmware_version (on success),
        and camera_count (on success) in { data, meta } format.

    Status Codes:
        200: Test completed (check data.success for result)
        401: Authentication failed
        502: SSL certificate error
        503: Host unreachable
        504: Connection timed out
    """
    protect_service = get_protect_service()

    result = await protect_service.test_connection(
        host=test_data.host,
        port=test_data.port,
        username=test_data.username,
        password=test_data.password,
        verify_ssl=test_data.verify_ssl
    )

    # Map error types to HTTP status codes
    if not result.success:
        if result.error_type == "auth_error":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=result.message
            )
        elif result.error_type == "ssl_error":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=result.message
            )
        elif result.error_type == "connection_error":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.message
            )
        elif result.error_type == "timeout":
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=result.message
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.message
            )

    return ProtectTestResponse(
        data=ProtectTestResultData(
            success=result.success,
            message=result.message,
            firmware_version=result.firmware_version,
            camera_count=result.camera_count
        ),
        meta=create_meta()
    )


@router.post("/controllers/{controller_id}/test", response_model=ProtectTestResponse)
async def test_existing_controller(controller_id: str, db: Session = Depends(get_db)):
    """
    Test connection to an existing UniFi Protect controller using stored credentials.

    This endpoint retrieves the controller from the database, decrypts the
    stored password, and tests the connection.

    Args:
        controller_id: Controller UUID
        db: Database session

    Returns:
        Test result with success status, message, firmware_version (on success),
        and camera_count (on success) in { data, meta } format.

    Raises:
        404: Controller not found
        401: Authentication failed
        502: SSL certificate error
        503: Host unreachable
        504: Connection timed out
    """
    # Load controller from database
    controller = db.query(ProtectController).filter(ProtectController.id == controller_id).first()

    if not controller:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Controller with id '{controller_id}' not found"
        )

    # Get decrypted password
    try:
        password = controller.get_decrypted_password()
    except Exception as e:
        logger.error(f"Failed to decrypt password for controller {controller_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to decrypt controller credentials"
        )

    protect_service = get_protect_service()

    result = await protect_service.test_connection(
        host=controller.host,
        port=controller.port,
        username=controller.username,
        password=password,
        verify_ssl=controller.verify_ssl
    )

    # Map error types to HTTP status codes
    if not result.success:
        if result.error_type == "auth_error":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=result.message
            )
        elif result.error_type == "ssl_error":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=result.message
            )
        elif result.error_type == "connection_error":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.message
            )
        elif result.error_type == "timeout":
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=result.message
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.message
            )

    return ProtectTestResponse(
        data=ProtectTestResultData(
            success=result.success,
            message=result.message,
            firmware_version=result.firmware_version,
            camera_count=result.camera_count
        ),
        meta=create_meta()
    )


# Story P2-1.4: Connection Management Endpoints

@router.post("/controllers/{controller_id}/connect", response_model=ProtectConnectionResponse)
async def connect_controller(controller_id: str, db: Session = Depends(get_db)):
    """
    Connect to a UniFi Protect controller (AC10).

    Establishes a persistent WebSocket connection to the controller and
    starts a background listener for real-time events.

    Args:
        controller_id: Controller UUID
        db: Database session

    Returns:
        Connection status with { data: { controller_id, status }, meta } format.

    Raises:
        404: Controller not found
        503: Connection failed (unreachable, auth error, SSL error)
    """
    # Load controller from database
    controller = db.query(ProtectController).filter(ProtectController.id == controller_id).first()

    if not controller:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Controller with id '{controller_id}' not found"
        )

    protect_service = get_protect_service()

    try:
        success = await protect_service.connect(controller)

        if not success:
            # Connection failed - get error from database
            db.refresh(controller)
            error_msg = controller.last_error or "Connection failed"

            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=error_msg
            )

        return ProtectConnectionResponse(
            data=ProtectConnectionStatusData(
                controller_id=controller_id,
                status="connected",
                error=None
            ),
            meta=create_meta()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to connect controller {controller_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Connection failed: {type(e).__name__}"
        )


@router.post("/controllers/{controller_id}/disconnect", response_model=ProtectConnectionResponse)
async def disconnect_controller(controller_id: str, db: Session = Depends(get_db)):
    """
    Disconnect from a UniFi Protect controller (AC10).

    Closes the WebSocket connection and cancels the background listener task.

    Args:
        controller_id: Controller UUID
        db: Database session

    Returns:
        Disconnection status with { data: { controller_id, status }, meta } format.

    Raises:
        404: Controller not found
    """
    # Verify controller exists
    controller = db.query(ProtectController).filter(ProtectController.id == controller_id).first()

    if not controller:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Controller with id '{controller_id}' not found"
        )

    protect_service = get_protect_service()

    try:
        await protect_service.disconnect(controller_id)

        return ProtectConnectionResponse(
            data=ProtectConnectionStatusData(
                controller_id=controller_id,
                status="disconnected",
                error=None
            ),
            meta=create_meta()
        )

    except Exception as e:
        logger.error(f"Failed to disconnect controller {controller_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Disconnect failed: {type(e).__name__}"
        )


# Story P2-2.1: Camera Discovery Endpoint

@router.get("/controllers/{controller_id}/cameras", response_model=ProtectCamerasResponse)
async def discover_cameras(
    controller_id: str,
    force_refresh: bool = False,
    db: Session = Depends(get_db)
):
    """
    Discover cameras from a connected UniFi Protect controller (Story P2-2.1).

    Returns a list of all cameras available on the specified controller,
    including metadata like type, model, online status, and smart detection
    capabilities. Results are cached for 60 seconds.

    Args:
        controller_id: Controller UUID
        force_refresh: If True, bypass cache and fetch fresh data
        db: Database session (for cross-referencing enabled cameras)

    Returns:
        Camera list with { data: [...], meta } format where meta includes:
        - count: Number of cameras discovered
        - controller_id: The queried controller ID
        - cached: Whether results came from cache
        - cached_at: Cache timestamp (if cached)
        - warning: Warning message if any issues occurred

    Note:
        - Results are NOT auto-saved to cameras table (AC3)
        - is_enabled_for_ai is true for cameras already in the cameras table
        - Cache TTL is 60 seconds (AC4)
        - On discovery failure, cached results returned if available (AC8)

    Raises:
        404: Controller not found
        503: Controller not connected and no cached results available
    """
    # Verify controller exists
    controller = db.query(ProtectController).filter(ProtectController.id == controller_id).first()

    if not controller:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Controller with id '{controller_id}' not found"
        )

    logger.info(
        f"Camera discovery requested for controller {controller_id}",
        extra={
            "event_type": "protect_camera_discovery_api_start",
            "controller_id": controller_id,
            "force_refresh": force_refresh
        }
    )

    protect_service = get_protect_service()

    # Discover cameras using the service
    result = await protect_service.discover_cameras(controller_id, force_refresh=force_refresh)

    # Cross-reference with cameras table to set is_enabled_for_ai, smart_detection_types, and is_new
    # Story P2-2.3: Also include configured filters for enabled cameras
    # Story P2-2.4 AC11: Mark cameras as "new" if they've never been in our database
    import json as json_lib

    enabled_cameras_map = {}  # protect_camera_id -> Camera record
    known_camera_ids = set()  # All protect_camera_ids we've ever seen (enabled or not)

    if result.cameras:
        # Query cameras table for existing Protect cameras linked to this controller
        # First get enabled cameras for filters
        existing_cameras = db.query(Camera).filter(
            Camera.protect_controller_id == controller_id,
            Camera.protect_camera_id.isnot(None),
            Camera.is_enabled == True
        ).all()
        enabled_cameras_map = {c.protect_camera_id: c for c in existing_cameras}

        # Query ALL cameras that have ever been added for this controller (AC11)
        # This includes both enabled and disabled cameras to determine "is_new"
        all_known_cameras = db.query(Camera.protect_camera_id).filter(
            Camera.protect_controller_id == controller_id,
            Camera.protect_camera_id.isnot(None)
        ).all()
        known_camera_ids = {c.protect_camera_id for c in all_known_cameras}

        logger.debug(
            f"Found {len(enabled_cameras_map)} enabled cameras, {len(known_camera_ids)} known cameras for controller {controller_id}",
            extra={
                "event_type": "protect_camera_discovery_cross_reference",
                "controller_id": controller_id,
                "enabled_count": len(enabled_cameras_map),
                "known_count": len(known_camera_ids)
            }
        )

    # Transform to response schema with is_enabled_for_ai, smart_detection_types, and is_new set
    response_cameras = []
    for camera in result.cameras:
        # Set is_enabled_for_ai based on cross-reference (AC7)
        camera_record = enabled_cameras_map.get(camera.protect_camera_id)
        is_enabled = camera_record is not None

        # Story P2-2.3: Include smart_detection_types for enabled cameras
        smart_detection_types = None
        if camera_record and camera_record.smart_detection_types:
            try:
                smart_detection_types = json_lib.loads(camera_record.smart_detection_types)
            except (json_lib.JSONDecodeError, TypeError):
                smart_detection_types = None

        # Story P2-2.4 AC11: Mark as "new" if never been in database
        is_new = camera.protect_camera_id not in known_camera_ids

        response_cameras.append(ProtectDiscoveredCamera(
            protect_camera_id=camera.protect_camera_id,
            name=camera.name,
            type=camera.type,
            model=camera.model,
            is_online=camera.is_online,
            is_doorbell=camera.is_doorbell,
            is_enabled_for_ai=is_enabled,
            smart_detection_capabilities=camera.smart_detection_capabilities,
            smart_detection_types=smart_detection_types,
            is_new=is_new
        ))

    # Check if we should return 503 (no cameras and no cache due to not connected)
    if not result.cameras and result.warning and "not connected" in result.warning.lower():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=result.warning
        )

    # Build response with meta (AC6)
    response = ProtectCamerasResponse(
        data=response_cameras,
        meta=ProtectCameraDiscoveryMeta(
            count=len(response_cameras),
            controller_id=controller_id,
            cached=result.cached,
            cached_at=result.cached_at,
            warning=result.warning
        )
    )

    logger.info(
        f"Camera discovery completed for controller {controller_id}",
        extra={
            "event_type": "protect_camera_discovery_api_complete",
            "controller_id": controller_id,
            "camera_count": len(response_cameras),
            "cached": result.cached,
            "has_warning": result.warning is not None
        }
    )

    return response


# Story P2-2.2: Camera Enable/Disable Endpoints

@router.post(
    "/controllers/{controller_id}/cameras/{camera_id}/enable",
    response_model=ProtectCameraEnableResponse,
    status_code=status.HTTP_201_CREATED
)
async def enable_camera(
    controller_id: str,
    camera_id: str,
    request: ProtectCameraEnableRequest = None,
    db: Session = Depends(get_db)
):
    """
    Enable a discovered camera for AI analysis (Story P2-2.2, AC6)

    Creates a camera record in the database with source_type='protect'.
    If the camera already exists, updates it to enabled.

    Args:
        controller_id: The controller UUID
        camera_id: The Protect camera ID (protect_camera_id)
        request: Optional request body with name override and smart detection types
        db: Database session

    Returns:
        ProtectCameraEnableResponse with camera data and meta

    Raises:
        404: Controller not found
        400: Camera not found in discovered cameras
    """
    # Default request if none provided
    if request is None:
        request = ProtectCameraEnableRequest()

    logger.info(
        f"Enabling camera {camera_id} for controller {controller_id}",
        extra={
            "event_type": "protect_camera_enable_start",
            "controller_id": controller_id,
            "protect_camera_id": camera_id
        }
    )

    # Verify controller exists
    controller = db.query(ProtectController).filter(ProtectController.id == controller_id).first()
    if not controller:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Controller with id '{controller_id}' not found"
        )

    # Get discovered cameras to validate camera_id and get camera info
    protect_service = get_protect_service()
    discovery_result = await protect_service.discover_cameras(controller_id)

    # Find the camera in discovered list
    discovered_camera = None
    for cam in discovery_result.cameras:
        if cam.protect_camera_id == camera_id:
            discovered_camera = cam
            break

    if not discovered_camera:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Camera with id '{camera_id}' not found in discovered cameras"
        )

    # Check if camera already exists in database
    existing_camera = db.query(Camera).filter(
        Camera.protect_controller_id == controller_id,
        Camera.protect_camera_id == camera_id
    ).first()

    import json

    if existing_camera:
        # Update existing camera to enabled
        existing_camera.is_enabled = True
        existing_camera.smart_detection_types = json.dumps(request.smart_detection_types)
        if request.name:
            existing_camera.name = request.name
        db.commit()
        db.refresh(existing_camera)
        camera_record = existing_camera

        logger.info(
            f"Updated existing camera {camera_id} to enabled",
            extra={
                "event_type": "protect_camera_enable_updated",
                "controller_id": controller_id,
                "protect_camera_id": camera_id,
                "camera_id": existing_camera.id
            }
        )
    else:
        # Create new camera record (AC6)
        camera_name = request.name or discovered_camera.name
        camera_record = Camera(
            name=camera_name,
            type='rtsp',  # Required field - Protect cameras are effectively RTSP
            source_type='protect',
            protect_controller_id=controller_id,
            protect_camera_id=camera_id,
            protect_camera_type=discovered_camera.type,
            is_doorbell=discovered_camera.is_doorbell,
            smart_detection_types=json.dumps(request.smart_detection_types),
            is_enabled=True,
            motion_enabled=True,  # Default to motion enabled
        )
        db.add(camera_record)
        db.commit()
        db.refresh(camera_record)

        logger.info(
            f"Created new camera record for {camera_id}",
            extra={
                "event_type": "protect_camera_enable_created",
                "controller_id": controller_id,
                "protect_camera_id": camera_id,
                "camera_id": camera_record.id
            }
        )

    # Clear discovery cache to reflect new is_enabled_for_ai state
    protect_service.clear_camera_cache(controller_id)

    # Build response
    return ProtectCameraEnableResponse(
        data=ProtectCameraEnableData(
            camera_id=camera_record.id,
            protect_camera_id=camera_id,
            name=camera_record.name,
            is_enabled_for_ai=True,
            smart_detection_types=request.smart_detection_types
        ),
        meta=create_meta()
    )


@router.post(
    "/controllers/{controller_id}/cameras/{camera_id}/disable",
    response_model=ProtectCameraDisableResponse
)
async def disable_camera(
    controller_id: str,
    camera_id: str,
    db: Session = Depends(get_db)
):
    """
    Disable a camera from AI analysis (Story P2-2.2, AC7)

    Sets the camera record to disabled without deleting it.
    This preserves settings for future re-enabling.

    Args:
        controller_id: The controller UUID
        camera_id: The Protect camera ID (protect_camera_id)
        db: Database session

    Returns:
        ProtectCameraDisableResponse with camera data and meta

    Raises:
        404: Controller or camera not found
    """
    logger.info(
        f"Disabling camera {camera_id} for controller {controller_id}",
        extra={
            "event_type": "protect_camera_disable_start",
            "controller_id": controller_id,
            "protect_camera_id": camera_id
        }
    )

    # Verify controller exists
    controller = db.query(ProtectController).filter(ProtectController.id == controller_id).first()
    if not controller:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Controller with id '{controller_id}' not found"
        )

    # Find camera in database
    camera = db.query(Camera).filter(
        Camera.protect_controller_id == controller_id,
        Camera.protect_camera_id == camera_id
    ).first()

    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera with id '{camera_id}' not found or not enabled"
        )

    # Disable camera (AC7 - keep record, just mark disabled)
    camera.is_enabled = False
    db.commit()

    logger.info(
        f"Disabled camera {camera_id}",
        extra={
            "event_type": "protect_camera_disable_complete",
            "controller_id": controller_id,
            "protect_camera_id": camera_id,
            "camera_id": camera.id
        }
    )

    # Clear discovery cache to reflect new is_enabled_for_ai state
    protect_service = get_protect_service()
    protect_service.clear_camera_cache(controller_id)

    # Build response
    return ProtectCameraDisableResponse(
        data=ProtectCameraDisableData(
            protect_camera_id=camera_id,
            is_enabled_for_ai=False
        ),
        meta=create_meta()
    )


@router.put(
    "/controllers/{controller_id}/cameras/{camera_id}/filters",
    response_model=ProtectCameraFiltersResponse
)
async def update_camera_filters(
    controller_id: str,
    camera_id: str,
    request: ProtectCameraFiltersRequest,
    db: Session = Depends(get_db)
):
    """
    Update camera event type filters (Story P2-2.3, AC6, AC7)

    Updates the smart_detection_types for an enabled camera.
    Settings persist across app restarts.

    Args:
        controller_id: The controller UUID
        camera_id: The Protect camera ID (protect_camera_id)
        request: The filter configuration
        db: Database session

    Returns:
        ProtectCameraFiltersResponse with updated camera data and meta

    Raises:
        404: Controller or camera not found
        422: Invalid filter types
    """
    logger.info(
        f"Updating filters for camera {camera_id} on controller {controller_id}",
        extra={
            "event_type": "protect_camera_filters_update_start",
            "controller_id": controller_id,
            "protect_camera_id": camera_id,
            "filters": request.smart_detection_types
        }
    )

    # Verify controller exists
    controller = db.query(ProtectController).filter(ProtectController.id == controller_id).first()
    if not controller:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Controller with id '{controller_id}' not found"
        )

    # Find camera in database
    camera = db.query(Camera).filter(
        Camera.protect_controller_id == controller_id,
        Camera.protect_camera_id == camera_id
    ).first()

    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera with id '{camera_id}' not found or not enabled"
        )

    # Update smart_detection_types (AC6 - persist in database)
    import json
    camera.smart_detection_types = json.dumps(request.smart_detection_types)
    db.commit()
    db.refresh(camera)

    logger.info(
        f"Updated filters for camera {camera_id}",
        extra={
            "event_type": "protect_camera_filters_update_complete",
            "controller_id": controller_id,
            "protect_camera_id": camera_id,
            "camera_id": camera.id,
            "smart_detection_types": request.smart_detection_types
        }
    )

    # Clear discovery cache to reflect updated filters
    protect_service = get_protect_service()
    protect_service.clear_camera_cache(controller_id)

    # Build response (AC7)
    return ProtectCameraFiltersResponse(
        data=ProtectCameraFiltersData(
            protect_camera_id=camera_id,
            name=camera.name,
            smart_detection_types=request.smart_detection_types,
            is_enabled_for_ai=camera.is_enabled
        ),
        meta=create_meta()
    )
