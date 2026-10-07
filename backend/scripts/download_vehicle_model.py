#!/usr/bin/env python3
"""
Download MobileNet-SSD (PASCAL VOC) weights for VehicleDetectionService.

Source: https://github.com/chuanqi305/MobileNet-SSD (the original Caffe
release used by OpenCV's DNN samples). Files are pinned by SHA-256 and the
script refuses a file that does not match.

Usage:
    python scripts/download_vehicle_model.py [--dest DIR]

Default destination: backend/app/models/mobilenet_ssd/
The detector also honours $ARGUS_VEHICLE_MODEL_DIR and the legacy
backend/models/ directory.
"""
import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

_BASE = "https://raw.githubusercontent.com/chuanqi305/MobileNet-SSD/bb17b6c3eef36d80be441ae8e5339be66e8e3b7a"
MODELS = {
    "MobileNetSSD_deploy.prototxt": (
        f"{_BASE}/deploy.prototxt",
        "2d180f723b3109e21f8287f6b3c691390d07b60eed998327cd3259ffa0e50608",
    ),
    "MobileNetSSD_deploy.caffemodel": (
        f"{_BASE}/mobilenet_iter_73000.caffemodel",
        "52eed8be80522c152a17fb56740de705b79881bde1a167e0e747310523685fc7",
    ),
}
DEFAULT_DEST = Path(__file__).resolve().parent.parent / "app" / "models" / "mobilenet_ssd"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    args = parser.parse_args()
    args.dest.mkdir(parents=True, exist_ok=True)

    ok = True
    for name, (url, expected) in MODELS.items():
        target = args.dest / name
        if target.is_file() and sha256(target) == expected:
            print(f"{name}: already present, checksum ok")
            continue
        tmp = target.with_suffix(target.suffix + ".part")
        print(f"Downloading {name} from {url}")
        urllib.request.urlretrieve(url, tmp)
        actual = sha256(tmp)
        if actual != expected:
            tmp.unlink(missing_ok=True)
            print(f"  CHECKSUM MISMATCH: expected {expected}, got {actual}", file=sys.stderr)
            ok = False
            continue
        tmp.replace(target)
        print(f"  saved {target} (sha256 {actual})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
