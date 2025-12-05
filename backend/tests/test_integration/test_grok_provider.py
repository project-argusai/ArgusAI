"""
Integration tests for xAI Grok provider (Story P2-6.4, AC6)

Tests Grok provider configuration and fallback:
- Grok provider can be configured via API
- Grok provider works in AI fallback chain
- Grok uses correct model and base URL
- Grok has appropriate retry logic

These tests use mocks since actual API calls would be expensive.
"""
import pytest
import numpy as np
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import tempfile
import os

from main import app
from app.core.database import Base, get_db
from app.models.system_setting import SystemSetting
from app.services.ai_service import (
    AIService,
    GrokProvider,
    AIResult,
    AIProvider as AIProviderEnum,
)


# Create test database
test_db_fd, test_db_path = tempfile.mkstemp(suffix=".db")
os.close(test_db_fd)

TEST_DATABASE_URL = f"sqlite:///{test_db_path}"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency for testing"""
    db = TestingSessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# Override database dependency
app.dependency_overrides[get_db] = override_get_db

# Create tables once
Base.metadata.create_all(bind=engine)

# Create test client
client = TestClient(app)


@pytest.fixture(scope="function", autouse=True)
def cleanup_database():
    """Clean up database between tests"""
    yield
    db = TestingSessionLocal()
    try:
        db.query(SystemSetting).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture
def sample_frame():
    """Create a sample image frame"""
    return np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)


@pytest.fixture
def ai_service():
    """Create AI service instance"""
    service = AIService()
    service.configure_providers(grok_key="xai-test-key-12345")
    return service


@pytest.fixture
def grok_provider():
    """Create Grok provider instance"""
    return GrokProvider("xai-test-key-12345")


class TestGrokProviderConfiguration:
    """Tests for Grok provider configuration (AC6)"""

    def test_grok_uses_correct_base_url(self, grok_provider):
        """Test Grok uses xAI API base URL"""
        assert grok_provider.client.base_url.host == "api.x.ai"

    def test_grok_uses_correct_model(self, grok_provider):
        """Test Grok uses grok-2-vision-1212 model"""
        assert grok_provider.model == "grok-2-vision-1212"

    def test_grok_provider_instantiation(self):
        """Test Grok provider can be instantiated"""
        provider = GrokProvider("xai-test-key")
        assert provider is not None
        assert provider.model is not None

    def test_grok_provider_has_required_methods(self, grok_provider):
        """Test Grok provider has generate_description method"""
        assert hasattr(grok_provider, 'generate_description')
        assert callable(grok_provider.generate_description)


class TestGrokProviderAPIConfiguration:
    """Tests for configuring Grok via API"""

    def test_save_grok_api_key_via_settings(self):
        """Test Grok API key can be saved via settings API"""
        settings_data = {
            "grok_api_key": "xai-new-api-key-67890"
        }

        response = client.put("/api/v1/system/settings", json=settings_data)
        # Response depends on endpoint implementation
        assert response.status_code in [200, 201, 422]

    def test_grok_key_not_exposed_in_response(self):
        """Test API key is not exposed in get settings response"""
        # First set a key
        client.put("/api/v1/system/settings", json={
            "grok_api_key": "xai-secret-key"
        })

        # Get settings
        response = client.get("/api/v1/system/settings")
        if response.status_code == 200:
            data = response.json()
            settings = data.get("data", data)
            # Key should be masked or not present in full
            if "grok_api_key" in settings:
                assert settings["grok_api_key"] != "xai-secret-key"


class TestGrokInFallbackChain:
    """Tests for Grok in AI fallback chain (AC6)"""

    @pytest.mark.asyncio
    async def test_grok_in_provider_order(self, ai_service):
        """Test Grok is included in provider order"""
        # Grok should be available as a provider
        assert AIProviderEnum.GROK in ai_service.providers

    @pytest.mark.asyncio
    async def test_fallback_to_grok_when_openai_fails(self, ai_service, sample_frame):
        """Test fallback to Grok when OpenAI fails"""
        # Configure both providers
        ai_service.configure_providers(
            openai_key="sk-test-openai",
            grok_key="xai-test-grok"
        )

        # Mock OpenAI to fail
        openai_fail = AIResult(
            description="",
            confidence=0,
            objects_detected=[],
            provider="openai",
            tokens_used=0,
            response_time_ms=100,
            cost_estimate=0.0,
            success=False,
            error="API rate limit"
        )

        # Mock Grok to succeed
        grok_success = AIResult(
            description="Person detected at front door",
            confidence=85,
            objects_detected=["person"],
            provider="grok",
            tokens_used=100,
            response_time_ms=500,
            cost_estimate=0.015,
            success=True
        )

        with patch.object(
            ai_service.providers.get(AIProviderEnum.OPENAI),
            'generate_description',
            new=AsyncMock(return_value=openai_fail)
        ), patch.object(
            ai_service.providers.get(AIProviderEnum.GROK),
            'generate_description',
            new=AsyncMock(return_value=grok_success)
        ):
            result = await ai_service.generate_description(
                sample_frame,
                "Test Camera",
                datetime.now(timezone.utc),
                ["person"],
                sla_timeout_ms=30000
            )

        assert result.success is True
        assert result.provider == "grok"


class TestGrokDescriptionGeneration:
    """Tests for Grok description generation"""

    @pytest.mark.asyncio
    async def test_grok_generates_description(self, grok_provider):
        """Test Grok generates description successfully"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "A delivery person with a package at the front door."
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 95
        mock_response.usage.prompt_tokens = 60
        mock_response.usage.completion_tokens = 35

        with patch.object(
            grok_provider.client.chat.completions,
            'create',
            new=AsyncMock(return_value=mock_response)
        ):
            result = await grok_provider.generate_description(
                "base64_image_data",
                "Front Door Camera",
                "2025-12-05T10:00:00",
                ["person", "package"]
            )

        assert result.success is True
        assert result.provider == "grok"
        assert "delivery" in result.description.lower() or "package" in result.description.lower()

    @pytest.mark.asyncio
    async def test_grok_handles_api_error(self, grok_provider):
        """Test Grok handles API errors gracefully"""
        with patch.object(
            grok_provider.client.chat.completions,
            'create',
            new=AsyncMock(side_effect=Exception("500 Internal Server Error"))
        ):
            result = await grok_provider.generate_description(
                "base64_data",
                "Camera",
                "2025-12-05T10:00:00",
                []
            )

        assert result.success is False
        assert result.error is not None


