"""
Camera CRUD API endpoints

Provides REST API for camera configuration management:
- POST /cameras - Create new camera
- GET /cameras - List all cameras
- GET /cameras/{id} - Get single camera
- PUT /cameras/{id} - Update camera
- DELETE /cameras/{id} - Delete camera
- POST /cameras/{id}/test - Test connection
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
import logging
import cv2
import base64
import numpy as np

try:
    import av
    PYAV_AVAILABLE = True
except ImportError:
    PYAV_AVAILABLE = False

from app.core.database import get_db
from app.models.camera import Camera
from app.schemas.camera import CameraCreate, CameraUpdate, CameraResponse, CameraTestResponse
from app.schemas.motion import (
    MotionConfigUpdate, MotionConfigResponse, MotionTestRequest, MotionTestResponse,
    DetectionZone, DetectionSchedule
)
from app.services.camera_service import CameraService
from app.services.motion_detection_service import motion_detection_service
from app.services.detection_zone_manager import detection_zone_manager
from app.services.event_processor import get_event_processor, ProcessingEvent
from app.services.protect_service import get_protect_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cameras", tags=["cameras"])

# Global camera service instance (singleton)
camera_service = CameraService()


@router.post("", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
def create_camera(
    camera_data: CameraCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new camera and start capture thread

    Args:
        camera_data: Camera configuration from request body
        db: Database session

    Returns:
        Created camera object

    Raises:
        409: Camera with same name already exists
        400: Validation error or failed to start camera
    """
    try:
        # Check for duplicate name
        existing = db.query(Camera).filter(Camera.name == camera_data.name).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Camera with name '{camera_data.name}' already exists"
            )

        # Create camera model
        camera = Camera(
            name=camera_data.name,
            type=camera_data.type,
            rtsp_url=camera_data.rtsp_url,
            username=camera_data.username,
            password=camera_data.password,  # Will be auto-encrypted by model
            device_index=camera_data.device_index,
            frame_rate=camera_data.frame_rate,
            is_enabled=camera_data.is_enabled,
            motion_sensitivity=camera_data.motion_sensitivity,
            motion_cooldown=camera_data.motion_cooldown
        )

        # Save to database
        db.add(camera)
        db.commit()
        db.refresh(camera)

        # Start camera capture thread if enabled
        if camera.is_enabled:
            success = camera_service.start_camera(camera)
            if not success:
                logger.warning(f"Camera {camera.id} created but failed to start capture thread")

        logger.info(f"Camera created: {camera.id} ({camera.name})")

        return camera

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create camera: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create camera"
        )


@router.get("", response_model=List[CameraResponse])
def list_cameras(
    is_enabled: bool = None,
    db: Session = Depends(get_db)
):
    """
    List all cameras with optional filtering

    Args:
        is_enabled: Optional filter by enabled status
        db: Database session

    Returns:
        List of camera objects
    """
    try:
        query = db.query(Camera)

        if is_enabled is not None:
            query = query.filter(Camera.is_enabled == is_enabled)

        cameras = query.all()

        return cameras

    except Exception as e:
        logger.error(f"Failed to list cameras: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve cameras"
        )


@router.get("/{camera_id}", response_model=CameraResponse)
def get_camera(
    camera_id: str,
    db: Session = Depends(get_db)
):
    """
    Get single camera by ID

    Args:
        camera_id: UUID of camera
        db: Database session

    Returns:
        Camera object

    Raises:
        404: Camera not found
    """
    try:
        camera = db.query(Camera).filter(Camera.id == camera_id).first()

        if not camera:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Camera {camera_id} not found"
            )

        return camera

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get camera {camera_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve camera"
        )


@router.put("/{camera_id}", response_model=CameraResponse)
def update_camera(
    camera_id: str,
    camera_data: CameraUpdate,
    db: Session = Depends(get_db)
):
    """
    Update existing camera configuration

    Args:
        camera_id: UUID of camera to update
        camera_data: Fields to update
        db: Database session

    Returns:
        Updated camera object

    Raises:
        404: Camera not found
        400: Validation error
    """
    try:
        camera = db.query(Camera).filter(Camera.id == camera_id).first()

        if not camera:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Camera {camera_id} not found"
            )

        # Track if we need to restart camera
        was_enabled = camera.is_enabled
        restart_needed = False

        # Update fields
        update_data = camera_data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(camera, field, value)

            # Check if restart needed
            if field in ['rtsp_url', 'username', 'password', 'device_index', 'frame_rate']:
                restart_needed = True

        # Save changes
        db.commit()
        db.refresh(camera)

        # Handle camera thread lifecycle
        if restart_needed and camera.is_enabled:
            # Stop and restart camera
            camera_service.stop_camera(camera_id)
            camera_service.start_camera(camera)
        elif camera.is_enabled and not was_enabled:
            # Start camera (was disabled, now enabled)
            camera_service.start_camera(camera)
        elif not camera.is_enabled and was_enabled:
            # Stop camera (was enabled, now disabled)
            camera_service.stop_camera(camera_id)

        logger.info(f"Camera updated: {camera_id}")

        return camera

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update camera {camera_id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update camera"
        )


