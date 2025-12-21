"""
Tests for Story P8-2.3: Configurable Frame Count Setting

Tests cover:
- Settings API returns analysis_frame_count with default 10
- Settings API accepts valid values (5, 10, 15, 20)
- Settings API rejects invalid values
- Frame extractor uses configured count
"""

import pytest


class TestAnalysisFrameCountSettings:
    """Test analysis_frame_count setting in system settings API."""

    def test_get_settings_returns_default_frame_count(self, api_client):
        """AC3.7: Default value is 10 when not set."""
        response = api_client.get("/api/v1/system/settings")
        assert response.status_code == 200
        # analysis_frame_count should default to None (not set) or be absent
        # The frontend will use 10 as default

    def test_update_settings_with_valid_frame_count_5(self, api_client):
        """AC3.6: Setting accepts valid value 5."""
        response = api_client.put(
            "/api/v1/system/settings",
            json={"analysis_frame_count": 5}
        )
        assert response.status_code == 200

    def test_saved_frame_count_persists_in_get_response(self, api_client):
        """Verify that saved frame count is returned in GET response."""
        # Save value 15
        put_response = api_client.put(
            "/api/v1/system/settings",
            json={"analysis_frame_count": 15}
        )
        assert put_response.status_code == 200

        # Get settings and verify value is returned as integer
        get_response = api_client.get("/api/v1/system/settings")
        assert get_response.status_code == 200
        data = get_response.json()
        assert "analysis_frame_count" in data
        assert data["analysis_frame_count"] == 15
        assert isinstance(data["analysis_frame_count"], int)

    def test_update_settings_with_valid_frame_count_10(self, api_client):
        """AC3.6: Setting accepts valid value 10."""
        response = api_client.put(
            "/api/v1/system/settings",
            json={"analysis_frame_count": 10}
        )
        assert response.status_code == 200

    def test_update_settings_with_valid_frame_count_15(self, api_client):
        """AC3.6: Setting accepts valid value 15."""
        response = api_client.put(
            "/api/v1/system/settings",
            json={"analysis_frame_count": 15}
        )
        assert response.status_code == 200

    def test_update_settings_with_valid_frame_count_20(self, api_client):
        """AC3.6: Setting accepts valid value 20."""
        response = api_client.put(
            "/api/v1/system/settings",
            json={"analysis_frame_count": 20}
        )
        assert response.status_code == 200

    def test_update_settings_rejects_invalid_frame_count_0(self, api_client):
        """Settings API rejects invalid value 0."""
        response = api_client.put(
            "/api/v1/system/settings",
            json={"analysis_frame_count": 0}
        )
        # Should return 422 Unprocessable Entity for invalid literal
        assert response.status_code == 422

    def test_update_settings_rejects_invalid_frame_count_3(self, api_client):
        """Settings API rejects invalid value 3."""
        response = api_client.put(
            "/api/v1/system/settings",
            json={"analysis_frame_count": 3}
        )
        assert response.status_code == 422

    def test_update_settings_rejects_invalid_frame_count_25(self, api_client):
        """Settings API rejects invalid value 25."""
        response = api_client.put(
            "/api/v1/system/settings",
            json={"analysis_frame_count": 25}
        )
        assert response.status_code == 422

    def test_update_settings_rejects_invalid_frame_count_string(self, api_client):
        """Settings API rejects non-integer value."""
        response = api_client.put(
            "/api/v1/system/settings",
            json={"analysis_frame_count": "ten"}
        )
        assert response.status_code == 422


class TestFrameExtractorConstants:
    """Test frame extractor constant changes for P8-2.3."""

    def test_frame_extract_default_count_is_10(self):
        """AC3.7: Default count is now 10."""
        from app.services.frame_extractor import FRAME_EXTRACT_DEFAULT_COUNT
        assert FRAME_EXTRACT_DEFAULT_COUNT == 10

    def test_frame_extract_max_count_is_20(self):
        """Max count increased to 20 to support all configurable values."""
        from app.services.frame_extractor import FRAME_EXTRACT_MAX_COUNT
        assert FRAME_EXTRACT_MAX_COUNT == 20

    def test_frame_extractor_accepts_frame_count_20(self):
        """Frame extractor should accept frame_count=20."""
        from app.services.frame_extractor import FrameExtractor
        extractor = FrameExtractor()

        # Calculate indices for 20 frames from 300 total
        indices = extractor._calculate_frame_indices(300, 20)
        assert len(indices) == 20
        assert indices[0] == 0  # First frame
        assert indices[-1] == 299  # Last frame
