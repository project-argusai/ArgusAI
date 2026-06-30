"""
Unit tests for SettingsService.get_frame_extraction_config().

Wires the previously-dead admin settings back into a single typed reader so the
live AI pipeline and the reanalyze endpoint honor admin-configured frame count,
sampling strategy, and extraction offset. Defaults mirror the SystemSettings
schema (analysis_frame_count=10, frame_sampling_strategy="uniform",
frame_extraction_offset_ms=2000), and invalid/out-of-range values fall back to
those defaults rather than reaching the extractor.
"""
import pytest

from app.models.system_setting import SystemSetting
from app.services.settings_service import SettingsService


def _set(db, key, value):
    db.add(SystemSetting(key=key, value=str(value)))
    db.commit()


def test_defaults_when_no_settings(db_session):
    cfg = SettingsService(db_session).get_frame_extraction_config()
    assert cfg["frame_count"] == 10
    assert cfg["sampling_strategy"] == "uniform"
    assert cfg["offset_ms"] == 2000


def test_reads_configured_values(db_session):
    _set(db_session, "settings_analysis_frame_count", 5)
    _set(db_session, "settings_frame_sampling_strategy", "hybrid")
    _set(db_session, "settings_frame_extraction_offset_ms", 3000)

    cfg = SettingsService(db_session).get_frame_extraction_config()
    assert cfg["frame_count"] == 5
    assert cfg["sampling_strategy"] == "hybrid"
    assert cfg["offset_ms"] == 3000


def test_invalid_frame_count_falls_back_to_default(db_session):
    _set(db_session, "settings_analysis_frame_count", "99")  # not in {5,10,15,20}
    cfg = SettingsService(db_session).get_frame_extraction_config()
    assert cfg["frame_count"] == 10


def test_non_numeric_frame_count_falls_back(db_session):
    _set(db_session, "settings_analysis_frame_count", "abc")
    cfg = SettingsService(db_session).get_frame_extraction_config()
    assert cfg["frame_count"] == 10


def test_invalid_sampling_strategy_falls_back(db_session):
    _set(db_session, "settings_frame_sampling_strategy", "magic")
    cfg = SettingsService(db_session).get_frame_extraction_config()
    assert cfg["sampling_strategy"] == "uniform"


def test_offset_out_of_range_is_clamped(db_session):
    _set(db_session, "settings_frame_extraction_offset_ms", 999999)
    cfg = SettingsService(db_session).get_frame_extraction_config()
    assert cfg["offset_ms"] == 10000  # clamped to schema max
