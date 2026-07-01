"""
Unit tests for EventHomeKitDispatcher.

This service was extracted from EventProcessor (#443 Phase B decomposition): it
owns the HomeKit sensor-trigger routing for a processed event (motion + the
detection-type-specific sensor), as fire-and-forget non-blocking tasks whose
errors never propagate.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.event_homekit_dispatcher import (
    EventHomeKitDispatcher,
    reset_event_homekit_dispatcher,
)


@pytest.fixture
def dispatcher():
    reset_event_homekit_dispatcher()
    return EventHomeKitDispatcher()


def _mock_homekit(running=True):
    hk = MagicMock()
    hk.is_running = running
    hk.trigger_motion = MagicMock(return_value=True)
    hk.trigger_occupancy = MagicMock(return_value=True)
    hk.trigger_vehicle = MagicMock(return_value=True)
    hk.trigger_animal = MagicMock(return_value=True)
    hk.trigger_package = MagicMock(return_value=True)
    return hk


def _event(camera_id="cam-1", delivery_carrier=None):
    return SimpleNamespace(camera_id=camera_id, delivery_carrier=delivery_carrier)


async def _dispatch(dispatcher, hk, event, event_id, sdt):
    with patch(
        "app.services.event_homekit_dispatcher._get_container",
        return_value=SimpleNamespace(homekit_service=hk),
    ):
        await dispatcher.dispatch(event, event_id, sdt)
        # Let the fire-and-forget create_task coroutines run.
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_person_triggers_motion_and_occupancy(dispatcher):
    hk = _mock_homekit()
    await _dispatch(dispatcher, hk, _event(), "evt-1", "person")
    hk.trigger_motion.assert_called_once_with("cam-1", event_id="evt-1")
    hk.trigger_occupancy.assert_called_once_with("cam-1", event_id="evt-1")
    hk.trigger_vehicle.assert_not_called()


@pytest.mark.asyncio
async def test_vehicle_triggers_motion_and_vehicle(dispatcher):
    hk = _mock_homekit()
    await _dispatch(dispatcher, hk, _event(), "evt-2", "vehicle")
    hk.trigger_motion.assert_called_once()
    hk.trigger_vehicle.assert_called_once_with("cam-1", event_id="evt-2")
    hk.trigger_occupancy.assert_not_called()


@pytest.mark.asyncio
async def test_animal_triggers_motion_and_animal(dispatcher):
    hk = _mock_homekit()
    await _dispatch(dispatcher, hk, _event(), "evt-3", "animal")
    hk.trigger_animal.assert_called_once_with("cam-1", event_id="evt-3")


@pytest.mark.asyncio
async def test_package_triggers_with_carrier(dispatcher):
    hk = _mock_homekit()
    await _dispatch(dispatcher, hk, _event(delivery_carrier="fedex"), "evt-4", "package")
    hk.trigger_package.assert_called_once_with(
        "cam-1", event_id="evt-4", delivery_carrier="fedex"
    )


@pytest.mark.asyncio
async def test_noop_when_homekit_not_running(dispatcher):
    hk = _mock_homekit(running=False)
    await _dispatch(dispatcher, hk, _event(), "evt-5", "person")
    hk.trigger_motion.assert_not_called()
    hk.trigger_occupancy.assert_not_called()


@pytest.mark.asyncio
async def test_trigger_error_is_swallowed(dispatcher):
    """A failing HomeKit call must not raise out of the dispatcher."""
    hk = _mock_homekit()
    hk.trigger_motion.side_effect = RuntimeError("bridge down")
    # Should not raise.
    await _dispatch(dispatcher, hk, _event(), "evt-6", "person")
    # Occupancy still attempted despite motion failing.
    hk.trigger_occupancy.assert_called_once()
