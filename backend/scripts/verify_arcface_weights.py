#!/usr/bin/env python3
"""
Check the user-supplied ArcFace weights before turning ArcFace on.

ArgusAI never downloads these weights (InsightFace licenses them for
non-commercial research use only). Put ``w600k_r50.onnx`` from InsightFace's
``buffalo_l`` package at backend/app/models/arcface/ (or point
ARGUS_ARCFACE_MODEL_PATH at it), then run:

    python scripts/verify_arcface_weights.py            # checksum only
    python scripts/verify_arcface_weights.py --load     # also load and embed a test face

Exit code 0 when the file matches the expected SHA-256 (the pinned buffalo_l
hash, or ARGUS_ARCFACE_SHA256 for another export), 1 otherwise.
"""
import argparse
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Verify the ArcFace weights file.")
    parser.add_argument("--path", type=Path, help="weights file (default: configured path)")
    parser.add_argument("--load", action="store_true", help="also load the model and embed a test face")
    args = parser.parse_args(argv)

    from app.services.arcface_recognizer import (
        ArcFaceRecognizer,
        arcface_model_path,
        expected_sha256,
        file_sha256,
    )

    path = args.path or arcface_model_path()
    print(f"weights:  {path}")
    if not path.is_file():
        print("result:   MISSING", file=sys.stderr)
        return 1
    actual, expected = file_sha256(path), expected_sha256()
    print(f"expected: {expected}")
    print(f"actual:   {actual}")
    if actual != expected:
        print("result:   CHECKSUM MISMATCH (not loaded)", file=sys.stderr)
        return 1
    print("result:   OK")
    if args.load:
        import cv2

        fixture = backend_dir / "tests" / "fixtures" / "faces" / "astronaut_256.jpg"
        rec = ArcFaceRecognizer(model_path=str(path), verified=True)
        if not rec.is_available():
            print("load:     FAILED (YuNet detector missing? run download_vehicle_model.py --only face)", file=sys.stderr)
            return 1
        faces = rec.identify(cv2.imread(str(fixture)))
        print(f"load:     OK, {len(faces)} face(s), dim {faces[0].embedding.shape[0] if faces else '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