@router.delete("/{camera_id}", status_code=status.HTTP_200_OK)
def delete_camera(
    camera_id: str,
    db: Session = Depends(get_db)
):
    """
    Delete camera and stop capture thread

    Args:
        camera_id: UUID of camera to delete
        db: Database session

    Returns:
        Success confirmation

    Raises:
        404: Camera not found
    """
    try:
        camera = db.query(Camera).filter(Camera.id == camera_id).first()

        if not camera:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Camera {camera_id} not found"
            )

        # Stop capture thread if running
        camera_service.stop_camera(camera_id)

        # Delete from database
        db.delete(camera)
        db.commit()

        logger.info(f"Camera deleted: {camera_id} ({camera.name})")

        return {"deleted": True, "camera_id": camera_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete camera {camera_id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete camera"
        )


@router.post("/{camera_id}/reconnect")
def reconnect_camera(
    camera_id: str,
    db: Session = Depends(get_db)
):
    """
    Force reconnect a camera (stop and restart capture)

    Args:
        camera_id: UUID of camera to reconnect
        db: Database session

    Returns:
        Success status and message

    Raises:
        404: Camera not found
        400: Camera is disabled
    """
    import time

    try:
        camera = db.query(Camera).filter(Camera.id == camera_id).first()

        if not camera:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Camera {camera_id} not found"
            )

        if not camera.is_enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Camera {camera_id} is disabled. Enable it first."
            )

        # Stop camera if running
        camera_service.stop_camera(camera_id)
        time.sleep(0.5)

        # Try to verify connection with PyAV before starting capture thread
        # This helps with intermittent network issues
        try:
            import av
            connection_str = camera_service._build_rtsp_url(camera)
            if connection_str.startswith("rtsps://"):
                logger.info(f"Testing PyAV connection for camera {camera_id}")
                container = av.open(connection_str, options={'rtsp_transport': 'tcp'}, timeout=10)
                stream = container.streams.video[0]
                # Get one frame to verify
                for frame in container.decode(stream):
                    logger.info(f"PyAV test successful: {stream.codec_context.width}x{stream.codec_context.height}")
                    break
                container.close()
        except Exception as e:
            logger.warning(f"PyAV pre-test failed: {e}")
            # Continue anyway - the capture thread will retry

        # Start camera
        success = camera_service.start_camera(camera)

        if success:
            logger.info(f"Camera {camera_id} reconnect initiated")
            return {"success": True, "message": "Camera reconnect initiated"}
        else:
            return {"success": False, "message": "Failed to start camera"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reconnect camera {camera_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reconnect camera: {str(e)}"
        )


@router.post("/{camera_id}/test", response_model=CameraTestResponse)
def test_camera_connection(
    camera_id: str,
    db: Session = Depends(get_db)
):
    """
    Test camera connection without starting persistent capture

    Args:
        camera_id: UUID of camera to test
        db: Database session

    Returns:
        Test result with success status and optional thumbnail

    Raises:
        404: Camera not found
    """
    try:
        camera = db.query(Camera).filter(Camera.id == camera_id).first()

        if not camera:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Camera {camera_id} not found"
            )

        # Build connection string
        if camera.type == "rtsp":
            # Build RTSP URL with credentials
            rtsp_url = camera.rtsp_url

            if camera.username:
                password = camera.get_decrypted_password() if camera.password else ""

                if "://" in rtsp_url:
                    protocol, rest = rtsp_url.split("://", 1)
                    creds = camera.username
                    if password:
                        creds += f":{password}"
                    rtsp_url = f"{protocol}://{creds}@{rest}"

            connection_str = rtsp_url

        elif camera.type == "usb":
            connection_str = camera.device_index
        else:
            return CameraTestResponse(
                success=False,
                message=f"Unknown camera type: {camera.type}"
            )

        # Attempt connection
        frame = None
        cap = None
        av_container = None

        # Use PyAV for secure RTSP (rtsps://) streams
        if camera.type == "rtsp" and PYAV_AVAILABLE and connection_str.startswith("rtsps://"):
            try:
                av_container = av.open(connection_str, options={'rtsp_transport': 'tcp'})
                av_stream = av_container.streams.video[0]
                for av_frame in av_container.decode(av_stream):
                    frame = av_frame.to_ndarray(format='bgr24')
                    break
                av_container.close()
            except Exception as e:
                if av_container:
                    av_container.close()
                return CameraTestResponse(
                    success=False,
                    message=f"Failed to connect to secure RTSP stream: {str(e)}"
                )
        else:
            # Use OpenCV for USB cameras and non-secure RTSP
            if camera.type == "rtsp":
                cap = cv2.VideoCapture(connection_str, cv2.CAP_FFMPEG)
            else:
                cap = cv2.VideoCapture(connection_str)
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000)  # 10 second timeout

            if not cap.isOpened():
                cap.release()

                # USB-specific error message
                if camera.type == "usb":
                    return CameraTestResponse(
                        success=False,
                        message=f"USB camera not found at device index {camera.device_index}. Check that camera is connected."
                    )
                else:
                    return CameraTestResponse(
                        success=False,
                        message="Failed to connect to camera. Check IP address, port, and network connectivity."
                    )

            # Try to read a test frame
            ret, frame = cap.read()
            cap.release()

            if not ret or frame is None:
                return CameraTestResponse(
                    success=False,
                    message="Connected to camera but failed to capture frame. Check camera stream format."
                )

        # Generate thumbnail
        try:
            # Resize frame to thumbnail size
            thumbnail_height = 240
            aspect_ratio = frame.shape[1] / frame.shape[0]
            thumbnail_width = int(thumbnail_height * aspect_ratio)

            thumbnail = cv2.resize(frame, (thumbnail_width, thumbnail_height))

            # Encode as JPEG
            _, buffer = cv2.imencode('.jpg', thumbnail)

            # Convert to base64
            thumbnail_b64 = base64.b64encode(buffer).decode('utf-8')

            if cap is not None:
                cap.release()

            # Type-specific success message
            if camera.type == "usb":
                success_msg = f"USB camera connected successfully (device {camera.device_index})"
            else:
                success_msg = "Connection successful"

            return CameraTestResponse(
                success=True,
                message=success_msg,
                thumbnail=f"data:image/jpeg;base64,{thumbnail_b64}"
            )

        except Exception as e:
            logger.error(f"Failed to generate thumbnail: {e}")
            if cap is not None:
                cap.release()

            return CameraTestResponse(
                success=True,
                message="Connection successful (thumbnail generation failed)"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Camera test failed: {e}", exc_info=True)

        # Try to determine error type
        error_str = str(e).lower()

        # USB-specific errors
        if camera.type == "usb":
            if "permission" in error_str or "denied" in error_str:
                message = (
                    f"Permission denied for USB camera at device index {camera.device_index}. "
                    "On Linux, add user to 'video' group: sudo usermod -a -G video $USER"
                )
            elif "busy" in error_str or "in use" in error_str:
                message = (
                    f"USB camera at device index {camera.device_index} is already in use by another application. "
                    "Close other apps using the camera and try again."
                )
            else:
                message = f"USB camera connection failed: {str(e)}"
        # RTSP-specific errors
        elif "401" in error_str or "authentication" in error_str or "unauthorized" in error_str:
            message = "Authentication failed. Check username and password."
        elif "timeout" in error_str or "timed out" in error_str:
            message = "Connection timeout. Check IP address and network connectivity."
        elif "refused" in error_str:
            message = "Connection refused. Check port number and camera RTSP service."
        else:
            message = f"Connection failed: {str(e)}"

        return CameraTestResponse(
            success=False,
            message=message
        )


# ============================================================================
# Motion Configuration Endpoints (F2.1)
# ============================================================================

@router.put("/{camera_id}/motion/config", response_model=CameraResponse)
def update_motion_config(
    camera_id: str,
    config: MotionConfigUpdate,
    db: Session = Depends(get_db)
):
    """
    Update motion detection configuration for camera

    Args:
        camera_id: UUID of camera
        config: Motion configuration updates
        db: Database session

    Returns:
        Updated camera object with new motion config

    Raises:
        404: Camera not found
        422: Validation error

    Side Effects:
        - Reloads motion detector if algorithm changed
        - Configuration persists across restarts (AC-12)
    """
    try:
        camera = db.query(Camera).filter(Camera.id == camera_id).first()

        if not camera:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Camera {camera_id} not found"
            )

        # Track if algorithm changed
        algorithm_changed = False
        old_algorithm = camera.motion_algorithm

        # Update fields
        update_data = config.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(camera, field, value)

            if field == 'motion_algorithm' and value != old_algorithm:
                algorithm_changed = True

        # Save changes
        db.commit()
        db.refresh(camera)

        # Reload motion detector if algorithm changed
        if algorithm_changed:
            motion_detection_service.reload_config(camera_id, camera.motion_algorithm)
            logger.info(f"Motion detector reloaded for camera {camera_id}: {old_algorithm} -> {camera.motion_algorithm}")

        logger.info(f"Motion configuration updated for camera {camera_id}")

        return camera

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update motion config for camera {camera_id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update motion configuration"
        )


