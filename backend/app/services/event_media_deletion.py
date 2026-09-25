"""Per-event media deletion shared by single delete, bulk delete, and later retention.

Issue #599. Retention and wipe (#600) should call ``delete_event_media`` and
``reconcile_orphans`` rather than unlinking event files themselves. This module
does not change scheduled retention or wipe behavior.

Invariants for one call that the caller then commits:

- A stored path is unlinked only when it resolves inside its media root and is
  not a symlink. Traversal, absolute paths outside the root, and symlinks are
  refused and left on disk.
- The event row is removed only when every associated file was removed or was
  already absent. Failures keep the row so the remaining files are not orphaned.
- Database pointers are cleared only for files that are confirmed gone, so a
  kept event does not point at a file this call deleted.
- Missing files are success (idempotent). A later retry finishes the rest.
- This method does not commit. If the caller cannot commit, it must not report
  success: files may already be gone and a retry clears the restored pointers.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.models.event import Event
from app.models.event_frame import EventFrame
from app.services.cleanup_service import (
    _is_within_directory,
    _safe_join,
    _thumbnail_relative_key,
    annotated_sibling_path,
    resolve_thumbnail_fs_path,
)

logger = logging.getLogger(__name__)

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_VIDEO_PREFIXES = (
    "data/videos/",
    "/data/videos/",
    "videos/",
    "/videos/",
)
_FRAME_PREFIX = "frames/"
_SAMPLE_LIMIT = 50


def _backend_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def default_media_roots() -> dict[str, str]:
    """Configured media directories, falling back to backend/data/*."""
    from app.core.config import settings

    data = os.path.join(_backend_dir(), "data")

    def pick(configured: Optional[str], name: str) -> str:
        if configured is not None and str(configured).strip():
            return os.path.abspath(str(configured).strip())
        return os.path.join(data, name)

    return {
        "thumbnail_root": pick(settings.MEDIA_THUMBNAIL_DIR, "thumbnails"),
        "frames_root": pick(settings.MEDIA_FRAMES_DIR, "frames"),
        "video_root": pick(settings.MEDIA_VIDEO_DIR, "videos"),
        "clips_root": pick(settings.MEDIA_CLIPS_DIR, "clips"),
    }


@dataclass
class MediaFailure:
    event_id: str
    kind: str
    reason: str
    stored_path: str

    def as_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "kind": self.kind,
            "reason": self.reason,
            "stored_path": self.stored_path[:500],
        }


@dataclass
class EventMediaDeletionResult:
    event_id: str
    event_deleted: bool = False
    failures: list[MediaFailure] = field(default_factory=list)
    thumbnails_deleted: int = 0
    frames_deleted: int = 0
    videos_deleted: int = 0
    clips_deleted: int = 0
    bytes_freed: int = 0
    commit_failed: bool = False

    @property
    def fully_deleted(self) -> bool:
        return self.event_deleted and not self.failures and not self.commit_failed

    def failure_dicts(self) -> list[dict]:
        items = [item.as_dict() for item in self.failures]
        if self.commit_failed:
            items.append({
                "event_id": self.event_id,
                "kind": "database",
                "reason": "commit_failed",
                "stored_path": "",
            })
        return items


@dataclass
class OrphanMediaReport:
    dry_run: bool
    skipped: bool = False
    skip_reason: Optional[str] = None
    orphan_files: int = 0
    deleted_files: int = 0
    failed_files: int = 0
    skipped_symlinks: int = 0
    bytes: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)
    samples: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """A dry run succeeds when the report was built. Apply succeeds when every orphan unlink worked."""
        if self.skipped:
            return False
        if self.dry_run:
            return True
        return self.failed_files == 0

    def as_dict(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "success": self.success,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "orphan_files": self.orphan_files,
            "deleted_files": self.deleted_files,
            "failed_files": self.failed_files,
            "skipped_symlinks": self.skipped_symlinks,
            "bytes": self.bytes,
            "by_kind": self.by_kind,
            "samples": self.samples,
        }


@dataclass
class _Target:
    kind: str
    stored: str
    root: str
    resolved: Optional[str] = None
    refusal: Optional[str] = None
    frame_id: Optional[str] = None
    # Pointer cleared only when this target and every sibling in the group succeed.
    clear_group: Optional[str] = None
    counter: str = "frames"


class EventMediaDeletionService:
    """Delete one event's files inside the configured media roots."""

    def __init__(
        self,
        thumbnail_root: Optional[str] = None,
        frames_root: Optional[str] = None,
        video_root: Optional[str] = None,
        clips_root: Optional[str] = None,
        unlink: Optional[Callable[[str], None]] = None,
    ):
        roots = default_media_roots()
        self.thumbnail_root = thumbnail_root or roots["thumbnail_root"]
        self.frames_root = frames_root or roots["frames_root"]
        self.video_root = video_root or roots["video_root"]
        self.clips_root = clips_root or roots["clips_root"]
        self._unlink = unlink or os.remove

    def delete_event_media(self, db: Session, event: Event) -> EventMediaDeletionResult:
        """Unlink this event's media and stage DB updates. Does not commit."""
        result = EventMediaDeletionResult(event_id=event.id)
        targets = self._enumerate(db, event)
        outcomes: dict[int, str] = {}

        seen: set[str] = set()
        deferred: list[tuple[int, _Target]] = []
        for index, target in enumerate(targets):
            if target.kind == "thumbnail" and not target.refusal:
                deferred.append((index, target))
                continue
            self._consume_target(result, event.id, outcomes, seen, index, target)

        annotated_failed = any(
            outcomes.get(index) == "failed" and targets[index].kind == "annotated_thumbnail"
            for index in outcomes
        )
        for index, target in deferred:
            if annotated_failed:
                # Leave the primary thumbnail in place so its pointer still
                # names a file that exists. The annotated failure is the record.
                outcomes[index] = "kept"
                continue
            self._consume_target(result, event.id, outcomes, seen, index, target)

        self._apply_pointer_updates(db, event, targets, outcomes, partial=bool(result.failures))
        if result.failures:
            result.event_deleted = False
            logger.warning(
                "Event media deletion incomplete",
                extra={
                    "event_id": event.id,
                    "failure_count": len(result.failures),
                    "reasons": sorted({item.reason for item in result.failures}),
                },
            )
        else:
            db.delete(event)
            result.event_deleted = True
        return result

    def _consume_target(
        self,
        result: EventMediaDeletionResult,
        event_id: str,
        outcomes: dict[int, str],
        seen: set[str],
        index: int,
        target: _Target,
    ) -> None:
        if target.refusal:
            result.failures.append(MediaFailure(
                event_id, target.kind, target.refusal, target.stored,
            ))
            outcomes[index] = "failed"
            return
        resolved = target.resolved or ""
        if resolved in seen:
            outcomes[index] = "removed"
            return
        status, size = self._unlink_file(resolved, target.root)
        if status == "failed":
            result.failures.append(MediaFailure(
                event_id, target.kind, "unlink_failed", target.stored,
            ))
            outcomes[index] = "failed"
            return
        seen.add(resolved)
        outcomes[index] = status
        if status != "removed":
            return
        result.bytes_freed += size
        if target.counter == "thumbnails":
            result.thumbnails_deleted += 1
        elif target.counter == "videos":
            result.videos_deleted += 1
        elif target.counter == "clips":
            result.clips_deleted += 1
        else:
            result.frames_deleted += 1

    def reconcile_orphans(self, db: Session, *, dry_run: bool = True) -> OrphanMediaReport:
        """Report or delete media files that no event or entity still references.

        Reference lookup failure deletes nothing. Symlinks are never removed.
        """
        report = OrphanMediaReport(dry_run=dry_run)
        try:
            snapshot = self._reference_snapshot(db)
        except Exception:
            logger.exception("Orphan media reference lookup failed; deleting nothing")
            report.skipped = True
            report.skip_reason = "reference_lookup_failed"
            return report

        for kind, root, protected_rels, protected_reals in (
            ("thumbnail", self.thumbnail_root, snapshot["thumb_rels"], snapshot["thumb_reals"]),
            ("frame", self.frames_root, snapshot["frame_rels"], snapshot["frame_reals"]),
            ("video", self.video_root, snapshot["video_rels"], snapshot["video_reals"]),
            ("clip", self.clips_root, snapshot["clip_rels"], snapshot["clip_reals"]),
        ):
            self._sweep_root(
                report,
                kind=kind,
                root=root,
                protected_rels=protected_rels,
                protected_reals=protected_reals,
                live_frame_dirs=snapshot["live_ids"] if kind == "frame" else None,
            )
        return report

    def _enumerate(self, db: Session, event: Event) -> list[_Target]:
        targets: list[_Target] = []
        self._add_thumbnail(targets, event)
        self._add_frames(db, targets, event)
        self._add_video(targets, event)
        self._add_clips(targets, event)
        return targets

    def _add_thumbnail(self, targets: list[_Target], event: Event) -> None:
        stored = getattr(event, "thumbnail_path", None)
        if not stored or not str(stored).strip():
            return
        stored = str(stored).strip()
        resolved = resolve_thumbnail_fs_path(stored, self.thumbnail_root)
        refusal = None if resolved else "outside_root"
        if resolved and os.path.islink(resolved):
            refusal = "symlink"
            resolved = None
        targets.append(_Target(
            kind="thumbnail",
            stored=stored,
            root=self.thumbnail_root,
            resolved=resolved,
            refusal=refusal,
            clear_group="thumbnail",
            counter="thumbnails",
        ))
        if refusal:
            # The annotated sibling is addressed from the stored thumbnail.
            # Keep that pointer until the stored path itself is usable.
            return
        sibling = annotated_sibling_path(resolved)
        sibling_refusal = None
        if os.path.islink(sibling) or not _is_within_directory(sibling, self.thumbnail_root):
            sibling_refusal = "symlink" if os.path.islink(sibling) else "outside_root"
            sibling = None
        targets.append(_Target(
            kind="annotated_thumbnail",
            stored=stored,
            root=self.thumbnail_root,
            resolved=sibling,
            refusal=sibling_refusal,
            clear_group="thumbnail",
            counter="thumbnails",
        ))

    def _add_frames(self, db: Session, targets: list[_Target], event: Event) -> None:
        rows = db.query(EventFrame).filter(EventFrame.event_id == event.id).all()
        for row in rows:
            stored = str(row.frame_path or "")
            resolved, refusal = self._resolve_frame_path(stored, event.id)
            if resolved and os.path.islink(resolved):
                refusal = "symlink"
                resolved = None
            if resolved or refusal:
                targets.append(_Target(
                    kind="frame",
                    stored=stored or f"frame:{row.frame_number}",
                    root=self.frames_root,
                    resolved=resolved,
                    refusal=refusal,
                    frame_id=row.id,
                    clear_group=f"frame:{row.id}",
                    counter="frames",
                ))
            canonical, canonical_refusal = self._canonical_frame(event.id, row.frame_number)
            if canonical and resolved and os.path.normpath(canonical) == os.path.normpath(resolved):
                continue
            if canonical or canonical_refusal:
                targets.append(_Target(
                    kind="frame",
                    stored=f"frame_{row.frame_number:03d}.jpg",
                    root=self.frames_root,
                    resolved=canonical,
                    refusal=canonical_refusal,
                    frame_id=row.id,
                    clear_group=f"frame:{row.id}",
                    counter="frames",
                ))

        event_dir, dir_refusal = self._event_frame_dir(event.id)
        if dir_refusal:
            targets.append(_Target(
                kind="frame",
                stored=event.id,
                root=self.frames_root,
                refusal=dir_refusal,
                counter="frames",
            ))
            return
        if not event_dir or not os.path.isdir(event_dir):
            return
        known = {
            os.path.normpath(target.resolved)
            for target in targets
            if target.resolved
        }
        for name in os.listdir(event_dir):
            full = os.path.join(event_dir, name)
            if os.path.islink(full):
                targets.append(_Target(
                    kind="other",
                    stored=name,
                    root=self.frames_root,
                    refusal="symlink",
                    counter="frames",
                ))
                continue
            if not os.path.isfile(full):
                continue
            if not _is_within_directory(full, event_dir):
                targets.append(_Target(
                    kind="other",
                    stored=name,
                    root=self.frames_root,
                    refusal="outside_root",
                    counter="frames",
                ))
                continue
            if os.path.normpath(full) in known:
                continue
            targets.append(_Target(
                kind="other",
                stored=name,
                root=self.frames_root,
                resolved=full,
                counter="frames",
            ))

    def _add_video(self, targets: list[_Target], event: Event) -> None:
        stored = getattr(event, "video_path", None)
        if stored and str(stored).strip():
            stored = str(stored).strip()
            resolved, refusal = self._resolve_media_file(
                stored, self.video_root, _VIDEO_PREFIXES,
            )
            if resolved and os.path.islink(resolved):
                refusal = "symlink"
                resolved = None
            targets.append(_Target(
                kind="video",
                stored=stored,
                root=self.video_root,
                resolved=resolved,
                refusal=refusal,
                clear_group="video",
                counter="videos",
            ))
        canonical, canonical_refusal = self._canonical_file(self.video_root, event.id, ".mp4")
        if canonical_refusal or (canonical and os.path.exists(canonical)):
            already = any(
                target.resolved and canonical
                and os.path.normpath(target.resolved) == os.path.normpath(canonical)
                for target in targets
            )
            if not already:
                targets.append(_Target(
                    kind="video",
                    stored=f"{event.id}.mp4",
                    root=self.video_root,
                    resolved=None if canonical_refusal else canonical,
                    refusal=canonical_refusal,
                    counter="videos",
                ))

    def _add_clips(self, targets: list[_Target], event: Event) -> None:
        for name in (f"{event.id}.mp4", f"reanalyze_{event.id}.mp4"):
            if not _SAFE_ID.match(event.id):
                targets.append(_Target(
                    kind="clip",
                    stored=name,
                    root=self.clips_root,
                    refusal="unsafe_event_id",
                    counter="clips",
                ))
                continue
            path = os.path.join(self.clips_root, name)
            if os.path.islink(path):
                targets.append(_Target(
                    kind="clip",
                    stored=name,
                    root=self.clips_root,
                    refusal="symlink",
                    counter="clips",
                ))
                continue
            if not os.path.exists(path):
                continue
            if not _is_within_directory(path, self.clips_root):
                targets.append(_Target(
                    kind="clip",
                    stored=name,
                    root=self.clips_root,
                    refusal="outside_root",
                    counter="clips",
                ))
                continue
            targets.append(_Target(
                kind="clip",
                stored=name,
                root=self.clips_root,
                resolved=path,
                counter="clips",
            ))

    def _apply_pointer_updates(
        self,
        db: Session,
        event: Event,
        targets: list[_Target],
        outcomes: dict[int, str],
        *,
        partial: bool,
    ) -> None:
        groups: dict[str, list[int]] = {}
        for index, target in enumerate(targets):
            if target.clear_group:
                groups.setdefault(target.clear_group, []).append(index)

        def group_ok(name: str) -> bool:
            indexes = groups.get(name, [])
            return bool(indexes) and all(outcomes.get(i) in {"removed", "missing"} for i in indexes)

        if partial and group_ok("thumbnail"):
            event.thumbnail_path = None
        if partial and group_ok("video"):
            event.video_path = None

        if partial:
            cleared_frames = [
                targets[indexes[0]].frame_id
                for name, indexes in groups.items()
                if name.startswith("frame:") and group_ok(name) and targets[indexes[0]].frame_id
            ]
            if cleared_frames:
                db.query(EventFrame).filter(EventFrame.id.in_(cleared_frames)).delete(
                    synchronize_session=False
                )

        if not partial:
            event_dir, dir_refusal = self._event_frame_dir(event.id)
            if event_dir and not dir_refusal and os.path.isdir(event_dir) and not os.path.islink(event_dir):
                try:
                    if not os.listdir(event_dir):
                        os.rmdir(event_dir)
                except OSError:
                    logger.warning(
                        "Could not remove empty event frame directory",
                        extra={"event_id": event.id},
                    )

    def _unlink_file(self, path: str, root: str) -> tuple[str, int]:
        if not path or os.path.islink(path) or not _is_within_directory(path, root):
            return "failed", 0
        if not os.path.exists(path):
            return "missing", 0
        if not os.path.isfile(path):
            return "failed", 0
        try:
            size = os.path.getsize(path)
            self._unlink(path)
        except OSError:
            logger.warning("Failed to unlink media file", extra={"kind": "unlink_failed"})
            return "failed", 0
        return "removed", size

    def _resolve_frame_path(self, stored: str, event_id: str) -> tuple[Optional[str], Optional[str]]:
        raw = (stored or "").strip()
        if not raw:
            return None, None
        normalized = raw.replace("\\", "/")
        if normalized.startswith(_FRAME_PREFIX):
            return self._confine(_safe_join(self.frames_root, normalized[len(_FRAME_PREFIX):]), self.frames_root)
        if os.path.isabs(raw):
            if _is_within_directory(raw, self.frames_root) and not os.path.islink(raw):
                return os.path.normpath(raw), None
            return None, "outside_root"
        if not _SAFE_ID.match(event_id):
            return None, "unsafe_event_id"
        return self._confine(
            _safe_join(os.path.join(self.frames_root, event_id), normalized),
            self.frames_root,
        )

    def _canonical_frame(self, event_id: str, frame_number: Optional[int]) -> tuple[Optional[str], Optional[str]]:
        if frame_number is None:
            return None, None
        event_dir, refusal = self._event_frame_dir(event_id)
        if refusal or not event_dir:
            return None, refusal or "unsafe_event_id"
        return os.path.join(event_dir, f"frame_{int(frame_number):03d}.jpg"), None

    def _event_frame_dir(self, event_id: str) -> tuple[Optional[str], Optional[str]]:
        if not _SAFE_ID.match(event_id or ""):
            return None, "unsafe_event_id"
        candidate = os.path.join(self.frames_root, event_id)
        if os.path.islink(candidate):
            return None, "symlink"
        if not _is_within_directory(candidate, self.frames_root):
            return None, "outside_root"
        return candidate, None

    def _canonical_file(self, root: str, event_id: str, suffix: str) -> tuple[Optional[str], Optional[str]]:
        if not _SAFE_ID.match(event_id or ""):
            return None, "unsafe_event_id"
        candidate = os.path.join(root, f"{event_id}{suffix}")
        if os.path.islink(candidate):
            return None, "symlink"
        if not _is_within_directory(candidate, root):
            return None, "outside_root"
        return candidate, None

    def _resolve_media_file(
        self,
        stored: str,
        root: str,
        prefixes: tuple[str, ...],
    ) -> tuple[Optional[str], Optional[str]]:
        raw = stored.strip().replace("\\", "/").split("?", 1)[0].split("#", 1)[0]
        if ".." in raw.split("/"):
            return None, "outside_root"
        for prefix in prefixes:
            if raw.startswith(prefix):
                return self._confine(_safe_join(root, raw[len(prefix):]), root)
        if os.path.isabs(stored.strip()):
            if _is_within_directory(stored.strip(), root) and not os.path.islink(stored.strip()):
                return os.path.normpath(stored.strip()), None
            return None, "outside_root"
        return self._confine(_safe_join(root, raw), root)

    @staticmethod
    def _confine(path: Optional[str], root: str) -> tuple[Optional[str], Optional[str]]:
        if not path or not _is_within_directory(path, root):
            return None, "outside_root"
        if os.path.islink(path):
            return None, "symlink"
        return path, None

    def _reference_snapshot(self, db: Session) -> dict:
        from app.models.recognized_entity import RecognizedEntity

        live_ids: set[str] = set()
        thumb_rels: set[str] = set()
        video_rels: set[str] = set()
        clip_rels: set[str] = set()
        frame_rels: set[str] = set()
        thumb_reals: set[str] = set()
        video_reals: set[str] = set()
        clip_reals: set[str] = set()
        frame_reals: set[str] = set()

        for event_id, thumbnail_path, video_path in db.query(
            Event.id, Event.thumbnail_path, Event.video_path
        ).all():
            live_ids.add(event_id)
            key = _thumbnail_relative_key(thumbnail_path, self.thumbnail_root)
            if key:
                thumb_rels.add(key)
                thumb_rels.add(annotated_sibling_path(key).replace(os.sep, "/"))
            if video_path:
                resolved, refusal = self._resolve_media_file(
                    str(video_path), self.video_root, _VIDEO_PREFIXES,
                )
                if resolved and not refusal:
                    video_rels.add(os.path.relpath(resolved, self.video_root).replace(os.sep, "/"))
                    video_reals.add(os.path.realpath(resolved))
            if _SAFE_ID.match(event_id):
                video_rels.add(f"{event_id}.mp4")
                clip_rels.add(f"{event_id}.mp4")
                clip_rels.add(f"reanalyze_{event_id}.mp4")
                frame_rels.add(event_id)

        for (stored,) in db.query(RecognizedEntity.thumbnail_path).all():
            key = _thumbnail_relative_key(stored, self.thumbnail_root)
            if key:
                thumb_rels.add(key)
                thumb_rels.add(annotated_sibling_path(key).replace(os.sep, "/"))

        for (frame_path,) in db.query(EventFrame.frame_path).all():
            raw = str(frame_path or "").replace("\\", "/")
            if raw.startswith(_FRAME_PREFIX):
                resolved, refusal = self._confine(
                    _safe_join(self.frames_root, raw[len(_FRAME_PREFIX):]),
                    self.frames_root,
                )
                if resolved and not refusal:
                    frame_rels.add(os.path.relpath(resolved, self.frames_root).replace(os.sep, "/"))
                    if os.path.exists(resolved) and not os.path.islink(resolved):
                        frame_reals.add(os.path.realpath(resolved))

        return {
            "live_ids": live_ids,
            "thumb_rels": thumb_rels,
            "thumb_reals": thumb_reals,
            "frame_rels": frame_rels,
            "frame_reals": frame_reals,
            "video_rels": video_rels,
            "video_reals": video_reals,
            "clip_rels": clip_rels,
            "clip_reals": clip_reals,
        }

    def _sweep_root(
        self,
        report: OrphanMediaReport,
        *,
        kind: str,
        root: str,
        protected_rels: set[str],
        protected_reals: set[str],
        live_frame_dirs: Optional[set[str]],
    ) -> None:
        if not os.path.isdir(root) or os.path.islink(root):
            return
        root_real = os.path.realpath(root)
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            if kind == "frame" and os.path.normpath(dirpath) == os.path.normpath(root):
                # Keep directories that still belong to a live event. Everything
                # under an unknown event directory is an orphan candidate.
                kept = []
                for name in list(dirnames):
                    child = os.path.join(dirpath, name)
                    if os.path.islink(child):
                        report.skipped_symlinks += 1
                        continue
                    if live_frame_dirs and name in live_frame_dirs:
                        continue
                    kept.append(name)
                dirnames[:] = kept
            else:
                kept_dirs = []
                for name in dirnames:
                    child = os.path.join(dirpath, name)
                    if os.path.islink(child):
                        report.skipped_symlinks += 1
                    elif _is_within_directory(child, root_real):
                        kept_dirs.append(name)
                dirnames[:] = kept_dirs

            for name in filenames:
                full = os.path.join(dirpath, name)
                if os.path.islink(full):
                    report.skipped_symlinks += 1
                    continue
                if not os.path.isfile(full) or not _is_within_directory(full, root_real):
                    continue
                relative = os.path.relpath(full, root).replace(os.sep, "/")
                real = os.path.realpath(full)
                if kind == "frame" and live_frame_dirs:
                    top = relative.split("/", 1)[0]
                    if top in live_frame_dirs:
                        continue
                if relative in protected_rels or real in protected_reals:
                    continue
                self._record_orphan(report, kind, full, relative)

        if not report.dry_run:
            self._remove_empty_dirs(root, live_frame_dirs if kind == "frame" else None)

    def _record_orphan(self, report: OrphanMediaReport, kind: str, full: str, relative: str) -> None:
        report.orphan_files += 1
        report.by_kind[kind] = report.by_kind.get(kind, 0) + 1
        if len(report.samples) < _SAMPLE_LIMIT:
            report.samples.append(f"{kind}:{relative}")
        try:
            size = os.path.getsize(full)
        except OSError:
            size = 0
        if report.dry_run:
            report.bytes += size
            return
        status, removed_size = self._unlink_file(full, self._root_for_kind(kind))
        if status == "removed":
            report.deleted_files += 1
            report.bytes += removed_size or size
        elif status == "missing":
            report.deleted_files += 1
        else:
            report.failed_files += 1

    def _root_for_kind(self, kind: str) -> str:
        return {
            "thumbnail": self.thumbnail_root,
            "frame": self.frames_root,
            "video": self.video_root,
            "clip": self.clips_root,
        }[kind]

    def _remove_empty_dirs(self, root: str, preserve_top: Optional[set[str]] = None) -> None:
        for dirpath, dirnames, filenames in os.walk(root, topdown=False, followlinks=False):
            if os.path.normpath(dirpath) == os.path.normpath(root) or os.path.islink(dirpath):
                continue
            relative = os.path.relpath(dirpath, root).replace(os.sep, "/")
            if preserve_top and relative.split("/", 1)[0] in preserve_top:
                continue
            if dirnames or filenames:
                continue
            if not _is_within_directory(dirpath, root):
                continue
            try:
                os.rmdir(dirpath)
            except OSError:
                logger.warning("Could not remove empty orphan directory")
