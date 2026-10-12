"""Collect frames from real person/vehicle events for the Phase 0 VLM retest.

Runs outside ArgusAI. Polls the prod SQLite DB read-only (mode=ro) for new
Protect events with smart_detection_type person/vehicle, then saves:
  <out>/<event_id>_hq.jpg   one frame grabbed from the camera's High RTSPS channel
  <out>/<event_id>_thumb.jpg  a copy of ArgusAI's stored thumbnail
plus <out>/index.jsonl (event id, type, camera index, grab latency; no text).
<out> is chmod 700 and must never leave this host. Stops at --max-frames
events or --max-bytes, or when the stop file <out>/STOP exists.
Note: the grab happens after ArgusAI stores the event (poll lag + AI time), so
the subject may have left the frame; the thumbnail is the detection-time image.
"""
import argparse
import asyncio
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from common import BACKEND, grab_frame, protect_client, readonly_session

TYPES = ("person", "vehicle")


def dir_bytes(p: Path) -> int:
    return sum(f.stat().st_size for f in p.iterdir() if f.is_file())


async def main(a):
    from sqlalchemy import text
    out = Path(os.path.expanduser(a.out)); out.mkdir(mode=0o700, exist_ok=True); os.chmod(out, 0o700)
    idx = out / "index.jsonl"
    seen = set()
    if idx.exists():
        seen = {json.loads(l)["event_id"] for l in idx.read_text().splitlines() if l.strip()}
    since = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    client, urls, cam_ix, refreshed = None, {}, {}, 0.0
    while True:
        if (out / "STOP").exists() or len(seen) >= a.max_frames or dir_bytes(out) >= a.max_bytes:
            print(json.dumps({"stopped": True, "events": len(seen), "bytes": dir_bytes(out)}), flush=True)
            break
        if time.time() - refreshed > 3600:
            try:
                if client:
                    await client.close_session()
                client = await protect_client()
                cams = [c for c in client.bootstrap.cameras.values() if c.is_connected]
                urls = {c.id: next((ch.rtsps_url for ch in c.channels if ch.name == "High" and ch.is_rtsp_enabled), None) for c in cams}
                cam_ix = {c.id: i + 1 for i, c in enumerate(cams)}
                refreshed = time.time()
            except Exception as e:  # noqa: BLE001
                print(json.dumps({"protect_error": type(e).__name__}), flush=True)
                await asyncio.sleep(60); continue
        db = readonly_session()
        try:
            rows = db.execute(text(
                "SELECT e.id, e.smart_detection_type, e.thumbnail_path, c.protect_camera_id FROM events e "
                "JOIN cameras c ON c.id = e.camera_id WHERE e.source_type='protect' AND e.created_at >= :s "
                "AND e.smart_detection_type IN ('person','vehicle') ORDER BY e.created_at"), {"s": since}).fetchall()
        except Exception as e:  # noqa: BLE001
            rows = []
            print(json.dumps({"db_error": type(e).__name__}), flush=True)
        finally:
            db.close()
        for eid, etype, thumb, pcid in rows:
            if eid in seen:
                continue
            seen.add(eid)
            rec = {"event_id": eid, "type": etype, "cam": cam_ix.get(pcid), "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
            url = urls.get(pcid)
            if url:
                try:
                    img, s = await asyncio.to_thread(grab_frame, url)
                    img.save(out / f"{eid}_hq.jpg", quality=90)
                    rec.update(hq=f"{img.width}x{img.height}", grab_ms=round(s * 1000))
                except Exception as e:  # noqa: BLE001
                    rec["hq_error"] = type(e).__name__
            if thumb:
                rel = thumb.split("/thumbnails/", 1)[-1].lstrip("/")
                for src in (BACKEND / "data" / "thumbnails" / rel, BACKEND / "data" / thumb.lstrip("/")):
                    if src.is_file():
                        shutil.copyfile(src, out / f"{eid}_thumb.jpg"); rec["thumb"] = True
                        break
            for f in out.glob(f"{eid}_*.jpg"):
                os.chmod(f, 0o600)
            with open(idx, "a") as fh:
                fh.write(json.dumps(rec) + "\n")
            print(json.dumps({k: v for k, v in rec.items() if k != "event_id"}), flush=True)
        await asyncio.sleep(a.poll)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="~/argus-bench-frames")
    p.add_argument("--poll", type=float, default=5.0)
    p.add_argument("--max-frames", type=int, default=300)
    p.add_argument("--max-bytes", type=int, default=2 * 1024**3)
    asyncio.run(main(p.parse_args()))