@router.get("/{camera_id}/motion/config", response_model=MotionConfigResponse)
def get_motion_config(
    camera_id: str,
    db: Session = Depends(get_db)
):
    """
    Get current motion detection configuration for camera

    Args:
        camera_id: UUID of camera
        db: Database session

    Returns:
        Motion configuration (enabled, sensitivity, cooldown, algorithm)

    Raises:
        404: Camera not found
    """
    try:
        camera = db.query(Camera).filter(Camera.id == camera_id).first()

        if not camera:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Camera {camera_id} not found"
            )

        return MotionConfigResponse(
            motion_enabled=camera.motion_enabled,
            motion_sensitivity=camera.motion_sensitivity,
            motion_cooldown=camera.motion_cooldown,
            motion_algorithm=camera.motion_algorithm
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get motion config for camera {camera_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get motion configuration"
        )


@router.post("/{camera_id}/motion/test", response_model=MotionTestResponse)
def test_motion_detection(
    camera_id: str,
    test_request: MotionTestRequest = None,
    db: Session = Depends(get_db)
):
    """
    Test motion detection on current frame (ephemeral, not saved to database)

    Args:
        camera_id: UUID of camera
        test_request: Optional overrides for sensitivity and algorithm
        db: Database session

    Returns:
        Motion test results with preview image

    Raises:
        404: Camera not found
        400: Camera not running or failed to capture frame

    Note:
        - Ephemeral: Results NOT saved to database (DECISION-4)
        - Rate limit: 10 requests/minute per camera (TODO: implement rate limiting)
    """
    try:
        camera = db.query(Camera).filter(Camera.id == camera_id).first()

        if not camera:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Camera {camera_id} not found"
            )

        # Check if camera is running
        camera_status = camera_service.get_camera_status(camera_id)
        if not camera_status or camera_status.get('status') != 'connected':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Camera {camera_id} is not currently running. Start camera first."
            )

        # Get current frame from camera service
        # NOTE: This is a simplified implementation
        # Real implementation would need to add a method to CameraService to get latest frame
        # For now, we'll attempt to capture a frame directly
        frame = None

        if camera.type == "rtsp":
            connection_str = camera_service._build_rtsp_url(camera)

            # Use PyAV for secure RTSP streams
            if PYAV_AVAILABLE and connection_str.startswith("rtsps://"):
                try:
                    av_container = av.open(connection_str, options={'rtsp_transport': 'tcp'})
                    av_stream = av_container.streams.video[0]
                    for av_frame in av_container.decode(av_stream):
                        frame = av_frame.to_ndarray(format='bgr24')
                        break
                    av_container.close()
                except Exception as e:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Failed to capture frame from secure RTSP stream: {str(e)}"
                    )
            else:
                cap = cv2.VideoCapture(connection_str, cv2.CAP_FFMPEG)
                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
                if not cap.isOpened():
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Failed to capture frame from camera"
                    )
                ret, frame = cap.read()
                cap.release()
                if not ret or frame is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Failed to read frame from camera"
                    )
        else:
            connection_str = camera.device_index
            cap = cv2.VideoCapture(connection_str)
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
            if not cap.isOpened():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to capture frame from camera"
                )
            ret, frame = cap.read()
            cap.release()
            if not ret or frame is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to read frame from camera"
                )

        # Use test overrides or camera defaults
        sensitivity = test_request.sensitivity if test_request and test_request.sensitivity else camera.motion_sensitivity
        algorithm = test_request.algorithm if test_request and test_request.algorithm else camera.motion_algorithm

        # Create temporary detector for test
        from app.services.motion_detector import MotionDetector
        temp_detector = MotionDetector(algorithm=algorithm)

        # Run motion detection
        motion_detected, confidence, bounding_box = temp_detector.detect_motion(frame, sensitivity)

        # Generate preview image with bounding box overlay
        preview_frame = frame.copy()

        if motion_detected and bounding_box:
            x, y, w, h = bounding_box
            cv2.rectangle(preview_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(
                preview_frame,
                f"Motion: {confidence:.2f}",
                (x, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                2
            )

        # Encode as JPEG and convert to base64
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
        ret, buffer = cv2.imencode('.jpg', preview_frame, encode_param)
        preview_b64 = base64.b64encode(buffer).decode('utf-8')

        logger.info(f"Motion test for camera {camera_id}: detected={motion_detected}, confidence={confidence:.3f}")

        return MotionTestResponse(
            motion_detected=motion_detected,
            confidence=confidence,
            bounding_box={
                "x": bounding_box[0],
                "y": bounding_box[1],
                "width": bounding_box[2],
                "height": bounding_box[3]
            } if bounding_box else None,
            preview_image=f"data:image/jpeg;base64,{preview_b64}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Motion test failed for camera {camera_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Motion test failed: {str(e)}"
        )


# ==================== Detection Zone Endpoints (F2.2) ====================


@router.get("/{camera_id}/zones", response_model=List[DetectionZone])
def get_camera_zones(
    camera_id: str,
    db: Session = Depends(get_db)
):
    """
    Get detection zones for a camera

    Args:
        camera_id: UUID of camera
        db: Database session

    Returns:
        List of DetectionZone objects (empty list if no zones configured)

    Raises:
        404: Camera not found
    """
    camera = db.query(Camera).filter(Camera.id == camera_id).first()

    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera {camera_id} not found"
        )

    # Parse detection zones JSON (return empty list if None)
    if not camera.detection_zones:
        return []

    try:
        import json
        zones = json.loads(camera.detection_zones)
        return zones
    except (json.JSONDecodeError, TypeError) as e:
        logger.error(f"Invalid detection_zones JSON for camera {camera_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid zone configuration in database"
        )


@router.put("/{camera_id}/zones", response_model=CameraResponse)
def update_camera_zones(
    camera_id: str,
    zones: List[DetectionZone],
    db: Session = Depends(get_db)
):
    """
    Update detection zones for a camera

    Args:
        camera_id: UUID of camera
        zones: List of DetectionZone objects
        db: Database session

    Returns:
        Updated camera object with new zones

    Raises:
        404: Camera not found
        422: Invalid zone configuration
    """
    camera = db.query(Camera).filter(Camera.id == camera_id).first()

    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera {camera_id} not found"
        )

    # Validate zones (Pydantic already validated, but double-check)
    if len(zones) > 10:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Maximum 10 zones allowed per camera"
        )

    # Serialize zones to JSON
    try:
        import json
        zones_dict = [zone.model_dump() for zone in zones]
        camera.detection_zones = json.dumps(zones_dict)

        db.commit()
        db.refresh(camera)

        logger.info(
            f"Updated detection zones for camera {camera_id}: "
            f"{len(zones)} zones configured"
        )

        return camera

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update zones for camera {camera_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update zones: {str(e)}"
        )


