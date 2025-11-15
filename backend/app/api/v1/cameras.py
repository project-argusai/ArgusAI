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
from typing import List
import logging
import cv2
import base64
import numpy as np

from app.core.database import get_db
from app.models.camera import Camera
from app.schemas.camera import CameraCreate, CameraUpdate, CameraResponse, CameraTestResponse
from app.schemas.motion import MotionConfigUpdate, MotionConfigResponse, MotionTestRequest, MotionTestResponse
from app.services.camera_service import CameraService
from app.services.motion_detection_service import motion_detection_service

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

        if not ret or frame is None:
            cap.release()
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
        if camera.type == "rtsp":
            connection_str = camera_service._build_rtsp_url(camera)
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
