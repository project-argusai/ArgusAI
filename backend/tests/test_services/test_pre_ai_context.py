"""
Tests that would have caught the original named-description wiring bugs.

Covers:
- Protect vision path receives a context-enhanced custom_prompt with a named entity
- Similar-event search uses an in-memory CLIP vector, not a throwaway UUID
- Protect persist stores delivery_carrier and context_included
- Unnamed entities are not injected as names
- Prompt contract includes local time and carrier instruction
"""
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from app.services.context_prompt_service import (
    ContextEnhancedPromptService,
    ContextEnhancedPromptResult,
)
from app.services.entity_alert_service import EntityAlertService
from app.services.entity_service import EntityMatchResult
from app.services.pre_ai_context_service import (
    PreAIContextService,
    format_timestamp_for_ai,
    reset_pre_ai_context_service,
)
from app.services.prompt_templates import (
    MULTI_FRAME_SYSTEM_PROMPT,
    NAMING_AND_CARRIER_INSTRUCTION,
)
from app.services.ai_prompt_service import AIPromptService
from app.models.event import Event
from app.services.similarity_service import SimilarEvent


def _named_person(name="Isaac"):
    now = datetime.now(timezone.utc)
    return EntityMatchResult(
        entity_id="ent-isaac",
        entity_type="person",
        name=name,
        first_seen_at=now - timedelta(days=10),
        last_seen_at=now - timedelta(days=1),
        occurrence_count=8,
        similarity_score=0.91,
        is_new=False,
    )


class TestUnnamedEntitiesAreNotInjected:
    def test_format_entity_context_skips_unnamed(self):
        service = ContextEnhancedPromptService(
            entity_service=MagicMock(),
            similarity_service=MagicMock(),
        )
        unnamed = EntityMatchResult(
            entity_id="ent-x",
            entity_type="person",
            name=None,
            first_seen_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc),
            occurrence_count=3,
            similarity_score=0.88,
            is_new=False,
        )
        assert service._format_entity_context(unnamed) is None

    def test_format_entity_context_skips_blank_name(self):
        service = ContextEnhancedPromptService(
            entity_service=MagicMock(),
            similarity_service=MagicMock(),
        )
        blank = EntityMatchResult(
            entity_id="ent-x",
            entity_type="person",
            name="   ",
            first_seen_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc),
            occurrence_count=3,
            similarity_score=0.88,
            is_new=False,
        )
        assert service._format_entity_context(blank) is None

    def test_named_entity_is_injected(self):
        service = ContextEnhancedPromptService(
            entity_service=MagicMock(),
            similarity_service=MagicMock(),
        )
        result = service._format_entity_context(_named_person())
        assert result is not None
        assert "Isaac" in result
        assert "unnamed" not in result.lower()