@router.post("/{camera_id}/zones/test")
def test_camera_zones(
    camera_id: str,
    test_zones: List[DetectionZone] = None,
    db: Session = Depends(get_db)
):
    """
    Test detection zones with current camera frame

    Args:
        camera_id: UUID of camera
        test_zones: Optional zones to test (uses camera's zones if not provided)
        db: Database session

    Returns:
        Preview image with zones overlay and motion detection result

    Raises:
        404: Camera not found
        500: No frame available or capture error
    """
    camera = db.query(Camera).filter(Camera.id == camera_id).first()

    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera {camera_id} not found"
        )

    # Get camera's active capture if running
    active_capture = camera_service._active_captures.get(camera_id)

    if not active_capture or not active_capture.isOpened():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Camera not running or no frame available. Start camera first."
        )

    # Capture current frame
    ret, frame = active_capture.read()

    if not ret or frame is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to capture frame from camera"
        )

    # Use test zones or camera's configured zones
    zones_to_test = test_zones if test_zones else []
    if not zones_to_test and camera.detection_zones:
        try:
            import json
            zones_dict = json.loads(camera.detection_zones)
            zones_to_test = [DetectionZone(**z) for z in zones_dict]
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.warning(f"Failed to parse camera zones: {e}")

    # Draw zones on frame
    frame_with_zones = frame.copy()

    for zone in zones_to_test:
        vertices = zone.vertices
        if len(vertices) < 3:
            continue

        # Convert to numpy array
        points = np.array([[v['x'], v['y']] for v in vertices], dtype=np.int32)

        # Draw polygon
        color = (0, 255, 0) if zone.enabled else (128, 128, 128)  # Green if enabled, gray if disabled
        cv2.polylines(frame_with_zones, [points], isClosed=True, color=color, thickness=2)

        # Add zone name
        if len(vertices) > 0:
            text_pos = (vertices[0]['x'], vertices[0]['y'] - 10)
            cv2.putText(
                frame_with_zones,
                zone.name,
                text_pos,
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                1
            )

    # Encode preview
    _, buffer = cv2.imencode('.jpg', frame_with_zones, [cv2.IMWRITE_JPEG_QUALITY, 85])
    preview_b64 = base64.b64encode(buffer).decode('utf-8')

    # Run motion detection test (if enabled)
    motion_detected = False
    if camera.motion_enabled:
        try:
            detector = motion_detection_service._get_or_create_detector(camera_id, camera.motion_algorithm)
            motion_detected, confidence, bounding_box = detector.detect_motion(
                frame,
                sensitivity=camera.motion_sensitivity
            )
        except Exception as e:
            logger.warning(f"Motion detection test failed: {e}")

    return {
        "motion_detected": motion_detected,
        "zones_count": len(zones_to_test),
        "enabled_zones_count": sum(1 for z in zones_to_test if z.enabled),
        "preview_image": f"data:image/jpeg;base64,{preview_b64}"
    }


