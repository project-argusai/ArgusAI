"""(b) Full-res Protect snapshot latency and reliability. Read-only.

Takes --rounds snapshots per camera, sequentially, with --gap seconds between
calls. Bytes are discarded unless --save is given, in which case JPEGs go to
$BENCH_DIR/snaps (mode 700, on this host only) for the VLM benchmark.
Also reports, per camera, which RTSP channels are enabled and their
resolution/bitrate/fps. Stream URLs are never printed.
"""
import argparse
import asyncio
import io
import time

from common import bench_dir, emit, protect_client, require_healthy, summary


async def main(a):
    require_healthy()
    from PIL import Image
    client = await protect_client()
    cams = [c for c in client.bootstrap.cameras.values() if c.is_connected]
    snaps = bench_dir("snaps") if a.save else None
    channels, lat, sizes, res, errors, per_cam = [], [], [], {}, {}, []
    for i, cam in enumerate(cams):
        chs = []
        for ch in cam.channels:
            chs.append({"name": ch.name, "w": ch.width, "h": ch.height, "fps": ch.fps,
                        "kbps": round((ch.bitrate or 0) / 1000), "rtsp_enabled": bool(ch.is_rtsp_enabled)})
        channels.append({"cam": f"cam{i+1}", "channels": chs})
        cam_lat, ok = [], 0
        for r in range(a.rounds):
            t = time.perf_counter()
            try:
                w_req = a.width or max(ch.width for ch in cam.channels)
                data = await asyncio.wait_for(client.get_camera_snapshot(cam.id, width=w_req), a.timeout)
                ms = (time.perf_counter() - t) * 1000
                if not data:
                    raise ValueError("empty")
                ok += 1
                cam_lat.append(ms); lat.append(ms); sizes.append(len(data) / 1024)
                w, h = Image.open(io.BytesIO(data)).size
                res[f"{w}x{h}"] = res.get(f"{w}x{h}", 0) + 1
                if snaps:
                    (snaps / f"cam{i+1}_{r:03d}.jpg").write_bytes(data)
            except Exception as e:  # noqa: BLE001
                errors[type(e).__name__] = errors.get(type(e).__name__, 0) + 1
            await asyncio.sleep(a.gap)
        per_cam.append({"cam": f"cam{i+1}", "ok": ok, "of": a.rounds, "latency_ms": summary(cam_lat)})
        require_healthy()
    await client.close_session()
    total = len(cams) * a.rounds
    emit("protect_snapshot", {
        "cameras": len(cams), "attempts": total, "success": len(lat),
        "success_rate": round(len(lat) / total, 3) if total else None,
        "latency_ms": summary(lat), "size_kb": summary(sizes), "resolutions": res,
        "errors": errors, "per_camera": per_cam, "rtsp_channels": channels,
    })


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--rounds", type=int, default=10)
    p.add_argument("--gap", type=float, default=3.0)
    p.add_argument("--width", type=int, default=None, help="default: the camera's High channel width (Protect returns 640px if no width is given)")
    p.add_argument("--timeout", type=float, default=15.0)
    p.add_argument("--save", action="store_true")
    asyncio.run(main(p.parse_args()))
