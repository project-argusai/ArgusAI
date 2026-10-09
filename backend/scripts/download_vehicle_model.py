#!/usr/bin/env python3
"""
Download the local detector / recognizer weights, pinned by SHA-256.

Model sets:

* ``vehicle``: MobileNet-SSD (PASCAL VOC) for VehicleDetectionService.
  Source: https://github.com/chuanqi305/MobileNet-SSD (the original Caffe
  release used by OpenCV's DNN samples).
  Default destination: backend/app/models/mobilenet_ssd/ (the detector also
  honours $ARGUS_VEHICLE_MODEL_DIR and the legacy backend/models/ directory).
* ``face``: YuNet face detector (MIT) and SFace face recognizer
  (Apache-2.0) from the OpenCV Model Zoo, for FaceRecognitionService.
  Both run on OpenCV's own DNN module (cv2.FaceDetectorYN /
  cv2.FaceRecognizerSF), so no extra Python package is needed.
  Default destination: backend/app/models/opencv_zoo/ (also honours
  $ARGUS_FACE_MODEL_DIR).
* ``plate``: licence-plate detector (open-image-models YOLOv9-t 384, MIT)
  and plate OCR (fast-plate-ocr CCT-XS v2 global, MIT) for plate matching
  on known vehicles. Needs the optional ``requirements-plates.txt``
  packages to run. These are GitHub release assets (not commit-addressed),
  so the SHA-256 pin is what guarantees the bytes.
  Default destination: backend/app/models/plates/ (or $PLATE_MODEL_DIR /
  the PLATE_MODEL_DIR setting).

Every file is pinned to an exact upstream commit and checked against its
SHA-256. A file that does not match is refused and the script exits 1.

Usage:
    python scripts/download_vehicle_model.py              # vehicle + face (plate is opt-in)
    python scripts/download_vehicle_model.py --only plate # plate matching models
    python scripts/download_vehicle_model.py --only face  # one set
    python scripts/download_vehicle_model.py --only vehicle --dest DIR
"""
import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

_MODELS_DIR = Path(__file__).resolve().parent.parent / "app" / "models"

_SSD_BASE = "https://raw.githubusercontent.com/chuanqi305/MobileNet-SSD/bb17b6c3eef36d80be441ae8e5339be66e8e3b7a"
# opencv_zoo stores the ONNX files in Git LFS; github.com/<repo>/raw/<sha>/
# redirects to the LFS object, so the commit pin still holds.
_ZOO_BASE = "https://github.com/opencv/opencv_zoo/raw/47534e27c9851bb1128ccc0102f1145e27f23f98/models"

MODEL_SETS = {
    "vehicle": {
        "dest": _MODELS_DIR / "mobilenet_ssd",
        "files": {
            "MobileNetSSD_deploy.prototxt": (
                f"{_SSD_BASE}/deploy.prototxt",
                "2d180f723b3109e21f8287f6b3c691390d07b60eed998327cd3259ffa0e50608",
            ),
            "MobileNetSSD_deploy.caffemodel": (
                f"{_SSD_BASE}/mobilenet_iter_73000.caffemodel",
                "52eed8be80522c152a17fb56740de705b79881bde1a167e0e747310523685fc7",
            ),
        },
    },
    "face": {
        "dest": _MODELS_DIR / "opencv_zoo",
        "files": {
            "face_detection_yunet_2023mar.onnx": (
                f"{_ZOO_BASE}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
                "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
            ),
            "face_recognition_sface_2021dec.onnx": (
                f"{_ZOO_BASE}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
                "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
            ),
        },
    },
}

_OIM_ASSETS = "https://github.com/ankandrew/open-image-models/releases/download/assets"
_OCR_ASSETS = "https://github.com/ankandrew/cnn-ocr-lp/releases/download/arg-plates"

MODEL_SETS["plate"] = {
    "dest": _MODELS_DIR / "plates",
    "files": {
        "yolo-v9-t-384-license-plates-end2end.onnx": (
            f"{_OIM_ASSETS}/yolo-v9-t-384-license-plates-end2end.onnx",
            "888397b96d761c89db40bc9c305838e8652660f5e282c2cadebbe8d2951a77a8",
        ),
        "cct_xs_v2_global.onnx": (
            f"{_OCR_ASSETS}/cct_xs_v2_global.onnx",
            "8031afb5fdc6b4d80462c9d542f1284ebd2cfddf5dbacd62609848d7e2855f44",
        ),
        "cct_xs_v2_global_plate_config.yaml": (
            f"{_OCR_ASSETS}/cct_xs_v2_global_plate_config.yaml",
            "0335c74a305173bb6f393efed0fde03cadeaa0b649ed8e19f431016d8232d0a6",
        ),
    },
}

OPT_IN_SETS = frozenset({"plate"})

# Kept for callers that imported the old single-set constants.
MODELS = MODEL_SETS["vehicle"]["files"]
DEFAULT_DEST = MODEL_SETS["vehicle"]["dest"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download_set(files: dict, dest: Path) -> bool:
    dest.mkdir(parents=True, exist_ok=True)
    ok = True
    for name, (url, expected) in files.items():
        target = dest / name
        if target.is_file() and sha256(target) == expected:
            print(f"{name}: already present, checksum ok")
            continue
        tmp = target.with_suffix(target.suffix + ".part")
        print(f"Downloading {name} from {url}")
        try:
            urllib.request.urlretrieve(url, tmp)
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            print(f"  DOWNLOAD FAILED: {exc}", file=sys.stderr)
            ok = False
            continue
        actual = sha256(tmp)
        if actual != expected:
            tmp.unlink(missing_ok=True)
            print(f"  CHECKSUM MISMATCH: expected {expected}, got {actual}", file=sys.stderr)
            ok = False
            continue
        tmp.replace(target)
        print(f"  saved {target} (sha256 {actual})")
    return ok


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--only", choices=sorted(MODEL_SETS), help="download one model set")
    parser.add_argument("--dest", type=Path, help="destination directory (requires --only)")
    args = parser.parse_args(argv)
    if args.dest and not args.only:
        parser.error("--dest needs --only, since each model set has its own directory")

    # Plate models are only needed when plate matching is turned on.
    names = [args.only] if args.only else [n for n in MODEL_SETS if n not in OPT_IN_SETS]
    ok = True
    for name in names:
        spec = MODEL_SETS[name]
        print(f"== {name} models")
        ok = download_set(spec["files"], args.dest or spec["dest"]) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
