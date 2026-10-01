"""objects_detected lists only the subjects that are actually present."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.ai_types import AIResult
from app.services.identification import (
    apply_identification,
    empty_identification,
    extract_objects_from_description,
    resolve_objects_detected,
)
from app.services.protect_event_storage_service import ProtectEventStorageService


ANCHOR = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

# The post-#632 empty-frame sentence names every category. Keyword matching
# used to store all four.
EMPTY_FRAME = (
    "No person, vehicle, animal, or package is visible. Nothing visible in the frame."
)
OVER_INCLUSIVE = (
    "A person walks toward the door. A dog stands in the yard. "
    "No package is visible. A car is parked in the background."
)


def _result(description: str, objects=None) -> AIResult:
    return AIResult(
        description=description,
        confidence=70,
        objects_detected=list(objects or ["person", "vehicle", "animal", "package"]),
        provider="test",
        tokens_used=1,
        response_time_ms=1,
        cost_estimate=0.0,
        success=True,
    )


def _ident(**fields) -> str:
    payload = {
        "description": fields.pop("description", ""),
        "count": 1,
        "identity": "unknown",
        "action": "walking",
        "direction": "toward camera",
        "package_or_carrier": "none",
    }
    payload.update(fields)
    return json.dumps(payload)


def test_empty_frame_is_an_empty_list():
    result = _result(EMPTY_FRAME)
    apply_identification(result, _ident(
        description=EMPTY_FRAME,
        object_type="none",
        count=0,
        package_or_carrier="package",
    ))
    assert result.identification["object_type"] == "none"
    assert result.objects_detected == []

    # An empty frame stays empty even when Protect labeled the event.
    assert resolve_objects_detected(
        identification=result.identification,
        description=EMPTY_FRAME,
        smart_detection_types=["animal"],
    ) == []


def test_negated_mentions_do_not_add_categories():
    text = (
        "A dog runs across the yard. No package. No vehicles visible. Nothing else is visible."
    )
    assert extract_objects_from_description(text) == ["animal"]
    assert resolve_objects_detected(identification=None, description=text) == ["animal"]

    from app.services.ai_providers.base import AIProviderBase

    class _Provider(AIProviderBase):
        async def generate_description(self, *args, **kwargs):
            raise NotImplementedError

        async def generate_multi_image_description(self, *args, **kwargs):
            raise NotImplementedError

    assert _Provider("test-key")._extract_objects(
        "No package was left. No vehicles are visible."
    ) == []
    assert _Provider("test-key")._extract_objects("Nothing visible.") == []


def test_animal_only_ignores_other_categories_in_the_description():
    description = (
        "An animal crosses the yard past a person-shaped shadow. "
        "A car is parked in the background. No package is visible."
    )
    result = _result(description)
    apply_identification(result, _ident(description=description, object_type="animal"))
    assert result.objects_detected == ["animal"]


def test_person_with_no_package_does_not_keep_background_or_package():
    result = _result(OVER_INCLUSIVE)
    apply_identification(result, _ident(
        description=OVER_INCLUSIVE,
        object_type="person",
        package_or_carrier="none",
    ))
    assert result.objects_detected == ["person"]

    unsure = _result(OVER_INCLUSIVE)
    apply_identification(unsure, _ident(
        description=OVER_INCLUSIVE,
        object_type="person",
        package_or_carrier="cannot_tell",
    ))
    assert unsure.objects_detected == ["person"]

    # A bare "package" label is dropped when the description does not support it
    # (a sheet of paper is not a delivery). objects_detected follows that.
    paper = "A man holds a white sheet of paper."
    sheet = _result(paper)
    apply_identification(sheet, _ident(
        description=paper,
        object_type="person",
        package_or_carrier="package",
    ))
    assert sheet.identification["package_or_carrier"] == "none"
    assert sheet.objects_detected == ["person"]


def test_person_delivering_a_package_includes_package():
    description = "A person in a brown uniform sets a box on the step and walks away."
    result = _result(description)
    apply_identification(result, _ident(
        description=description,
        object_type="person",
        package_or_carrier="UPS",
        action="delivering",
    ))
    assert result.objects_detected == ["person", "package"]

    dropped = _result("A person sets a cardboard box on the step.")
    apply_identification(dropped, _ident(
        description="A person sets a cardboard box on the step.",
        object_type="package",
        package_or_carrier="none",
    ))
    assert dropped.objects_detected == ["package"]


def test_missing_identification_uses_smart_detect_then_text():
    soup = "A person, a vehicle, an animal, and a package are all mentioned."
    assert resolve_objects_detected(
        identification=None,
        description=soup,
        smart_detection_types=["animal", "motion", "ring"],
    ) == ["animal"]
    assert resolve_objects_detected(
        identification=empty_identification(),
        description=soup,
        smart_detection_types="animal",
    ) == ["animal"]

    # No Protect label: negated text is the fallback, not the raw keyword list.
    prose = "A dog runs across the yard. No package. No vehicles visible."
    result = _result(prose, objects=["person", "vehicle", "animal", "package"])
    apply_identification(result, prose)
    assert result.identification["object_type"] == "unknown"
    assert result.objects_detected == ["animal"]


@pytest.mark.asyncio
async def test_persist_uses_identification_and_smart_detect_fallback():
    service = ProtectEventStorageService()
    camera = SimpleNamespace(id="cam-1", name="Front Door")
    snap = SimpleNamespace(timestamp=ANCHOR, thumbnail_path=None)

    empty = _result(EMPTY_FRAME)
    apply_identification(empty, _ident(description=EMPTY_FRAME, object_type="none", count=0))
    db = MagicMock()
    stored = await service.persist_protect_event(
        db=db,
        camera=camera,
        snapshot_result=snap,
        ai_result=empty,
        protect_event_id="empty-frame",
        event_type="animal",
    )
    assert json.loads(stored.objects_detected) == []
    assert stored.smart_detection_type == "animal"

    missing = _result(
        "A person, a vehicle, an animal, and a package are all mentioned.",
        objects=["person", "vehicle", "animal", "package"],
    )
    missing.identification = empty_identification()
    db = MagicMock()
    stored = await service.persist_protect_event(
        db=db,
        camera=camera,
        snapshot_result=snap,
        ai_result=missing,
        protect_event_id="fallback",
        event_type="animal",
    )
    assert json.loads(stored.objects_detected) == ["animal"]
    assert missing.objects_detected == ["animal"]


def test_empty_frame_merge_does_not_restore_the_smart_detect_type():
    """A later Protect update must not put vehicle back on an empty frame."""
    from app.services.identification import dumps_identification

    service = ProtectEventStorageService()
    event = SimpleNamespace(
        id="evt-empty",
        objects_detected="[]",
        smart_detection_type="vehicle",
        is_doorbell_ring=False,
        protect_event_id="prot-1",
        identification=dumps_identification({
            "object_type": "none",
            "count": 0,
            "identity": "unknown",
            "action": "cannot_tell",
            "direction": "cannot_tell",
            "package_or_carrier": "none",
        }),
    )
    changed = service.merge_detection_types(MagicMock(), event, ["vehicle"], False)
    assert changed is False
    assert json.loads(event.objects_detected) == []

    # Missing identification still accepts the Protect label.
    unlabeled = SimpleNamespace(
        id="evt-open",
        objects_detected="[]",
        smart_detection_type="vehicle",
        is_doorbell_ring=False,
        protect_event_id="prot-2",
        identification=None,
    )
    changed = service.merge_detection_types(MagicMock(), unlabeled, ["vehicle"], False)
    assert changed is True
    assert json.loads(unlabeled.objects_detected) == ["vehicle"]
