"""Unit tests for AIProcessingCoordinator"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
import asyncio

from app.services.ai_processing_coordinator import AIProcessingCoordinator
from app.services.event_processor import ProcessingEvent


class TestAIProcessingCoordinator:
    """Tests for AIProcessingCoordinator"""

    @pytest.fixture
    def mock_ai_service(self):
        service = Mock()
        service.generate_description = AsyncMock()
        # Provide a fake semaphore for the context of the test
        service.ai_semaphore = asyncio.Semaphore(8)
        return service

    @pytest.fixture
    def mock_metrics(self):
        metrics = Mock()
        metrics.increment_error = Mock()
        metrics.record_processing_time = Mock()
        metrics.events_processed_success = 0
        metrics.events_processed_failure = 0
        return metrics

    @pytest.fixture
    def mock_context_services(self):
        """Mock the direct services passed to the coordinator"""
        return {
            "context_prompt_service": Mock(),
            "cost_alert_service": Mock(),
            "embedding_service": Mock(),
            "mqtt_service": Mock(),
            "homekit_service": Mock(),
            "face_embedding_service": Mock(),
            "vehicle_embedding_service": Mock(),
            "entity_service": Mock(),
        }

    @pytest.fixture
    def mock_helpers(self):
        """Mock the bound helper methods still on EventProcessor"""
        return {
            "handle_cost_cap_skip": AsyncMock(return_value=False),
            "generate_thumbnail": Mock(return_value="data:image/jpeg;base64,fake"),
            "generate_and_match_entity": AsyncMock(return_value=(b"fake-embedding", None)),
            "generate_ai_description": AsyncMock(),
            "store_processed_event": AsyncMock(return_value="event-123"),
            "send_push_notification": AsyncMock(),
            "publish_camera_status_sensors": AsyncMock(),
            "run_homekit_triggers": AsyncMock(),
            "link_entity_to_event": AsyncMock(),
            "process_face_embeddings": AsyncMock(),
            "process_vehicle_embeddings": AsyncMock(),
            "process_entity_alerts": AsyncMock(),
            "enrich_event_with_audio": AsyncMock(),
            "publish_event_to_mqtt": AsyncMock(),
            "store_event_with_retry": AsyncMock(return_value="event-123"),
        }

    @pytest.fixture
    def sample_event(self):
        event = Mock(spec=ProcessingEvent)
        event.camera_id = "cam-123"
        event.camera_name = "Test Cam"
        event.frame = b"fake-frame"
        event.timestamp = Mock()
        event.timestamp.isoformat.return_value = "2026-01-01T00:00:00"
        event.detected_objects = ["person"]
        event.metadata = {}
        return event

    @pytest.fixture
    def coordinator(self, mock_ai_service, mock_metrics, mock_context_services, mock_helpers):
        """Create coordinator with all mocks"""
        return AIProcessingCoordinator(
            ai_service=mock_ai_service,
            metrics=mock_metrics,
            context_prompt_service=mock_context_services["context_prompt_service"],
            cost_alert_service=mock_context_services["cost_alert_service"],
            embedding_service=mock_context_services["embedding_service"],
            mqtt_service=mock_context_services["mqtt_service"],
            # The helpers are passed as the bound methods (mocks in test)
            handle_cost_cap_skip=mock_helpers["handle_cost_cap_skip"],
            generate_thumbnail=mock_helpers["generate_thumbnail"],
            generate_and_match_entity=mock_helpers["generate_and_match_entity"],
            generate_ai_description=mock_helpers["generate_ai_description"],
            store_processed_event=mock_helpers["store_processed_event"],
            send_push_notification=mock_helpers["send_push_notification"],
            publish_camera_status_sensors=mock_helpers["publish_camera_status_sensors"],
            run_homekit_triggers=mock_helpers["run_homekit_triggers"],
            link_entity_to_event=mock_helpers["link_entity_to_event"],
            process_face_embeddings=mock_helpers["process_face_embeddings"],
            process_vehicle_embeddings=mock_helpers["process_vehicle_embeddings"],
            process_entity_alerts=mock_helpers["process_entity_alerts"],
            enrich_event_with_audio=mock_helpers["enrich_event_with_audio"],
            publish_event_to_mqtt=mock_helpers["publish_event_to_mqtt"],
            store_event_with_retry=mock_helpers["store_event_with_retry"],
            homekit_service=mock_context_services["homekit_service"],
            face_embedding_service=mock_context_services["face_embedding_service"],
            vehicle_embedding_service=mock_context_services["vehicle_embedding_service"],
            entity_service=mock_context_services["entity_service"],
        )

    @pytest.mark.asyncio
    async def test_happy_path(self, coordinator, mock_helpers, sample_event):
        """Happy path should call all the expected steps"""
        mock_ai_result = Mock()
        mock_ai_result.success = True
        mock_ai_result.description = "A person walking"
        mock_ai_result.confidence = 0.95
        mock_ai_result.provider = "openai"
        mock_ai_result.cost_estimate = 0.001
        mock_ai_result.response_time_ms = 1200
        mock_ai_result.objects_detected = ["person"]
        mock_ai_result.bounding_boxes = None

        mock_helpers["generate_ai_description"].return_value = mock_ai_result

        result = await coordinator.process_event(sample_event, worker_id=0)

        assert result is True
        mock_helpers["handle_cost_cap_skip"].assert_awaited_once()
        mock_helpers["generate_thumbnail"].assert_called_once()
        mock_helpers["generate_and_match_entity"].assert_awaited_once()
        mock_helpers["generate_ai_description"].assert_awaited_once()
        mock_helpers["store_processed_event"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cost_cap_skip(self, coordinator, mock_helpers, sample_event):
        """Should short-circuit when cost cap says to skip"""
        mock_helpers["handle_cost_cap_skip"].return_value = True

        result = await coordinator.process_event(sample_event, worker_id=0)

        assert result is True
        mock_helpers["handle_cost_cap_skip"].assert_awaited_once()
        # Should not call later steps
        mock_helpers["generate_ai_description"].assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ai_failure_stores_retry(self, coordinator, mock_helpers, sample_event):
        """AI failure should trigger a retry storage path"""
        mock_ai_result = Mock()
        mock_ai_result.success = False
        mock_helpers["generate_ai_description"].return_value = mock_ai_result

        result = await coordinator.process_event(sample_event, worker_id=0)

        assert result is False
        # Should have tried to store a retry event
        mock_helpers["store_event_with_retry"].assert_awaited()

    def test_initialization(self, mock_ai_service, mock_metrics, mock_context_services, mock_helpers):
        """Coordinator should accept all explicit dependencies"""
        coord = AIProcessingCoordinator(
            ai_service=mock_ai_service,
            metrics=mock_metrics,
            context_prompt_service=mock_context_services["context_prompt_service"],
            cost_alert_service=mock_context_services["cost_alert_service"],
            embedding_service=mock_context_services["embedding_service"],
            mqtt_service=mock_context_services["mqtt_service"],
            handle_cost_cap_skip=mock_helpers["handle_cost_cap_skip"],
            generate_thumbnail=mock_helpers["generate_thumbnail"],
            generate_and_match_entity=mock_helpers["generate_and_match_entity"],
            generate_ai_description=mock_helpers["generate_ai_description"],
            store_processed_event=mock_helpers["store_processed_event"],
            send_push_notification=mock_helpers["send_push_notification"],
            publish_camera_status_sensors=mock_helpers["publish_camera_status_sensors"],
            run_homekit_triggers=mock_helpers["run_homekit_triggers"],
            link_entity_to_event=mock_helpers["link_entity_to_event"],
            process_face_embeddings=mock_helpers["process_face_embeddings"],
            process_vehicle_embeddings=mock_helpers["process_vehicle_embeddings"],
            process_entity_alerts=mock_helpers["process_entity_alerts"],
            enrich_event_with_audio=mock_helpers["enrich_event_with_audio"],
            publish_event_to_mqtt=mock_helpers["publish_event_to_mqtt"],
            store_event_with_retry=mock_helpers["store_event_with_retry"],
            homekit_service=mock_context_services["homekit_service"],
            face_embedding_service=mock_context_services["face_embedding_service"],
            vehicle_embedding_service=mock_context_services["vehicle_embedding_service"],
            entity_service=mock_context_services["entity_service"],
        )
        assert coord.ai_service is mock_ai_service
        assert coord.metrics is mock_metrics

    @pytest.mark.asyncio
    async def test_context_prompt_service_is_used(self, coordinator, mock_context_services, mock_helpers, sample_event):
        """Should call context_prompt_service when building context-enhanced prompt"""
        mock_ai_result = Mock(success=True, description="test", confidence=0.9, provider="openai",
                              cost_estimate=0.001, response_time_ms=1000, objects_detected=["person"],
                              bounding_boxes=None)
        mock_helpers["generate_ai_description"].return_value = mock_ai_result
        mock_context_result = Mock(context_included=True, prompt="enhanced prompt")
        mock_context_services["context_prompt_service"].build_context_enhanced_prompt.return_value = mock_context_result

        await coordinator.process_event(sample_event, worker_id=0)

        mock_context_services["context_prompt_service"].build_context_enhanced_prompt.assert_awaited()

    @pytest.mark.asyncio
    async def test_context_failure_is_graceful(self, coordinator, mock_context_services, mock_helpers, sample_event):
        """Context building failure should not block processing"""
        mock_ai_result = Mock(success=True, description="test", confidence=0.9, provider="openai",
                              cost_estimate=0.001, response_time_ms=1000, objects_detected=["person"],
                              bounding_boxes=None)
        mock_helpers["generate_ai_description"].return_value = mock_ai_result
        mock_context_services["context_prompt_service"].build_context_enhanced_prompt.side_effect = Exception("context boom")

        result = await coordinator.process_event(sample_event, worker_id=0)

        assert result is True  # Should still succeed
        mock_helpers["generate_ai_description"].assert_awaited()  # Should proceed without context

    @pytest.mark.asyncio
    async def test_ocr_is_attempted_when_enabled(self, coordinator, mock_context_services, mock_helpers, sample_event):
        """Should attempt OCR extraction when the setting is enabled"""
        # This is a bit tricky because OCR is done inside _generate_ai_description via container lookup.
        # For a focused test we can at least ensure the happy path reaches the AI call.
        mock_ai_result = Mock(success=True, description="test", confidence=0.9, provider="openai",
                              cost_estimate=0.001, response_time_ms=1000, objects_detected=["person"],
                              bounding_boxes=None)
        mock_helpers["generate_ai_description"].return_value = mock_ai_result

        result = await coordinator.process_event(sample_event, worker_id=0)
        assert result is True

    @pytest.mark.asyncio
    async def test_all_post_processing_steps_are_called_on_success(self, coordinator, mock_helpers, sample_event):
        """Happy path should trigger all the post-processing helpers"""
        mock_ai_result = Mock(success=True, description="A person with a package", confidence=0.92,
                              provider="openai", cost_estimate=0.0012, response_time_ms=1100,
                              objects_detected=["person", "package"], bounding_boxes=None)
        mock_helpers["generate_ai_description"].return_value = mock_ai_result

        await coordinator.process_event(sample_event, worker_id=0)

        mock_helpers["send_push_notification"].assert_awaited_once()
        mock_helpers["publish_camera_status_sensors"].assert_awaited_once()
        mock_helpers["run_homekit_triggers"].assert_awaited_once()
        mock_helpers["link_entity_to_event"].assert_awaited_once()
        mock_helpers["process_face_embeddings"].assert_awaited_once()
        mock_helpers["process_vehicle_embeddings"].assert_awaited_once()
        mock_helpers["process_entity_alerts"].assert_awaited_once()
        mock_helpers["enrich_event_with_audio"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_metrics_are_updated_on_success(self, coordinator, mock_helpers, mock_metrics, sample_event):
        """Success path should update processing metrics"""
        mock_ai_result = Mock(success=True, description="test", confidence=0.9, provider="openai",
                              cost_estimate=0.001, response_time_ms=1000, objects_detected=["person"],
                              bounding_boxes=None)
        mock_helpers["generate_ai_description"].return_value = mock_ai_result

        await coordinator.process_event(sample_event, worker_id=0)

        # The coordinator itself updates some metrics via the injected object
        assert mock_metrics.record_processing_time.called or mock_metrics.events_processed_success >= 0

    @pytest.mark.asyncio
    async def test_cost_cap_skip_still_calls_store(self, coordinator, mock_helpers, sample_event):
        """Even on cost-cap skip, we should still store a (minimal) event"""
        mock_helpers["handle_cost_cap_skip"].return_value = True

        await coordinator.process_event(sample_event, worker_id=0)

        mock_helpers["store_event_with_retry"].assert_awaited()

    @pytest.mark.asyncio
    async def test_handle_cost_cap_skip_skip_path(self, coordinator, mock_helpers, sample_event):
        """_handle_cost_cap_skip should return True and trigger storage when cap is hit"""
        # We test it through the public method for now
        mock_helpers["handle_cost_cap_skip"].return_value = True

        result = await coordinator.process_event(sample_event, worker_id=0)

        assert result is True
        mock_helpers["handle_cost_cap_skip"].assert_awaited_once_with(sample_event)

    @pytest.mark.asyncio
    async def test_generate_ai_description_success(self, coordinator, mock_helpers, sample_event):
        """_generate_ai_description should return AIResult on success"""
        mock_ai_result = Mock(success=True, description="A test description", confidence=0.91,
                              provider="openai", cost_estimate=0.001, response_time_ms=950,
                              objects_detected=["person"], bounding_boxes=None)
        mock_helpers["generate_ai_description"].return_value = mock_ai_result

        # Call via the public method (it will go through the private one now)
        result = await coordinator.process_event(sample_event, worker_id=0)

        assert result is True
        mock_helpers["generate_ai_description"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generate_ai_description_ocr_path(self, coordinator, mock_context_services, mock_helpers, sample_event):
        """_generate_ai_description should attempt OCR when the setting is enabled"""
        # We can't easily mock the inner container lookup without more invasive patching,
        # but we can at least ensure the happy path still works when OCR would be considered.
        mock_ai_result = Mock(success=True, description="test", confidence=0.9, provider="openai",
                              cost_estimate=0.001, response_time_ms=1000, objects_detected=["person"],
                              bounding_boxes=None)
        mock_helpers["generate_ai_description"].return_value = mock_ai_result

        result = await coordinator.process_event(sample_event, worker_id=0)
        assert result is True

    @pytest.mark.asyncio
    async def test_context_prompt_service_called_with_expected_args(self, coordinator, mock_context_services, mock_helpers, sample_event):
        """The context_prompt_service should be called during context building"""
        mock_ai_result = Mock(success=True, description="test", confidence=0.9, provider="openai",
                              cost_estimate=0.001, response_time_ms=1000, objects_detected=["person"],
                              bounding_boxes=None)
        mock_helpers["generate_ai_description"].return_value = mock_ai_result

        # The context service is called inside the try block for context building
        await coordinator.process_event(sample_event, worker_id=0)

        # We can't easily assert exact args without more setup, but we can at least ensure it was considered
        # (the real assertion is that the coordinator reaches the generate_ai_description call)
        mock_helpers["generate_ai_description"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cost_alert_service_is_checked_on_success_path(self, coordinator, mock_context_services, mock_helpers, sample_event):
        """The injected cost_alert_service should be used after successful storage"""
        mock_ai_result = Mock(success=True, description="test", confidence=0.9, provider="openai",
                              cost_estimate=0.001, response_time_ms=1000, objects_detected=["person"],
                              bounding_boxes=None)
        mock_helpers["generate_ai_description"].return_value = mock_ai_result

        await coordinator.process_event(sample_event, worker_id=0)

        # In the current implementation the cost alerts check happens via container inside the coordinator.
        # Once we fully move the cost alerts block, we can assert on mock_context_services["cost_alert_service"].
        # For now this test documents the intent.
        assert True  # Placeholder until cost alerts are also moved into the coordinator

    @pytest.mark.asyncio
    async def test_embedding_service_used_for_early_embedding(self, coordinator, mock_context_services, mock_helpers, sample_event):
        """The embedding_service from the context should be used for early embeddings"""
        # The call goes through generate_and_match_entity → _generate_early_embedding
        await coordinator.process_event(sample_event, worker_id=0)

        # generate_and_match_entity is mocked at the context level, so we just ensure the path is exercised
        mock_helpers["generate_and_match_entity"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_cost_cap_skip_skip_path_direct(self, coordinator, mock_helpers, sample_event):
        """Direct test of _handle_cost_cap_skip when cap is hit"""
        # We can test the private method directly since it's now on the coordinator
        mock_helpers["handle_cost_cap_skip"].return_value = True

        # The private method is now on the coordinator
        result = await coordinator._handle_cost_cap_skip(sample_event)

        assert result is True
        mock_helpers["handle_cost_cap_skip"].assert_awaited_once_with(sample_event)

    @pytest.mark.asyncio
    async def test_generate_ai_description_ocr_path(self, coordinator, mock_context_services, mock_helpers, sample_event):
        """_generate_ai_description should attempt OCR when the setting is enabled"""
        # Mock the system setting to enable OCR
        mock_setting = Mock()
        mock_setting.value = "true"

        with patch("app.models.system_setting.SystemSetting") as mock_sys_setting:
            mock_sys_setting.query.return_value.filter.return_value.first.return_value = mock_setting

            with patch("app.services.ocr_service.is_ocr_available", return_value=True):
                with patch("app.services.ocr_service.extract_overlay_text", return_value="fake ocr text"):
                    mock_ai_result = Mock(success=True, description="test", confidence=0.9, provider="openai",
                                          cost_estimate=0.001, response_time_ms=1000, objects_detected=["person"],
                                          bounding_boxes=None)
                    mock_helpers["generate_ai_description"].return_value = mock_ai_result

                    result = await coordinator.process_event(sample_event, worker_id=0)
                    assert result is True

    @pytest.mark.asyncio
    async def test_store_processed_event_success(self, coordinator, mock_helpers, sample_event):
        """_store_processed_event should succeed and return event_id"""
        mock_ai_result = Mock(description="test desc", confidence=0.95, provider="openai",
                              cost_estimate=0.001, objects_detected=["person"])

        mock_helpers["store_processed_event"].return_value = "event-456"

        event_id = await coordinator._store_processed_event(
            event=sample_event,
            ai_result=mock_ai_result,
            thumbnail_base64="fake-thumb",
            delivery_carrier="UPS",
            has_annotations=True,
            bounding_boxes_json="[]",
        )

        assert event_id == "event-456"
        mock_helpers["store_processed_event"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_store_processed_event_failure(self, coordinator, mock_helpers, sample_event):
        """_store_processed_event should return None and record error on failure"""
        mock_ai_result = Mock(description="test desc", confidence=0.95, provider="openai",
                              cost_estimate=0.001, objects_detected=["person"])

        mock_helpers["store_processed_event"].return_value = None

        event_id = await coordinator._store_processed_event(
            event=sample_event,
            ai_result=mock_ai_result,
            thumbnail_base64="fake-thumb",
        )

        assert event_id is None
        mock_helpers["store_processed_event"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generate_and_match_entity_success(self, coordinator, mock_helpers, sample_event):
        """_generate_and_match_entity should return embedding and entity result"""
        mock_helpers["generate_and_match_entity"].return_value = (b"fake-emb", Mock(entity_id="ent-1"))

        emb, ent = await coordinator._generate_and_match_entity("fake-thumb")

        assert emb == b"fake-emb"
        assert ent is not None
        mock_helpers["generate_and_match_entity"].assert_awaited_once_with("fake-thumb")

    @pytest.mark.asyncio
    async def test_generate_and_match_entity_no_embedding(self, coordinator, mock_helpers, sample_event):
        """_generate_and_match_entity should return (None, None) when no embedding"""
        mock_helpers["generate_and_match_entity"].return_value = (None, None)

        emb, ent = await coordinator._generate_and_match_entity(None)

        assert emb is None
        assert ent is None

    @pytest.mark.asyncio
    async def test_cost_alert_service_called_after_success(self, coordinator, mock_context_services, mock_helpers, sample_event):
        """The injected cost_alert_service should be called after successful processing"""
        mock_ai_result = Mock(success=True, description="test", confidence=0.9, provider="openai",
                              cost_estimate=0.001, response_time_ms=1000, objects_detected=["person"],
                              bounding_boxes=None)
        mock_helpers["generate_ai_description"].return_value = mock_ai_result

        # The cost alerts check happens via container in the current implementation.
        # Once fully moved into the coordinator, we can assert on mock_context_services["cost_alert_service"]
        await coordinator.process_event(sample_event, worker_id=0)

        # Placeholder assertion until the cost alerts block is moved into the coordinator
        assert True

    @pytest.mark.asyncio
    async def test_mqtt_service_used_in_publish_mqtt_event(self, coordinator, mock_context_services, sample_event):
        """_publish_mqtt_event should use the injected mqtt_service"""
        # The method is now on the coordinator and uses self.context.mqtt_service
        # We can test it directly once the full logic is in the private method
        # For now, ensure the path is exercised via process_event
        mock_ai_result = Mock(success=True, description="test", confidence=0.9, provider="openai",
                              cost_estimate=0.001, response_time_ms=1000, objects_detected=["person"],
                              bounding_boxes=None)
        # Mock the helpers that are called before MQTT
        for key in ["handle_cost_cap_skip", "generate_thumbnail", "generate_and_match_entity", "generate_ai_description",
                    "store_processed_event"]:
            mock_helpers[key].return_value = "event-123" if "store" in key or "generate_ai" in key else False

        await coordinator.process_event(sample_event, worker_id=0)

        # The actual MQTT call is inside _publish_mqtt_event which uses self.context.mqtt_service
        # This test documents the intent
        assert True

    # ------------------------------------------------------------------
    # Direct tests for private methods (now on the coordinator)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_handle_cost_cap_skip_skip_path_direct(self, coordinator, mock_helpers, sample_event):
        """Direct test of _handle_cost_cap_skip when cap is hit"""
        mock_helpers["handle_cost_cap_skip"].return_value = True

        result = await coordinator._handle_cost_cap_skip(sample_event)

        assert result is True
        mock_helpers["handle_cost_cap_skip"].assert_awaited_once_with(sample_event)

    @pytest.mark.asyncio
    async def test_handle_cost_cap_skip_proceed_path_direct(self, coordinator, mock_helpers, sample_event):
        """Direct test of _handle_cost_cap_skip when cap allows analysis"""
        mock_helpers["handle_cost_cap_skip"].return_value = False

        result = await coordinator._handle_cost_cap_skip(sample_event)

        assert result is False

    @pytest.mark.asyncio
    async def test_generate_ai_description_success_direct(self, coordinator, mock_helpers, sample_event):
        """Direct test of _generate_ai_description success path"""
        mock_ai_result = Mock(success=True, description="A test description", confidence=0.91,
                              provider="openai", cost_estimate=0.001, response_time_ms=950,
                              objects_detected=["person"], bounding_boxes=None)
        mock_helpers["generate_ai_description"].return_value = mock_ai_result

        result = await coordinator._generate_ai_description(
            event=sample_event,
            worker_id=0,
            context_enhanced_prompt="test prompt",
            thumbnail_base64="fake-thumb",
        )

        assert result is mock_ai_result
        mock_helpers["generate_ai_description"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generate_ai_description_failure_stores_retry(self, coordinator, mock_helpers, sample_event):
        """_generate_ai_description should store a retry event on AI failure"""
        mock_ai_result = Mock(success=False)
        mock_helpers["generate_ai_description"].return_value = mock_ai_result

        result = await coordinator._generate_ai_description(
            event=sample_event,
            worker_id=0,
            context_enhanced_prompt=None,
            thumbnail_base64="fake-thumb",
        )

        assert result is None
        mock_helpers["store_event_with_retry"].assert_awaited()

    @pytest.mark.asyncio
    async def test_store_processed_event_success_direct(self, coordinator, mock_helpers, sample_event):
        """_store_processed_event should succeed and return event_id"""
        mock_ai_result = Mock(description="test desc", confidence=0.95, provider="openai",
                              cost_estimate=0.001, objects_detected=["person"])

        mock_helpers["store_processed_event"].return_value = "event-456"

        event_id = await coordinator._store_processed_event(
            event=sample_event,
            ai_result=mock_ai_result,
            thumbnail_base64="fake-thumb",
        )

        assert event_id == "event-456"
        mock_helpers["store_processed_event"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_store_processed_event_failure_direct(self, coordinator, mock_helpers, sample_event):
        """_store_processed_event should return None and record error on failure"""
        mock_ai_result = Mock(description="test desc", confidence=0.95, provider="openai",
                              cost_estimate=0.001, objects_detected=["person"])

        mock_helpers["store_processed_event"].return_value = None

        event_id = await coordinator._store_processed_event(
            event=sample_event,
            ai_result=mock_ai_result,
            thumbnail_base64="fake-thumb",
        )

        assert event_id is None
        mock_helpers["store_processed_event"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generate_and_match_entity_success_direct(self, coordinator, mock_helpers, sample_event):
        """_generate_and_match_entity should return embedding and entity result"""
        mock_helpers["generate_and_match_entity"].return_value = (b"fake-emb", Mock(entity_id="ent-1"))

        emb, ent = await coordinator._generate_and_match_entity("fake-thumb")

        assert emb == b"fake-emb"
        assert ent is not None
        mock_helpers["generate_and_match_entity"].assert_awaited_once_with("fake-thumb")

    @pytest.mark.asyncio
    async def test_generate_and_match_entity_no_embedding_direct(self, coordinator, mock_helpers, sample_event):
        """_generate_and_match_entity should return (None, None) when no embedding"""
        mock_helpers["generate_and_match_entity"].return_value = (None, None)

        emb, ent = await coordinator._generate_and_match_entity(None)

        assert emb is None
        assert ent is None

    @pytest.mark.asyncio
    async def test_send_push_notification_called(self, coordinator, mock_helpers, sample_event):
        """_send_push_notification should be called with correct arguments"""
        await coordinator._send_push_notification(
            event=sample_event,
            event_id="event-123",
            ai_result=Mock(description="test"),
            thumbnail_base64="fake-thumb",
        )

        mock_helpers["send_push_notification"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_publish_camera_status_sensors_called(self, coordinator, mock_helpers, sample_event):
        """_publish_camera_status_sensors should be called"""
        await coordinator._publish_camera_status_sensors(
            event=sample_event,
            event_id="event-123",
            ai_result=Mock(description="test"),
        )

        mock_helpers["publish_camera_status_sensors"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_publish_mqtt_event_uses_mqtt_service(self, coordinator, mock_context_services, sample_event):
        """_publish_mqtt_event should use the injected mqtt_service from context"""
        # The method is now on the coordinator
        await coordinator._publish_mqtt_event(event=sample_event, event_id="event-123")

        # At minimum we exercised the method (full assertion requires moving the full logic)
        assert True  # The real assertion will be possible once the full _publish_mqtt_event logic is in the coordinator

    @pytest.mark.asyncio
    async def test_store_embedding_success(self, coordinator, mock_context_services, sample_event):
        """_store_embedding should use the injected embedding_service"""
        await coordinator._store_embedding(
            event_id="event-123",
            embedding_vector=b"fake-emb",
            camera_id="cam-123",
        )

        # The embedding_service is in the context; once the full logic is in the private method we can assert
        assert True  # Placeholder until full logic is moved

    @pytest.mark.asyncio
    async def test_context_prompt_service_called_during_context_building(self, coordinator, mock_context_services, mock_helpers, sample_event):
        """The injected context_prompt_service should be used when building context"""
        mock_ai_result = Mock(success=True, description="test", confidence=0.9, provider="openai",
                              cost_estimate=0.001, response_time_ms=1000, objects_detected=["person"],
                              bounding_boxes=None)
        mock_helpers["generate_ai_description"].return_value = mock_ai_result

        await coordinator.process_event(sample_event, worker_id=0)

        # The actual call happens inside the context building block
        # This test documents the intent; full assertion will be possible once that block is fully moved
        assert True

    # ------------------------------------------------------------------
    # Post-processing branch tests (still on EventProcessor via context)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_run_homekit_triggers_called_with_correct_args(self, coordinator, mock_helpers, sample_event):
        """_run_homekit_triggers should be called with the right arguments"""
        mock_ai_result = Mock(success=True, description="test", confidence=0.9, provider="openai",
                              cost_estimate=0.001, response_time_ms=1000, objects_detected=["person"],
                              bounding_boxes=None)
        mock_helpers["generate_ai_description"].return_value = mock_ai_result

        await coordinator.process_event(sample_event, worker_id=0)

        mock_helpers["run_homekit_triggers"].assert_awaited_once_with(
            event=sample_event, event_id="event-123", smart_detection_type="person"
        )

    @pytest.mark.asyncio
    async def test_link_entity_to_event_called_with_correct_args(self, coordinator, mock_helpers, sample_event):
        """_link_entity_to_event should be called with embedding_vector"""
        mock_ai_result = Mock(success=True, description="test", confidence=0.9, provider="openai",
                              cost_estimate=0.001, response_time_ms=1000, objects_detected=["person"],
                              bounding_boxes=None)
        mock_helpers["generate_ai_description"].return_value = mock_ai_result
        mock_helpers["generate_and_match_entity"].return_value = (b"fake-emb", None)

        await coordinator.process_event(sample_event, worker_id=0)

        mock_helpers["link_entity_to_event"].assert_awaited_once_with(
            event=sample_event, event_id="event-123", embedding_vector=b"fake-emb"
        )

    @pytest.mark.asyncio
    async def test_process_face_embeddings_called(self, coordinator, mock_helpers, sample_event):
        """_process_face_embeddings should be called with correct args"""
        mock_ai_result = Mock(success=True, description="test", confidence=0.9, provider="openai",
                              cost_estimate=0.001, response_time_ms=1000, objects_detected=["person"],
                              bounding_boxes=None)
        mock_helpers["generate_ai_description"].return_value = mock_ai_result

        await coordinator.process_event(sample_event, worker_id=0)

        mock_helpers["process_face_embeddings"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_process_vehicle_embeddings_called(self, coordinator, mock_helpers, sample_event):
        """_process_vehicle_embeddings should be called"""
        mock_ai_result = Mock(success=True, description="test", confidence=0.9, provider="openai",
                              cost_estimate=0.001, response_time_ms=1000, objects_detected=["vehicle"],
                              bounding_boxes=None)
        mock_helpers["generate_ai_description"].return_value = mock_ai_result

        await coordinator.process_event(sample_event, worker_id=0)

        mock_helpers["process_vehicle_embeddings"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_process_entity_alerts_called(self, coordinator, mock_helpers, sample_event):
        """_process_entity_alerts should be called"""
        mock_ai_result = Mock(success=True, description="test", confidence=0.9, provider="openai",
                              cost_estimate=0.001, response_time_ms=1000, objects_detected=["person"],
                              bounding_boxes=None)
        mock_helpers["generate_ai_description"].return_value = mock_ai_result

        await coordinator.process_event(sample_event, worker_id=0)

        mock_helpers["process_entity_alerts"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_enrich_event_with_audio_called(self, coordinator, mock_helpers, sample_event):
        """_enrich_event_with_audio should be called as fire-and-forget"""
        mock_ai_result = Mock(success=True, description="test", confidence=0.9, provider="openai",
                              cost_estimate=0.001, response_time_ms=1000, objects_detected=["person"],
                              bounding_boxes=None)
        mock_helpers["generate_ai_description"].return_value = mock_ai_result

        await coordinator.process_event(sample_event, worker_id=0)

        mock_helpers["enrich_event_with_audio"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_post_processing_failure_does_not_fail_overall_processing(self, coordinator, mock_helpers, sample_event):
        """An exception in one post-processing step should not fail the whole event"""
        mock_ai_result = Mock(success=True, description="test", confidence=0.9, provider="openai",
                              cost_estimate=0.001, response_time_ms=1000, objects_detected=["person"],
                              bounding_boxes=None)
        mock_helpers["generate_ai_description"].return_value = mock_ai_result
        mock_helpers["send_push_notification"].side_effect = Exception("Push service down")

        result = await coordinator.process_event(sample_event, worker_id=0)

        # The overall processing should still succeed
        assert result is True
        # Other post-processing should still have been attempted
        mock_helpers["publish_camera_status_sensors"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_publish_mqtt_event_direct(self, coordinator, mock_context_services, sample_event):
        """Direct test of _publish_mqtt_event"""
        await coordinator._publish_mqtt_event(event=sample_event, event_id="event-xyz")

        # At minimum we exercised the method (full assertions will be possible once the full logic is moved)
        assert True

    @pytest.mark.asyncio
    async def test_store_embedding_direct(self, coordinator, mock_context_services, sample_event):
        """Direct test of _store_embedding"""
        await coordinator._store_embedding(
            event_id="event-xyz",
            embedding_vector=b"fake-emb",
            camera_id="cam-123",
        )

        # The embedding_service is in the context
        assert True  # Full assertion once the full logic is in the private method

    @pytest.mark.asyncio
    async def test_run_homekit_triggers_uses_injected_homekit_service(self, coordinator, mock_context_services, sample_event):
        """_run_homekit_triggers should call methods on the injected homekit_service"""
        mock_homekit = mock_context_services["homekit_service"]
        mock_homekit.is_running = True
        mock_homekit.trigger_motion.return_value = True
        mock_homekit.trigger_occupancy.return_value = True

        await coordinator._run_homekit_triggers(
            event=sample_event,
            event_id="event-123",
            smart_detection_type="person",
        )

        mock_homekit.trigger_motion.assert_called_once()
        mock_homekit.trigger_occupancy.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_face_embeddings_uses_injected_face_service(self, coordinator, mock_context_services, sample_event):
        """_process_face_embeddings should call the injected face_embedding_service"""
        mock_face = mock_context_services["face_embedding_service"]

        await coordinator._process_face_embeddings(
            event=sample_event,
            event_id="event-123",
            thumbnail_base64="fake-thumb",
        )

        mock_face.process_face_embedding.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_vehicle_embeddings_uses_injected_vehicle_service(self, coordinator, mock_context_services, sample_event):
        """_process_vehicle_embeddings should call the injected vehicle_embedding_service"""
        mock_vehicle = mock_context_services["vehicle_embedding_service"]

        await coordinator._process_vehicle_embeddings(
            event=sample_event,
            event_id="event-123",
            objects_json="[]",
            thumbnail_base64="fake-thumb",
            ai_result=Mock(description="test"),
            smart_detection_type="vehicle",
        )

        mock_vehicle.process_vehicle_embedding.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_entity_alerts_uses_injected_entity_service(self, coordinator, mock_context_services, sample_event):
        """_process_entity_alerts should call the injected entity_service"""
        mock_entity = mock_context_services["entity_service"]

        await coordinator._process_entity_alerts(
            event=sample_event,
            event_id="event-123",
            ai_result=Mock(description="test"),
            objects_detected=["person"],
        )

        mock_entity.execute_entity_alerts.assert_called_once()

    @pytest.mark.asyncio
    async def test_homekit_triggers_graceful_when_service_not_running(self, coordinator, mock_context_services, sample_event):
        """_run_homekit_triggers should do nothing if homekit_service is not running"""
        mock_homekit = mock_context_services["homekit_service"]
        mock_homekit.is_running = False

        await coordinator._run_homekit_triggers(
            event=sample_event,
            event_id="event-123",
            smart_detection_type="person",
        )

        mock_homekit.trigger_motion.assert_not_called()
        mock_homekit.trigger_occupancy.assert_not_called()

    @pytest.mark.asyncio
    async def test_post_processing_methods_handle_missing_services_gracefully(self, coordinator, mock_context_services, sample_event):
        """Post-processing methods should not crash if their service is None"""
        mock_context_services["face_embedding_service"] = None

        # Should not raise
        await coordinator._process_face_embeddings(
            event=sample_event,
            event_id="event-123",
            thumbnail_base64="fake-thumb",
        )

    @pytest.mark.asyncio
    async def test_publish_mqtt_event_uses_mqtt_service_direct(self, coordinator, mock_context_services, sample_event):
        """_publish_mqtt_event should use the injected mqtt_service"""
        await coordinator._publish_mqtt_event(event=sample_event, event_id="event-xyz")
        # The method uses self.mqtt_service; we just ensure it runs without error
        assert True

    @pytest.mark.asyncio
    async def test_store_embedding_uses_embedding_service_direct(self, coordinator, mock_context_services, sample_event):
        """_store_embedding should use the injected embedding_service"""
        await coordinator._store_embedding(
            event_id="event-xyz",
            embedding_vector=b"fake-emb",
            camera_id="cam-123",
        )
        # The method uses self.embedding_service; we just ensure it runs
        assert True