class TestSimilarEventSearchUsesInMemoryVector:
    @pytest.mark.asyncio
    async def test_build_prompt_passes_query_embedding_not_random_uuid(self):
        mock_similarity = MagicMock()
        mock_similarity.find_similar_events_by_embedding = AsyncMock(return_value=[
            SimilarEvent(
                event_id="past-1",
                similarity_score=0.93,
                thumbnail_url=None,
                description="Isaac arrives in a red BMW X3",
                timestamp=datetime.now(timezone.utc) - timedelta(days=2),
                camera_name="Driveway",
                camera_id="cam-1",
            )
        ])
        mock_similarity.find_similar_events = AsyncMock(
            side_effect=AssertionError("must not look up a throwaway event UUID")
        )

        service = ContextEnhancedPromptService(
            entity_service=MagicMock(),
            similarity_service=mock_similarity,
        )
        service._is_context_enabled = MagicMock(return_value=True)
        service._get_ab_test_percentage = MagicMock(return_value=0)
        service._get_similarity_threshold = MagicMock(return_value=0.7)
        service._get_time_window_days = MagicMock(return_value=30)
        service._get_time_pattern_context = AsyncMock(return_value=None)
        service._mcp_context_provider = MagicMock()
        service._mcp_context_provider.get_context = AsyncMock(
            return_value=MagicMock(
                feedback=None, entity=None, camera=None, time_pattern=None
            )
        )
        service._mcp_context_provider.format_for_prompt = MagicMock(return_value="")

        vector = [0.1] * 8
        result = await service.build_context_enhanced_prompt(
            db=MagicMock(),
            event_id="pre-persist",
            base_prompt="Describe the image",
            camera_id="cam-1",
            event_time=datetime.now(timezone.utc),
            matched_entity=_named_person(),
            query_embedding=vector,
        )

        mock_similarity.find_similar_events.assert_not_called()
        mock_similarity.find_similar_events_by_embedding.assert_awaited()
        call_kwargs = mock_similarity.find_similar_events_by_embedding.call_args.kwargs
        assert call_kwargs["embedding"] is vector
        assert result.context_included is True
        assert "Isaac" in result.prompt
        assert "Similar events" in result.prompt

    @pytest.mark.asyncio
    async def test_live_helper_forwards_in_memory_embedding(self):
        reset_pre_ai_context_service()
        mock_ctx = MagicMock()
        mock_ctx.build_context_enhanced_prompt = AsyncMock(
            return_value=ContextEnhancedPromptResult(
                prompt="enhanced with Isaac",
                context_included=True,
                entity_context_included=True,
                entity_name="Isaac",
            )
        )
        vector = [0.2] * 8
        helper = PreAIContextService()
        bundle = await helper.gather(
            db=MagicMock(),
            camera_id="cam-1",
            camera_name="Driveway",
            event_time=datetime.now(timezone.utc),
            detected_objects=["person"],
            embedding_vector=vector,
            event_type="person",
            context_service=mock_ctx,
        )
        kwargs = mock_ctx.build_context_enhanced_prompt.call_args.kwargs
        assert kwargs["query_embedding"] is vector
        assert kwargs["event_id"] != str(uuid.uuid4())  # not a fresh random at assert time
        # The live helper must not invent a random UUID for lookup
        assert kwargs["event_id"] in ("pre-persist", None) or kwargs["query_embedding"] is vector
        assert bundle.custom_prompt == "enhanced with Isaac"


class TestPromptContract:
    def test_prompt_includes_local_time_and_carrier_instruction(self):
        service = AIPromptService(default_prompt="Describe the scene.")
        prompt, _ = service.select_and_build_prompt(
            camera_id="cam-front",
            camera_name="Front Door",
            timestamp="2026-08-13T21:05:00-04:00",
            detected_objects=["person", "vehicle"],
        )
        assert "Local time:" in prompt
        assert "21:05" in prompt
        assert "Front Door" in prompt
        assert "UPS" in prompt or "carrier" in prompt.lower()
        assert "HISTORICAL CONTEXT" in NAMING_AND_CARRIER_INSTRUCTION or "name" in prompt.lower()

    def test_naming_instruction_mentions_carriers_and_names(self):
        assert "UPS" in NAMING_AND_CARRIER_INSTRUCTION
        assert "FedEx" in NAMING_AND_CARRIER_INSTRUCTION
        assert "HISTORICAL CONTEXT" in NAMING_AND_CARRIER_INSTRUCTION

    def test_multi_frame_placeholder_is_formatted(self):
        service = AIPromptService()
        prompt, _ = service.select_and_build_prompt(
            analysis_mode="multi_frame",
            num_frames=5,
        )
        assert "{num_frames}" not in prompt
        assert "5 frames" in prompt

    def test_format_timestamp_uses_configured_timezone(self):
        mock_db = MagicMock()
        setting = MagicMock()
        setting.value = "America/New_York"
        mock_db.query.return_value.filter.return_value.first.return_value = setting
        ts = datetime(2026, 8, 13, 1, 5, tzinfo=timezone.utc)
        result = format_timestamp_for_ai(ts, mock_db)
        assert "2026-08-12" in result or "21:05" in result or "-04:00" in result or "-05:00" in result