# ============================================================================
# Detection Schedule Endpoints (F2.3)
# ============================================================================

@router.put("/{camera_id}/schedule", response_model=CameraResponse)
def update_camera_schedule(
    camera_id: str,
    schedule: DetectionSchedule,
    db: Session = Depends(get_db)
):
    """
    Update detection schedule for camera

    Args:
        camera_id: Camera UUID
        schedule: DetectionSchedule schema with time/day configuration

    Returns:
        Updated camera with new detection_schedule

    Raises:
        404: Camera not found
        422: Invalid schedule format

    Example Request:
        PUT /api/v1/cameras/{id}/schedule
        {
            "id": "schedule-1",
            "name": "Weekday Nights",
            "days_of_week": [0, 1, 2, 3, 4],
            "start_time": "22:00",
            "end_time": "06:00",
            "enabled": true
        }
    """
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera {camera_id} not found"
        )

    # Serialize schedule to JSON
    try:
        import json
        schedule_json = json.dumps(schedule.model_dump())
    except Exception as e:
        logger.error(f"Failed to serialize schedule: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid schedule format"
        )

    # Update camera
    camera.detection_schedule = schedule_json

    try:
        db.commit()
        db.refresh(camera)
        logger.info(f"Updated detection schedule for camera {camera_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update camera schedule: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update schedule"
        )

    return camera


