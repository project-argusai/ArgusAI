"""VehicleDetectionService finds MobileNet-SSD weights in the documented places."""
import logging

import pytest

from app.services import vehicle_detection_service as vds


def _touch(d):
    d.mkdir(parents=True, exist_ok=True)
    (d / vds.VEHICLE_PROTOTXT).write_text("x")
    (d / vds.VEHICLE_CAFFEMODEL).write_bytes(b"x")


def test_env_dir_wins(tmp_path, monkeypatch):
    _touch(tmp_path / "custom")
    monkeypatch.setenv(vds.VEHICLE_MODEL_DIR_ENV, str(tmp_path / "custom"))
    proto, weights = vds.resolve_vehicle_model_paths()
    assert proto == str(tmp_path / "custom" / vds.VEHICLE_PROTOTXT)
    assert weights == str(tmp_path / "custom" / vds.VEHICLE_CAFFEMODEL)


def test_search_order(monkeypatch):
    monkeypatch.delenv(vds.VEHICLE_MODEL_DIR_ENV, raising=False)
    dirs = vds.vehicle_model_search_dirs()
    assert dirs[0].parts[-3:] == ("app", "models", "mobilenet_ssd")
    assert dirs[1].parts[-2:] == ("backend", "models") or dirs[1].name == "models"


def test_missing_weights_fall_back_with_warning(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(vds, "vehicle_model_search_dirs", lambda: [tmp_path / "nope"])
    svc = vds.VehicleDetectionService.__new__(vds.VehicleDetectionService)
    svc._model_loaded = False
    svc._use_fallback = False
    svc._net = None
    with caplog.at_level(logging.WARNING):
        svc._load_model()
    assert svc.is_using_fallback()
    assert any("DISABLED" in r.getMessage() for r in caplog.records)


def test_half_present_dir_is_skipped(tmp_path, monkeypatch):
    half = tmp_path / "half"
    half.mkdir()
    (half / vds.VEHICLE_PROTOTXT).write_text("x")
    full = tmp_path / "full"
    _touch(full)
    monkeypatch.setattr(vds, "vehicle_model_search_dirs", lambda: [half, full])
    assert vds.resolve_vehicle_model_paths()[0] == str(full / vds.VEHICLE_PROTOTXT)


def test_opencv_still_has_caffe_importer():
    """Face and vehicle detectors load Caffe weights. OpenCV 5 dropped the
    importer, which silently disabled both (see requirements.txt pin)."""
    import cv2

    assert hasattr(cv2.dnn, "readNetFromCaffe"), cv2.__version__