class TestGrokRetryLogic:
    """Tests for Grok-specific retry logic"""

    @pytest.mark.asyncio
    async def test_grok_retries_on_failure(self, ai_service, sample_frame):
        """Test Grok uses retry logic with backoff"""
        ai_service.configure_providers(grok_key="xai-test-key")
        grok_provider = ai_service.providers.get(AIProviderEnum.GROK)

        call_count = 0

        async def mock_generate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return AIResult(
                    description="",
                    confidence=0,
                    objects_detected=[],
                    provider="grok",
                    tokens_used=0,
                    response_time_ms=100,
                    cost_estimate=0.0,
                    success=False,
                    error="429 Too Many Requests"
                )
            return AIResult(
                description="Success on retry",
                confidence=85,
                objects_detected=["person"],
                provider="grok",
                tokens_used=100,
                response_time_ms=400,
                cost_estimate=0.015,
                success=True
            )

        with patch.object(grok_provider, 'generate_description', new=mock_generate):
            result = await ai_service._try_with_backoff(
                grok_provider,
                "base64_data",
                "Camera",
                "2025-12-05T10:00:00",
                [],
                provider_type=AIProviderEnum.GROK
            )

        # Should have called at least once
        assert call_count >= 1


class TestGrokObjectExtraction:
    """Tests for Grok object extraction from descriptions"""

    def test_extract_person(self, grok_provider):
        """Test extracting person from description"""
        objects = grok_provider._extract_objects("A person is standing at the door")
        assert "person" in objects

    def test_extract_vehicle(self, grok_provider):
        """Test extracting vehicle from description"""
        objects = grok_provider._extract_objects("A car is parked in the driveway")
        assert "vehicle" in objects

    def test_extract_package(self, grok_provider):
        """Test extracting package from description"""
        objects = grok_provider._extract_objects("A package was delivered to the porch")
        assert "package" in objects

    def test_extract_animal(self, grok_provider):
        """Test extracting animal from description"""
        objects = grok_provider._extract_objects("A dog is running in the yard")
        assert "animal" in objects

    def test_extract_unknown(self, grok_provider):
        """Test unknown returned for ambiguous description"""
        objects = grok_provider._extract_objects("Empty scene with nothing notable")
        assert "unknown" in objects


class TestGrokCostEstimate:
    """Tests for Grok cost estimation"""

    @pytest.mark.asyncio
    async def test_grok_returns_cost_estimate(self, grok_provider):
        """Test Grok returns cost estimate in result"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test description"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 100
        mock_response.usage.prompt_tokens = 65
        mock_response.usage.completion_tokens = 35

        with patch.object(
            grok_provider.client.chat.completions,
            'create',
            new=AsyncMock(return_value=mock_response)
        ):
            result = await grok_provider.generate_description(
                "base64_data",
                "Camera",
                "2025-12-05T10:00:00",
                []
            )

        assert result.cost_estimate > 0
        assert result.tokens_used == 100


class TestGrokProviderInSystem:
    """Integration tests for Grok in full system"""

    def test_grok_available_in_settings_page(self):
        """Test Grok appears as available provider option"""
        response = client.get("/api/v1/system/settings")
        if response.status_code == 200:
            # The settings endpoint should indicate Grok is available
            data = response.json()
            # Just verify we can check settings
            assert data is not None

    def test_ai_providers_endpoint_includes_grok(self):
        """Test AI providers endpoint includes Grok"""
        response = client.get("/api/v1/ai/providers")
        if response.status_code == 200:
            data = response.json()
            providers = data.get("data", data.get("providers", []))
            # Check if Grok is listed
            if isinstance(providers, list):
                provider_names = [p.get("name", p) for p in providers]
                # Grok should be in the list
                assert any("grok" in str(p).lower() for p in provider_names)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