@router.get("/{camera_id}/schedule", response_model=Optional[DetectionSchedule])
def get_camera_schedule(
    camera_id: str,
    db: Session = Depends(get_db)
):
    """
    Get detection schedule for camera

    Args:
        camera_id: Camera UUID

    Returns:
        DetectionSchedule or null if not configured

    Raises:
        404: Camera not found

    Example Response:
        {
            "id": "schedule-1",
            "name": "Weekday Nights",
            "days_of_week": [0, 1, 2, 3, 4],
            "start_time": "22:00",
            "end_time": "06:00",
            "enabled": true
        }
    """
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera {camera_id} not found"
        )

    if not camera.detection_schedule:
        return None

    # Parse JSON schedule
    try:
        import json
        schedule_dict = json.loads(camera.detection_schedule)
        return DetectionSchedule(**schedule_dict)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.error(f"Failed to parse camera schedule: {e}")
        return None


@router.get("/{camera_id}/schedule/status")
def get_camera_schedule_status(
    camera_id: str,
    db: Session = Depends(get_db)
):
    """
    Get current schedule status for camera

    Args:
        camera_id: Camera UUID

    Returns:
        Current schedule active state with reason

    Raises:
        404: Camera not found

    Example Response:
        {
            "active": true,
            "reason": "Within scheduled time and day",
            "current_time": "22:30:00",
            "current_day": 1,
            "schedule_enabled": true
        }
    """
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera {camera_id} not found"
        )

    # Import schedule manager
    from app.services.schedule_manager import schedule_manager
    from datetime import datetime

    # Check if detection is currently active
    is_active = schedule_manager.is_detection_active(camera_id, camera.detection_schedule)

    # Determine reason
    if not camera.detection_schedule:
        reason = "No schedule configured (always active)"
        schedule_enabled = None
    else:
        try:
            import json
            schedule_dict = json.loads(camera.detection_schedule)
            schedule_enabled = schedule_dict.get('enabled', False)

            if not schedule_enabled:
                reason = "Schedule disabled (always active)"
            elif is_active:
                reason = "Within scheduled time and day"
            else:
                reason = "Outside scheduled time or day"
        except (json.JSONDecodeError, TypeError, ValueError):
            reason = "Invalid schedule format (always active)"
            schedule_enabled = None

    # Get current time and day
    now = datetime.now()
    current_time = now.strftime('%H:%M:%S')
    current_day = now.weekday()  # 0=Monday, 6=Sunday

    return {
        "active": is_active,
        "reason": reason,
        "current_time": current_time,
        "current_day": current_day,
        "schedule_enabled": schedule_enabled
    }


