"""
Lightweight Service Container for ArgusAI (Phase B #450)

This is the official Lightweight DI Container built on top of the @singleton
decorator. It is the recommended way to obtain long-lived services.

## Why use the container?

- Single source of truth for service access
- Easy to mock or replace services in tests
- Consistent reset behavior across the entire application
- Preparation for future dependency injection needs

## Production Usage

```python
from app.services.service_container import container

# In routers, tasks, lifespan, etc.
camera_service = container.camera_service
tracker = container.ai_cost_tracker
resilience = container.ai_resilience_service
```

## Test Usage (strongly recommended)

```python
from app.services.service_container import container

@pytest.fixture(autouse=True)
def fresh_services():
    container.reset_all_for_tests()
    yield
    # Optional: reset again after test
```

## Adding a New Service

1. Make sure the service uses the `@singleton` decorator (or has a clean `get_*()` + `reset_*()` pair).
2. Add the getter + reset import here.
3. Add a property.
4. Add the reset function to `_reset_functions`.

## Dynamic Access

```python
service = container.get("camera_service")   # same as container.camera_service
```
"""

from typing import Any

# All the standardized singletons
from app.services.ai_cost_and_usage_tracker import (
    get_ai_cost_and_usage_tracker,
    reset_ai_cost_and_usage_tracker,
)
from app.services.camera_service import get_camera_service, reset_camera_service
from app.services.ai_resilience_service import (
    get_ai_resilience_service,
    reset_ai_resilience_service,
)
from app.services.cost_cap_service import get_cost_cap_service, reset_cost_cap_service
from app.services.cost_alert_service import get_cost_alert_service, reset_cost_alert_service
from app.services.summary_service import get_summary_service, reset_summary_service
from app.services.protect_service import get_protect_service, reset_protect_service
from app.services.homekit_service import get_homekit_service, reset_homekit_service
from app.services.mqtt_service import get_mqtt_service, reset_mqtt_service
from app.services.snapshot_service import get_snapshot_service, reset_snapshot_service
from app.services.event_processor import get_event_processor, reset_event_processor
from app.services.ai_service import get_ai_service, reset_ai_service
from app.services.protect_event_handler import get_protect_event_handler, reset_protect_event_handler
from app.services.motion_detection_service import motion_detection_service, reset_motion_detection_service
from app.services.clip_service import get_clip_service, reset_clip_service
from app.services.frame_storage_service import get_frame_storage_service, reset_frame_storage_service
from app.services.video_storage_service import get_video_storage_service, reset_video_storage_service
from app.services.voice_query_service import get_voice_query_service, reset_voice_query_service
from app.services.cleanup_service import get_cleanup_service, reset_cleanup_service
from app.services.backup_service import get_backup_service, reset_backup_service
from app.services.tunnel_service import get_tunnel_service, reset_tunnel_service
from app.services.stream_proxy_service import get_stream_proxy_service, reset_stream_proxy_service
from app.services.vehicle_embedding_service import get_vehicle_embedding_service, reset_vehicle_embedding_service
from app.services.vehicle_matching_service import get_vehicle_matching_service, reset_vehicle_matching_service