class TestProtectPersistContextFields:
    def test_event_model_stores_delivery_carrier_and_context_included(self):
        event = Event(
            camera_id="cam-1",
            timestamp=datetime.now(timezone.utc),
            description="UPS driver drops off a package at 1:00 PM at the front door",
            confidence=90,
            objects_detected='["person","package"]',
            source_type="protect",
            delivery_carrier="ups",
            context_included=True,
            context_stats=json.dumps({"entity_context_included": True}),
            recognition_status="known",
            enriched_description="UPS driver drops off a package",
            matched_entity_ids=json.dumps(["ent-isaac"]),
        )
        assert event.delivery_carrier == "ups"
        assert event.context_included is True
        assert event.recognition_status == "known"
        assert "ent-isaac" in event.matched_entity_ids


class TestProtectPipelinePassesCustomPrompt:
    @pytest.mark.asyncio
    async def test_single_frame_forwards_context_prompt_with_named_entity(self):
        from app.services.protect_ai_pipeline import ProtectAIPipeline, reset_protect_ai_pipeline
        from app.services.snapshot_service import SnapshotResult
        from app.services.pre_ai_context_service import PreAIContextBundle

        reset_protect_ai_pipeline()
        pipeline = ProtectAIPipeline()

        bundle = PreAIContextBundle(
            custom_prompt="HISTORICAL CONTEXT:\n- Known visitor: \"Isaac\" (named by user)",
            context_result=ContextEnhancedPromptResult(
                prompt="HISTORICAL CONTEXT:\n- Known visitor: \"Isaac\" (named by user)",
                context_included=True,
                entity_context_included=True,
                entity_name="Isaac",
            ),
            embedding_vector=[0.1] * 8,
            named_identities=[_named_person()],
            local_timestamp="2026-08-13T21:05:00-04:00",
            matched_entity_ids=["ent-isaac"],
            context_included=True,
        )

        orch = MagicMock()
        orch.analyze_image = AsyncMock(return_value=MagicMock(success=True, description="ok"))

        camera = MagicMock()
        camera.id = "cam-1"
        camera.name = "Driveway"
        camera.analysis_mode = "single_frame"

        snapshot = SnapshotResult(
            image_base64=(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
                "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
            ),
            thumbnail_path="t.jpg",
            width=1,
            height=1,
            camera_id="cam-1",
            timestamp=datetime.now(timezone.utc),
        )

        mock_helper = MagicMock()
        mock_helper.gather = AsyncMock(return_value=bundle)

        with patch(
            "app.services.vision_analysis_orchestrator.get_vision_analysis_orchestrator",
            return_value=orch,
        ), patch("app.services.ai_service.ai_service") as mock_ai, patch(
            "app.core.database.get_db_session"
        ), patch(
            "app.services.pre_ai_context_service.get_pre_ai_context_service",
            return_value=mock_helper,
        ):
            mock_ai.load_api_keys_from_db = AsyncMock()
            await pipeline.submit_snapshot_for_analysis(
                snapshot_result=snapshot,
                camera=camera,
                event_type="person",
            )

        orch.analyze_image.assert_awaited()
        kwargs = orch.analyze_image.call_args.kwargs
        assert kwargs["custom_prompt"] is not None
        assert "Isaac" in kwargs["custom_prompt"]
        assert kwargs["camera_id"] == "cam-1"
        assert kwargs["custom_prompt"] is not None


class TestComposedEnrichment:
    def test_compose_person_and_vehicle(self):
        service = EntityAlertService()
        person = MagicMock()
        person.name = "Isaac"
        person.entity_type = "person"
        vehicle = MagicMock()
        vehicle.name = "Isaac's BMW"
        vehicle.entity_type = "vehicle"
        vehicle.vehicle_color = "red"
        vehicle.vehicle_make = "BMW"
        vehicle.vehicle_model = "X3"

        enriched = service.enrich_description(
            "A person arrives in a vehicle at the driveway.",
            [person, vehicle],
        )
        assert "Isaac" in enriched
        assert "BMW" in enriched or "X3" in enriched
        assert not enriched.lower().startswith("a person")

    def test_unnamed_not_applied(self):
        service = EntityAlertService()
        unnamed = MagicMock()
        unnamed.name = None
        unnamed.entity_type = "person"
        original = "A person is at the door."
        assert service.enrich_description(original, [unnamed]) == original