# ============================================================================
# Live Preview & Manual Analysis Endpoints (Story 4.3)
# ============================================================================

@router.get("/{camera_id}/preview")
async def get_camera_preview(
    camera_id: str,
    db: Session = Depends(get_db)
):
    """
    Get current camera preview frame as base64-encoded JPEG

    Supports both RTSP/USB cameras (via camera_service) and Protect cameras
    (via protect_service snapshot API).

    Args:
        camera_id: UUID of camera
        db: Database session

    Returns:
        JSON with thumbnail_base64 field containing base64-encoded JPEG

    Raises:
        404: Camera not found
        400: Camera not running or failed to capture frame

    Example Response:
        {
            "thumbnail_base64": "/9j/4AAQSkZJRg..."
        }
    """
    try:
        camera = db.query(Camera).filter(Camera.id == camera_id).first()

        if not camera:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Camera {camera_id} not found"
            )

        # Check if camera is enabled
        if not camera.is_enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Camera {camera_id} is disabled"
            )

        # Route to appropriate service based on source_type
        if camera.source_type == 'protect':
            # Protect camera - use protect_service snapshot
            return await _get_protect_camera_preview(camera)
        else:
            # RTSP/USB camera - use camera_service
            return _get_rtsp_camera_preview(camera_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get preview for camera {camera_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get camera preview: {str(e)}"
        )


async def _get_protect_camera_preview(camera: Camera) -> dict:
    """Get preview for a Protect camera via snapshot API."""
    if not camera.protect_controller_id or not camera.protect_camera_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Camera is missing Protect controller or camera ID"
        )

    protect_service = get_protect_service()

    # Check if controller is connected
    conn_status = protect_service.get_connection_status(str(camera.protect_controller_id))
    if not conn_status.get('connected'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Protect controller is not connected"
        )

    try:
        snapshot_bytes = await protect_service.get_camera_snapshot(
            controller_id=str(camera.protect_controller_id),
            protect_camera_id=camera.protect_camera_id,
            width=640
        )

        if not snapshot_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No snapshot available from camera"
            )

        # Convert to base64
        preview_b64 = base64.b64encode(snapshot_bytes).decode('utf-8')

        return {
            "thumbnail_base64": preview_b64
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


def _get_rtsp_camera_preview(camera_id: str) -> dict:
    """Get preview for an RTSP/USB camera via camera_service."""
    # Get camera status from service
    cam_status = camera_service.get_camera_status(camera_id)

    if not cam_status or cam_status.get('status') != 'connected':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Camera {camera_id} is not currently running"
        )

    # Get latest frame from camera service
    latest_frame = camera_service.get_latest_frame(camera_id)

    if latest_frame is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No frame available from camera"
        )

    # Resize to preview size (640x480 or maintain aspect ratio)
    height, width = latest_frame.shape[:2]
    preview_width = 640
    aspect_ratio = width / height
    preview_height = int(preview_width / aspect_ratio)

    preview_frame = cv2.resize(latest_frame, (preview_width, preview_height))

    # Encode as JPEG
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 80]
    ret, buffer = cv2.imencode('.jpg', preview_frame, encode_param)

    if not ret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to encode preview image"
        )

    # Convert to base64
    preview_b64 = base64.b64encode(buffer).decode('utf-8')

    return {
        "thumbnail_base64": preview_b64
    }


@router.post("/{camera_id}/analyze")
async def analyze_camera(
    camera_id: str,
    db: Session = Depends(get_db)
):
    """
    Trigger manual camera analysis (bypasses motion detection)

    This endpoint forces an immediate AI analysis of the current camera frame,
    regardless of motion detection settings. The analysis happens asynchronously
    and results are saved as an Event in the database.

    Supports both RTSP/USB cameras (via camera_service) and Protect cameras
    (via Protect API snapshot).

    Args:
        camera_id: UUID of camera
        db: Database session

    Returns:
        Success confirmation message

    Raises:
        404: Camera not found
        400: Camera not running or analysis failed

    Example Response:
        {
            "success": true,
            "message": "Analysis triggered successfully"
        }
    """
    logger.info(f"=== ANALYZE ENDPOINT CALLED for camera {camera_id} ===")
    try:
        camera = db.query(Camera).filter(Camera.id == camera_id).first()
        logger.info(f"Camera found: {camera is not None}, source_type: {camera.source_type if camera else 'N/A'}")

        if not camera:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Camera {camera_id} not found"
            )

        # Check if camera is enabled
        if not camera.is_enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Camera {camera_id} is disabled. Enable camera first."
            )

        # Handle Protect cameras differently from RTSP/USB cameras
        if camera.source_type == 'protect':
            return await _analyze_protect_camera(camera, db)
        else:
            return await _analyze_rtsp_camera(camera, db)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to analyze camera {camera_id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger analysis: {str(e)}"
        )