class ServiceContainer:
    """
    Central, lazy registry for all long-lived ArgusAI services.

    Properties are lazy so they only create the underlying singleton on first access.
    """

    # ------------------------------------------------------------------
    # Core AI & Analysis
    # ------------------------------------------------------------------
    @property
    def ai_cost_tracker(self):
        return get_ai_cost_and_usage_tracker()

    @property
    def ai_resilience_service(self):
        return get_ai_resilience_service()

    @property
    def vision_analysis_orchestrator(self):
        """VisionAnalysisOrchestrator is the core analysis brain.
        Accessed via AIService for now (it wires many dependencies at startup).
        """
        ai = self.ai_service
        if not ai.vision_orchestrator:
            # This should normally be initialized during configure_providers
            raise RuntimeError("VisionAnalysisOrchestrator not yet wired in AIService")
        return ai.vision_orchestrator

    # ------------------------------------------------------------------
    # Camera & Media
    # ------------------------------------------------------------------
    @property
    def camera_service(self):
        return get_camera_service()

    @property
    def snapshot_service(self):
        return get_snapshot_service()

    # ------------------------------------------------------------------
    # Cost & Alerting
    # ------------------------------------------------------------------
    @property
    def cost_cap_service(self):
        return get_cost_cap_service()

    @property
    def cost_alert_service(self):
        return get_cost_alert_service()

    # ------------------------------------------------------------------
    # Summaries & Digests
    # ------------------------------------------------------------------
    @property
    def summary_service(self):
        return get_summary_service()

    # ------------------------------------------------------------------
    # Protect & Integrations
    # ------------------------------------------------------------------
    @property
    def protect_service(self):
        return get_protect_service()

    @property
    def homekit_service(self):
        return get_homekit_service()

    @property
    def mqtt_service(self):
        return get_mqtt_service()

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------
    @property
    def event_processor(self):
        return get_event_processor()

    @property
    def ai_service(self):
        return get_ai_service()

    @property
    def protect_event_handler(self):
        return get_protect_event_handler()

    @property
    def motion_detection_service(self):
        return motion_detection_service

    @property
    def clip_service(self):
        return get_clip_service()

    @property
    def frame_storage_service(self):
        return get_frame_storage_service()

    @property
    def video_storage_service(self):
        return get_video_storage_service()

    @property
    def voice_query_service(self):
        return get_voice_query_service()

    @property
    def cleanup_service(self):
        return get_cleanup_service()

    @property
    def backup_service(self):
        return get_backup_service()

    @property
    def tunnel_service(self):
        return get_tunnel_service()

    @property
    def stream_proxy_service(self):
        return get_stream_proxy_service()

    @property
    def vehicle_embedding_service(self):
        return get_vehicle_embedding_service()

    @property
    def vehicle_matching_service(self):
        return get_vehicle_matching_service()

    # ------------------------------------------------------------------
    # Testing utilities
    # ------------------------------------------------------------------
    _reset_functions = [
        reset_ai_cost_and_usage_tracker,
        reset_camera_service,
        reset_ai_resilience_service,
        reset_cost_cap_service,
        reset_cost_alert_service,
        reset_summary_service,
        reset_protect_service,
        reset_homekit_service,
        reset_mqtt_service,
        reset_snapshot_service,
        reset_event_processor,
        reset_ai_service,
        reset_protect_event_handler,
        reset_motion_detection_service,
        reset_clip_service,
        reset_frame_storage_service,
        reset_video_storage_service,
        reset_voice_query_service,
        reset_tunnel_service,
        reset_stream_proxy_service,
        reset_vehicle_embedding_service,
        reset_vehicle_matching_service,
        reset_cleanup_service,
        reset_backup_service,
    ]

    def reset_all_for_tests(self) -> None:
        """
        Reset every registered singleton.

        Call this at the beginning of tests (and optionally at the end)
        when you need completely fresh service instances.
        """
        for fn in self._reset_functions:
            try:
                fn()
            except Exception:
                pass  # Some services may not expose a reset function yet — safe to ignore.

    # ------------------------------------------------------------------
    # Convenience / introspection
    # ------------------------------------------------------------------
    def list_services(self) -> list[str]:
        """Return names of all services currently exposed by the container."""
        return [
            name for name in dir(self)
            if not name.startswith("_") and not callable(getattr(self, name))
        ]

    def get(self, name: str):
        """Dynamic access to a service by name (useful for plugins or generic code)."""
        if hasattr(self, name):
            return getattr(self, name)
        raise AttributeError(f"Service '{name}' is not registered in the container.")


# Global container instance (the recommended way to obtain services)
container = ServiceContainer()
