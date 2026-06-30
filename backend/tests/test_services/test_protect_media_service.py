"""
Unit tests for ProtectMediaService clip-download gating.

The configured analysis_mode decides whether a motion clip is downloaded:
- single_frame  -> never download a clip (snapshot only); saves bandwidth/time.
- multi_frame   -> download a clip (frames are extracted from it downstream).
- video_native  -> download a clip (sent natively to the provider).

This guards the regression where every event downloaded a clip regardless of
mode, and the inverse where multi_frame cameras were starved of a clip.
"""
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.services.protect_media_service import (
    ProtectMediaService,
    reset_protect_media_service,
)
from app.services.snapshot_service import SnapshotResult


@pytest.fixture
def media_service():
    reset_protect_media_service()
    return ProtectMediaService()


@pytest.fixture
def snapshot():
    return SnapshotResult(
        image_base64="abc",
        thumbnail_path="/tmp/t.jpg",
        width=1920,
        height=1080,
        camera_id="cam-1",
        timestamp=datetime.now(timezone.utc),
    )


async def _call(media_service, analysis_mode, is_doorbell_ring=False):
    return await media_service.get_media_for_event(
        controller_id="ctrl-1",
        protect_camera_id="protect-1",
        camera_id="cam-1",
        camera_name="Front Door",
        event_id="evt-1",
        event_timestamp=datetime.now(timezone.utc),
        is_doorbell_ring=is_doorbell_ring,
        analysis_mode=analysis_mode,
    )


@pytest.mark.asyncio
async def test_single_frame_mode_does_not_download_clip(media_service, snapshot):
    with patch.object(
        media_service, "_retrieve_snapshot", new_callable=AsyncMock, return_value=snapshot
    ), patch.object(
        media_service, "_download_clip", new_callable=AsyncMock, return_value=(Path("/tmp/c.mp4"), None)
    ) as mock_download:
        bundle = await _call(media_service, analysis_mode="single_frame")

    mock_download.assert_not_called()
    assert bundle.clip_path is None
    assert bundle.has_snapshot is True


@pytest.mark.asyncio
async def test_multi_frame_mode_downloads_clip(media_service, snapshot):
    with patch.object(
        media_service, "_retrieve_snapshot", new_callable=AsyncMock, return_value=snapshot
    ), patch.object(
        media_service, "_download_clip", new_callable=AsyncMock, return_value=(Path("/tmp/c.mp4"), None)
    ) as mock_download:
        bundle = await _call(media_service, analysis_mode="multi_frame")

    mock_download.assert_called_once()
    assert bundle.clip_path == Path("/tmp/c.mp4")


@pytest.mark.asyncio
async def test_video_native_mode_downloads_clip(media_service, snapshot):
    with patch.object(
        media_service, "_retrieve_snapshot", new_callable=AsyncMock, return_value=snapshot
    ), patch.object(
        media_service, "_download_clip", new_callable=AsyncMock, return_value=(Path("/tmp/c.mp4"), None)
    ) as mock_download:
        bundle = await _call(media_service, analysis_mode="video_native")

    mock_download.assert_called_once()


@pytest.mark.asyncio
async def test_unset_mode_defaults_to_downloading_clip(media_service, snapshot):
    """No configured mode -> multi_frame default -> clip is downloaded."""
    with patch.object(
        media_service, "_retrieve_snapshot", new_callable=AsyncMock, return_value=snapshot
    ), patch.object(
        media_service, "_download_clip", new_callable=AsyncMock, return_value=(Path("/tmp/c.mp4"), None)
    ) as mock_download:
        bundle = await _call(media_service, analysis_mode=None)

    mock_download.assert_called_once()
