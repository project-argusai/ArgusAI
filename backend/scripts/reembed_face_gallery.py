#!/usr/bin/env python3
"""
Re-embed stored face crops for the active face recognizer (after switching
ARGUS_FACE_RECOGNIZER between sface and arcface).

Face references are per model: each gallery item and face observation stores
the ``model_version`` of the backend that embedded it, and matching only
compares vectors of the active model. Right after a switch, nobody's face
matches until references exist for the new model. Both backends use the
same 112x112 aligned crop, and those crops are stored, so this script
rebuilds the vectors in place from them: no events need re-assigning.

Rows without a stored crop (older ones) are skipped; re-enroll those people
by assigning a few clear events to them. Dry run by default. Back up the
database first (sqlite3.backup), and restart the backend afterwards so the
gallery cache reloads.

    python scripts/reembed_face_gallery.py            # what would change
    python scripts/reembed_face_gallery.py --apply

Switching back later works the same way (run it again with the other model).
"""
import argparse
import json
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))


def reembed(db, recognizer, *, apply: bool) -> dict:
    """Re-embed face gallery items and face observations not on the active model."""
    import cv2
    import numpy as np

    from app.models.entity_gallery_item import EntityGalleryItem
    from app.models.face_embedding import FaceEmbedding
    from app.services.entity_gallery_service import FACE, read_crop

    target = recognizer.model_version
    stats = {"gallery": 0, "observations": 0, "skipped_no_crop": 0, "failed": 0}
    queries = (
        ("gallery", db.query(EntityGalleryItem).filter(EntityGalleryItem.kind == FACE, EntityGalleryItem.model_version != target)),
        ("observations", db.query(FaceEmbedding).filter(FaceEmbedding.model_version != target)),
    )
    for label, q in queries:
        for row in q.all():
            data = read_crop(getattr(row, "crop_path", None))
            if not data:
                stats["skipped_no_crop"] += 1
                continue
            img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
            vec = recognizer.embed_aligned(img) if img is not None else None
            if vec is None:
                stats["failed"] += 1
                continue
            stats[label] += 1
            if apply:
                row.embedding = json.dumps([round(float(x), 6) for x in vec])
                row.model_version = target
    if apply:
        db.commit()
    return stats


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Re-embed stored face crops for the active face model.")
    parser.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    args = parser.parse_args(argv)

    from app.core.database import SessionLocal
    from app.services.face_recognition_service import get_face_recognition_service

    recognizer = get_face_recognition_service()
    if not recognizer.is_available():
        print(f"Face backend '{recognizer.name}' is not available (weights missing?). Nothing done.", file=sys.stderr)
        return 1
    print(f"Active face model: {recognizer.name} ({recognizer.model_version})")
    db = SessionLocal()
    try:
        stats = reembed(db, recognizer, apply=args.apply)
    finally:
        db.close()
    mode = "Re-embedded" if args.apply else "Would re-embed"
    print(f"{mode}: {stats['gallery']} gallery item(s), {stats['observations']} observation(s)")
    print(f"Skipped (no stored crop): {stats['skipped_no_crop']}; failed: {stats['failed']}")
    if args.apply:
        print("Done. Restart the backend so the gallery cache reloads.")
    else:
        print("Nothing written. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
