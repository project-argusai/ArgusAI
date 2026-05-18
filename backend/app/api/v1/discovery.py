"""
Camera Discovery API Endpoints (Stories P5-2.1, P5-2.2)

ONVIF WS-Discovery endpoints for camera auto-discovery:
- POST /api/v1/cameras/discover - Trigger network scan for ONVIF cameras
- POST /api/v1/cameras/discover/device - Get detailed info for a specific device

Architecture Reference: docs/architecture/phase-5-additions.md
PRD Reference: docs/PRD-phase5.md (FR13, FR14, FR15)
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.schemas.discovery import (
    DiscoveredDevice,
    DiscoveryRequest,
    DiscoveryResponse,
    DeviceDetailsRequest,
    DeviceDetailsResponse,
    TestConnectionRequest,
    TestConnectionResponse,
)
from app.services.onvif_discovery_service import (
    WSDISCOVERY_AVAILABLE,
    ONVIF_ZEEP_AVAILABLE,
)
from app.services.service_container import container

logger = logging.getLogger(__name__)

router = APIRouter(tags=["discovery"])


class DiscoveryStatusResponse(BaseModel):
    """Response for discovery status check."""
    available: bool = Field(..., description="Whether ONVIF discovery is available")
    library_installed: bool = Field(..., description="Whether WSDiscovery is installed")
    message: str = Field(..., description="Status message")


@router.get(
    "/discover/status",
    response_model=DiscoveryStatusResponse,
    summary="Check discovery availability",
    description="Check if ONVIF camera discovery feature is available"
)
async def get_discovery_status() -> DiscoveryStatusResponse:
    """
    Check if ONVIF discovery is available.

    Returns availability status and whether required libraries are installed.
    """
    service = container.onvif_discovery_service

    if service.is_available:
        return DiscoveryStatusResponse(
            available=True,
            library_installed=True,
            message="ONVIF camera discovery is available"
        )
    else:
        return DiscoveryStatusResponse(
            available=False,
            library_installed=False,
            message=(
                "ONVIF discovery unavailable: WSDiscovery package not installed. "
                "Install with: pip install WSDiscovery"
            )
        )


@router.post(
    "/discover",
    response_model=DiscoveryResponse,
    summary="Discover ONVIF cameras",
    description="Scan local network for ONVIF-compatible cameras using WS-Discovery"
)
async def discover_cameras(
    request: Optional[DiscoveryRequest] = None
) -> DiscoveryResponse:
    """
    Discover ONVIF cameras on the local network.

    Sends WS-Discovery probes to multicast address 239.255.255.250:3702
    and collects responses from ONVIF Network Video Transmitters.

    Args:
        request: Optional discovery parameters (timeout)

    Returns:
        DiscoveryResponse with list of discovered devices

    Raises:
        503: If discovery service is unavailable
        500: If discovery fails due to network error
    """
    service = container.onvif_discovery_service

    # Check availability
    if not service.is_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "discovery_unavailable",
                "message": (
                    "ONVIF discovery unavailable: WSDiscovery package not installed. "
                    "Install with: pip install WSDiscovery"
                )
            }
        )

    # Get timeout from request or use default
    timeout = 10
    if request and request.timeout:
        timeout = request.timeout

    logger.info(f"Starting ONVIF camera discovery (timeout: {timeout}s)")

    try:
        result = await service.discover_cameras_with_result(timeout=timeout)

        return DiscoveryResponse(
            status=result.status,
            duration_ms=result.duration_ms,
            devices=result.devices,
            device_count=len(result.devices),
            error_message=result.error
        )

    except Exception as e:
        logger.error(f"Discovery endpoint error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "discovery_failed",
                "message": f"Discovery failed: {str(e)}"
            }
        )


@router.post(
    "/discover/clear-cache",
    summary="Clear discovery cache",
    description="Clear cached discovery results to force a fresh scan"
)
async def clear_discovery_cache() -> dict:
    """
    Clear the discovery results cache.

    Forces the next discovery scan to perform a fresh network probe
    instead of returning cached results.

    Returns:
        Success message
    """
    service = container.onvif_discovery_service
    service.clear_cache()

    logger.info("Discovery cache cleared")

    return {"status": "success", "message": "Discovery cache cleared"}


# ============================================================================
# Device Details Endpoints (Story P5-2.2)
# ============================================================================


class DeviceDetailsStatusResponse(BaseModel):
    """Response for device details status check."""
    available: bool = Field(..., description="Whether device details query is available")
    library_installed: bool = Field(..., description="Whether onvif-zeep is installed")
    message: str = Field(..., description="Status message")


@router.get(
    "/discover/device/status",
    response_model=DeviceDetailsStatusResponse,
    summary="Check device details availability",
    description="Check if ONVIF device details query feature is available"
)
async def get_device_details_status() -> DeviceDetailsStatusResponse:
    """
    Check if ONVIF device details query is available.

    Returns availability status and whether required libraries are installed.
    """
    service = container.onvif_discovery_service

    if service.is_device_details_available:
        return DeviceDetailsStatusResponse(
            available=True,
            library_installed=True,
            message="ONVIF device details query is available"
        )
    else:
        return DeviceDetailsStatusResponse(
            available=False,
            library_installed=False,
            message=(
                "ONVIF device details unavailable: onvif-zeep package not installed. "
                "Install with: pip install onvif-zeep"
            )
        )


@router.post(
    "/discover/device",
    response_model=DeviceDetailsResponse,
    summary="Get device details",
    description="Query a discovered ONVIF device for detailed information (manufacturer, model, stream profiles)"
)
async def get_device_details(
    request: DeviceDetailsRequest
) -> DeviceDetailsResponse:
    """
    Get detailed information from a discovered ONVIF device.

    Queries the device using ONVIF SOAP protocol to retrieve:
    - Device information (manufacturer, model, firmware version)
    - Media profiles (stream configurations)
    - RTSP URLs for each profile

    Args:
        request: Device details request with endpoint URL and optional credentials

    Returns:
        DeviceDetailsResponse with device info and profiles

    Raises:
        503: If onvif-zeep is not installed
        500: If device query fails due to network error
    """
    service = container.onvif_discovery_service

    # Check availability
    if not service.is_device_details_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "device_details_unavailable",
                "message": (
                    "ONVIF device details unavailable: onvif-zeep package not installed. "
                    "Install with: pip install onvif-zeep"
                )
            }
        )

    logger.info(f"Querying device details for: {request.endpoint_url}")

    try:
        result = await service.get_device_details(
            endpoint_url=request.endpoint_url,
            username=request.username,
            password=request.password
        )

        return DeviceDetailsResponse(
            status=result.status,
            device=result.device,
            error_message=result.error,
            duration_ms=result.duration_ms
        )

    except Exception as e:
        logger.error(f"Device details endpoint error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "device_query_failed",
                "message": f"Device query failed: {str(e)}"
            }
        )


# ============================================================================
# Test Connection Endpoint (Story P5-2.4)
# ============================================================================


@router.post(
    "/discover/test",
    response_model=TestConnectionResponse,
    summary="Test RTSP connection",
    description="Test an RTSP camera connection without saving the camera configuration",
    responses={
        200: {
            "description": "Connection test result",
            "content": {
                "application/json": {
                    "examples": {
                        "success": {
                            "summary": "Successful connection",
                            "value": {
                                "success": True,
                                "latency_ms": 234,
                                "resolution": "1920x1080",
                                "fps": 30,
                                "codec": "H.264",
                                "error": None
                            }
                        },
                        "failure": {
                            "summary": "Failed connection",
                            "value": {
                                "success": False,
                                "latency_ms": 5000,
                                "resolution": None,
                                "fps": None,
                                "codec": None,
                                "error": "Connection timed out after 5 seconds"
                            }
                        }
                    }
                }
            }
        },
        422: {
            "description": "Invalid RTSP URL format"
        }
    }
)
async def test_camera_connection(
    request: TestConnectionRequest
) -> TestConnectionResponse:
    """
    Test an RTSP camera connection without saving the camera.

    This endpoint validates connectivity to an RTSP stream and retrieves
    stream metadata (resolution, FPS, codec) on success. Useful for
    verifying camera settings before adding a camera.

    The test times out after 5 seconds to prevent hanging on unresponsive cameras.

    Args:
        request: Test connection request with RTSP URL and optional credentials

    Returns:
        TestConnectionResponse with success status, stream metadata, or error message

    Notes:
        - Password is never logged or included in error messages
        - URL must start with rtsp:// or rtsps://
        - Test includes opening connection and reading first frame
    """
    service = container.onvif_discovery_service

    # Sanitize URL for logging (remove password)
    sanitized_url = request.rtsp_url
    if request.password:
        sanitized_url = request.rtsp_url  # Password not embedded in URL yet

    logger.info(f"Testing RTSP connection: {sanitized_url}")

    try:
        result = await service.test_connection(
            rtsp_url=request.rtsp_url,
            username=request.username,
            password=request.password
        )

        if result.success:
            logger.info(
                f"Connection test successful: {sanitized_url} - "
                f"{result.resolution} @ {result.fps}fps"
            )
        else:
            logger.info(f"Connection test failed: {sanitized_url} - {result.error}")

        return result

    except Exception as e:
        logger.error(f"Test connection endpoint error: {e}", exc_info=True)
        return TestConnectionResponse(
            success=False,
            error=f"Test failed: {str(e)}"
        )