async def _analyze_rtsp_camera(camera: Camera, db: Session):
    """Handle manual analysis for RTSP/USB cameras"""
    camera_id = str(camera.id)

    # Check if camera is running
    camera_status = camera_service.get_camera_status(camera_id)

    if not camera_status or camera_status.get('status') != 'connected':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Camera {camera_id} is not currently running"
        )

    # Get latest frame
    latest_frame = camera_service.get_latest_frame(camera_id)

    if latest_frame is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No frame available from camera"
        )

    # Get event processor
    event_processor = get_event_processor()
    if event_processor is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Event processor not running. Check if AI service is configured."
        )

    # Queue event for AI processing
    from datetime import datetime, timezone

    processing_event = ProcessingEvent(
        camera_id=camera_id,
        camera_name=camera.name,
        frame=latest_frame,
        timestamp=datetime.now(timezone.utc),
        detected_objects=["manual_trigger"],
        metadata={"trigger": "manual", "source": "analyze_button"}
    )

    # Queue the event for async AI processing
    await event_processor.queue_event(processing_event)

    logger.info(f"Manual analysis queued for RTSP camera {camera_id} ({camera.name})")

    return {
        "success": True,
        "message": "Analysis triggered successfully"
    }


async def _analyze_protect_camera(camera: Camera, db: Session):
    """Handle manual analysis for Protect cameras (Story P2-3.3 extension)"""
    from app.services.protect_service import get_protect_service
    from app.services.snapshot_service import get_snapshot_service
    from app.services.protect_event_handler import get_protect_event_handler

    camera_id = str(camera.id)
    logger.info(f"Starting manual analysis for Protect camera {camera_id} ({camera.name})")

    # Validate Protect camera has required fields
    if not camera.protect_controller_id or not camera.protect_camera_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Protect camera is missing controller or camera ID configuration"
        )

    # Check if controller is connected
    protect_service = get_protect_service()
    controller_status = protect_service.get_connection_status(camera.protect_controller_id)
    logger.debug(f"Controller status for {camera.protect_controller_id}: {controller_status}")

    if not controller_status.get('connected'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Protect controller is not connected. Connect the controller first."
        )

    # Get snapshot from Protect API
    snapshot_service = get_snapshot_service()
    try:
        logger.debug(f"Requesting snapshot for camera {camera.protect_camera_id}")
        snapshot_result = await snapshot_service.get_snapshot(
            controller_id=camera.protect_controller_id,
            protect_camera_id=camera.protect_camera_id,
            camera_id=camera_id,
            camera_name=camera.name
        )
        logger.debug(f"Snapshot result: {snapshot_result is not None}")
    except Exception as e:
        logger.error(f"Failed to get snapshot for Protect camera {camera_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to get camera snapshot: {str(e)}"
        )

    if not snapshot_result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No snapshot available from Protect camera"
        )

    # Use the protect event handler to process through AI pipeline
    # This reuses the same code path as WebSocket events
    event_handler = get_protect_event_handler()

    # Submit to AI pipeline
    try:
        logger.debug(f"Submitting to AI pipeline for camera {camera_id}")
        ai_result = await event_handler._submit_to_ai_pipeline(
            snapshot_result=snapshot_result,
            camera=camera,
            event_type="manual_trigger"
        )
        logger.debug(f"AI result: success={ai_result.success if ai_result else 'None'}")
    except Exception as e:
        logger.error(f"AI pipeline exception for camera {camera_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI analysis exception: {str(e)}"
        )

    if not ai_result:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI analysis failed: No result returned"
        )

    if not ai_result.success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI analysis failed: {ai_result.error}"
        )

    # Store the event
    try:
        logger.debug(f"Storing event for camera {camera_id}")
        stored_event = await event_handler._store_protect_event(
            db=db,
            ai_result=ai_result,
            snapshot_result=snapshot_result,
            camera=camera,
            event_type="manual_trigger",
            protect_event_id=None  # Manual trigger has no Protect event ID
        )
    except Exception as e:
        logger.error(f"Failed to store event for camera {camera_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store analysis result: {str(e)}"
        )

    if not stored_event:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store analysis result"
        )

    # Broadcast event
    try:
        await event_handler._broadcast_event_created(stored_event, camera)
    except Exception as e:
        logger.warning(f"Failed to broadcast event {stored_event.id}: {e}")
        # Don't fail the request if broadcast fails

    logger.info(f"Manual analysis completed for Protect camera {camera_id} ({camera.name})")

    return {
        "success": True,
        "message": "Analysis completed successfully",
        "event_id": stored_event.id
    }
