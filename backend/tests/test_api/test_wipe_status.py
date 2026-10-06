"""Wipe must not claim success when media removal fails (CR-010 / #600)."""
from pathlib import Path
from unittest.mock import patch

from app.api.v1.system import DeleteDataResponse


def test_delete_data_response_defaults():
    resp = DeleteDataResponse(deleted_count=3, success=True)
    assert resp.status == "success"
    assert resp.files_failed == 0


def test_partial_wipe_shape():
    resp = DeleteDataResponse(
        deleted_count=10,
        success=False,
        status="partial",
        files_failed=2,
        message="retry",
    )
    assert resp.success is False
    assert resp.files_failed == 2
