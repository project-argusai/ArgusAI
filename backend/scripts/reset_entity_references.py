#!/usr/bin/env python3
"""
List and reset entity references before re-enrolling them from clean events.

Background: entity matching now compares face and vehicle *crops* against a
per-entity gallery (``entity_gallery_items``). Entities created before that
still carry a whole-frame CLIP ``reference_embedding`` and a reference
thumbnail, which on a fixed camera mostly show the background (and whatever
car happened to be parked). This script clears those so each entity can be
re-enrolled by assigning a few clean events to it in the UI.

Dry run by default; nothing is written without --apply. Back up the database
first (the deploy runbook's sqlite3.backup step).

Examples:
    python scripts/reset_entity_references.py --list
    python scripts/reset_entity_references.py --all --clear-reference-embedding --clear-thumbnail
    python scripts/reset_entity_references.py --entity <id> --clear-gallery --apply

Actions:
    --clear-gallery              remove gallery crops (face and vehicle)
    --clear-reference-embedding  set the legacy whole-frame embedding to the
                                 empty placeholder; the old scene matcher then
                                 skips the entity, and the next manual assign
                                 seeds it again (#677)
    --clear-thumbnail            unset the entity's reference image (the next
                                 assigned event's thumbnail replaces it)

Entity links, names, VIP/blocked flags and alert rules are never touched.
"""
import argparse
import json
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))


def _has_reference(raw) -> bool:
    try:
        vec = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        return False
    return isinstance(vec, list) and len(vec) > 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="List and reset entity references.")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--entity", action="append", default=[], metavar="ID", help="entity id (repeatable)")
    target.add_argument("--all", action="store_true", help="every person and vehicle entity")
    parser.add_argument("--list", action="store_true", help="show entities and their references")
    parser.add_argument("--clear-gallery", action="store_true")
    parser.add_argument("--clear-reference-embedding", action="store_true")
    parser.add_argument("--clear-thumbnail", action="store_true")
    parser.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    args = parser.parse_args(argv)

    actions = args.clear_gallery or args.clear_reference_embedding or args.clear_thumbnail
    if actions and not (args.entity or args.all):
        parser.error("choose --entity ID or --all")
    if not actions and not args.list:
        parser.error("nothing to do: pass --list or an action")

    from sqlalchemy import func

    from app.core.database import SessionLocal
    from app.models.entity_gallery_item import EntityGalleryItem
    from app.models.recognized_entity import RecognizedEntity
    from app.services.entity_gallery_service import get_entity_gallery_service

    db = SessionLocal()
    try:
        q = db.query(RecognizedEntity).filter(RecognizedEntity.entity_type.in_(("person", "vehicle")))
        if args.entity:
            q = q.filter(RecognizedEntity.id.in_(args.entity))
        entities = q.order_by(RecognizedEntity.entity_type, RecognizedEntity.name).all()
        if args.entity:
            missing = set(args.entity) - {e.id for e in entities}
            if missing:
                print(f"Unknown entity id(s): {', '.join(sorted(missing))}", file=sys.stderr)
                return 2

        counts = {}
        for entity_id, kind, n in (
            db.query(EntityGalleryItem.entity_id, EntityGalleryItem.kind, func.count(EntityGalleryItem.id))
            .group_by(EntityGalleryItem.entity_id, EntityGalleryItem.kind)
            .all()
        ):
            counts.setdefault(entity_id, {})[kind] = n

        print(f"{'id':36}  {'type':7}  {'name':24}  gallery(face/vehicle)  scene-ref  thumbnail")
        for e in entities:
            c = counts.get(e.id, {})
            print(
                f"{e.id:36}  {e.entity_type:7}  {(e.name or '(unnamed)')[:24]:24}  "
                f"{c.get('face', 0):>4} / {c.get('vehicle', 0):<4}           "
                f"{'yes' if _has_reference(e.reference_embedding) else 'no':9}  "
                f"{'yes' if e.thumbnail_path else 'no'}"
            )
        if not actions:
            return 0

        mode = "APPLY" if args.apply else "DRY RUN"
        print(f"\n[{mode}] {len(entities)} entit{'y' if len(entities) == 1 else 'ies'}:")
        gallery = get_entity_gallery_service()
        for e in entities:
            changes = []
            if args.clear_gallery:
                n = sum(counts.get(e.id, {}).values())
                changes.append(f"remove {n} gallery crop(s)")
                if args.apply and n:
                    gallery.reset_entity(db, e.id)
            if args.clear_reference_embedding and _has_reference(e.reference_embedding):
                changes.append("clear scene reference embedding")
                if args.apply:
                    e.reference_embedding = "[]"
            if args.clear_thumbnail and e.thumbnail_path:
                changes.append("clear reference thumbnail")
                if args.apply:
                    e.thumbnail_path = None
            print(f"  {e.name or e.id}: {', '.join(changes) or 'nothing to change'}")
        if args.apply:
            db.commit()
            print("Done. Restart the backend so match caches reload (or wait ~5 minutes).")
        else:
            print("Nothing written. Re-run with --apply.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
