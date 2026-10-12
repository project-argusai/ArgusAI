"""ARGUS_* keys read by face / vehicle matching must be accepted in backend/.env.

Settings rejects unknown .env keys, so before these were declared, putting
any of them in .env stopped the backend from starting.
"""
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.core import config
from app.core.config import Settings, env_or_setting
from app.services.entity_gallery_service import MatchThresholds

FERNET = Fernet.generate_key().decode()

ARGUS_ENV = {
    "ARGUS_FACE_MODEL_DIR": "/opt/argus/opencv_zoo",
    "ARGUS_VEHICLE_MODEL_DIR": "/opt/argus/mobilenet_ssd",
    "ARGUS_FACE_RECOGNIZER": "sface",
    "ARGUS_FACE_MATCH_THRESHOLD": "0.45",
    "ARGUS_FACE_MATCH_MARGIN": "0.06",
    "ARGUS_VEHICLE_CROP_STRONG": "0.93",
    "ARGUS_VEHICLE_CROP_SUPPORT": "0.81",
    "ARGUS_VEHICLE_CROP_MARGIN": "0.04",
    "ARGUS_OBJECT_ANALYSIS_TIMEOUT_S": "3.0",
}


def _write_env(tmp_path: Path, extra: dict) -> Path:
    lines = [f"ENCRYPTION_KEY={FERNET}", "JWT_SECRET_KEY=test-only-not-a-secret"]
    lines += [f"{k}={v}" for k, v in extra.items()]
    path = tmp_path / ".env"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def clean_env(monkeypatch):
    for key in ARGUS_ENV:
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


def test_env_file_with_argus_keys_loads(tmp_path, clean_env):
    s = Settings(_env_file=str(_write_env(tmp_path, ARGUS_ENV)))
    assert s.ARGUS_FACE_MODEL_DIR == "/opt/argus/opencv_zoo"
    assert s.ARGUS_VEHICLE_MODEL_DIR == "/opt/argus/mobilenet_ssd"
    assert s.ARGUS_FACE_RECOGNIZER == "sface"
    assert s.ARGUS_FACE_MATCH_THRESHOLD == 0.45
    assert s.ARGUS_FACE_MATCH_MARGIN == 0.06
    assert s.ARGUS_VEHICLE_CROP_STRONG == 0.93
    assert s.ARGUS_VEHICLE_CROP_SUPPORT == 0.81
    assert s.ARGUS_VEHICLE_CROP_MARGIN == 0.04
    assert s.ARGUS_OBJECT_ANALYSIS_TIMEOUT_S == 3.0


def test_unknown_env_file_key_is_still_rejected(tmp_path, clean_env):
    with pytest.raises(ValidationError):
        Settings(_env_file=str(_write_env(tmp_path, {"ARGUS_NOT_A_SETTING": "1"})))


def test_process_env_beats_env_file(tmp_path, clean_env):
    clean_env.setenv("ARGUS_VEHICLE_CROP_STRONG", "0.95")
    s = Settings(_env_file=str(_write_env(tmp_path, ARGUS_ENV)))
    assert s.ARGUS_VEHICLE_CROP_STRONG == 0.95


def test_defaults_match_the_code(clean_env):
    s = Settings(_env_file=None, ENCRYPTION_KEY=FERNET, JWT_SECRET_KEY="test-only-not-a-secret")
    d = MatchThresholds()
    assert s.ARGUS_FACE_MATCH_THRESHOLD is None  # face backend's own default
    assert s.ARGUS_FACE_MATCH_MARGIN == d.face_margin
    assert s.ARGUS_VEHICLE_CROP_STRONG == d.vehicle_strong
    assert s.ARGUS_VEHICLE_CROP_SUPPORT == d.vehicle_support
    assert s.ARGUS_VEHICLE_CROP_MARGIN == d.vehicle_margin
    assert s.ARGUS_OBJECT_ANALYSIS_TIMEOUT_S == 2.5
    assert s.ARGUS_FACE_RECOGNIZER is None and s.ARGUS_FACE_MODEL_DIR is None
    assert s.ARGUS_VEHICLE_MODEL_DIR is None


def test_code_reads_settings_and_env_still_wins(clean_env):
    clean_env.setattr(config.settings, "ARGUS_VEHICLE_CROP_STRONG", 0.97)
    clean_env.setattr(config.settings, "ARGUS_FACE_MATCH_MARGIN", 0.07)
    assert env_or_setting("ARGUS_VEHICLE_CROP_STRONG") == 0.97
    t = MatchThresholds.from_env()
    assert t.vehicle_strong == 0.97 and t.face_margin == 0.07

    clean_env.setenv("ARGUS_VEHICLE_CROP_STRONG", "0.99")
    assert MatchThresholds.from_env().vehicle_strong == 0.99


def test_model_dir_settings_are_searched_first(tmp_path, clean_env):
    from app.services.face_recognition_service import face_model_search_dirs
    from app.services.vehicle_detection_service import vehicle_model_search_dirs

    clean_env.setattr(config.settings, "ARGUS_FACE_MODEL_DIR", str(tmp_path / "faces"))
    clean_env.setattr(config.settings, "ARGUS_VEHICLE_MODEL_DIR", str(tmp_path / "cars"))
    assert face_model_search_dirs()[0] == tmp_path / "faces"
    assert vehicle_model_search_dirs()[0] == tmp_path / "cars"
