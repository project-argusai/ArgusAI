"""(d) Decode N low-res RTSPS substreams at full rate, keep 1 frame per
1/--fps seconds (the motion-gate input). Measures this process's CPU and RSS,
system CPU, and network bytes received. Uses PyAV; tries the VideoToolbox
hwaccel and falls back to software decode. Stream URLs come from the Protect
bootstrap in memory and are never printed. Stops on unhealthy /health.
"""
import argparse
import asyncio
import threading
import time

import psutil

from common import backend_healthy, emit, protect_client, summary


def low_urls(client):
    urls = []
    for cam in client.bootstrap.cameras.values():
        if not cam.is_connected:
            continue
        chs = [c for c in cam.channels if c.is_rtsp_enabled]
        if chs:
            ch = min(chs, key=lambda c: c.width * c.height)
            urls.append((ch.rtsps_url, f"{ch.width}x{ch.height}"))
    return urls


def _decode(url, fps, stop, hw, counters):
    import av
    kw = {}
    if hw:
        from av.codec.hwaccel import HWAccel
        kw["hwaccel"] = HWAccel(device_type="videotoolbox", allow_software_fallback=True)
    c = av.open(url, options={"rtsp_transport": "tcp"}, timeout=10, **kw)
    try:
        last = 0.0
        for frame in c.decode(video=0):
            counters["decoded"] += 1
            now = time.monotonic()
            if now - last >= 1.0 / fps:
                frame.to_ndarray(format="gray")  # what the motion gate would use
                counters["kept"] += 1
                last = now
            if stop.is_set():
                return
    finally:
        c.close()


def worker(i, url, fps, stop, stats, hw):
    """Decode until stop; VideoToolbox first, software if it fails; reconnect on drops."""
    counters = {"decoded": 0, "kept": 0}
    use_hw = hw
    while not stop.is_set():
        try:
            _decode(url, fps, stop, use_hw, counters)
        except Exception as e:  # noqa: BLE001
            key = f"{'hw' if use_hw else 'sw'}:{type(e).__name__}"
            stats["errors"][key] = stats["errors"].get(key, 0) + 1
            if use_hw:
                use_hw = False
                stats["hw_fallback"].append(i)
            else:
                stats["reconnects"] += 1
                time.sleep(2)
    stats["decoded"][i] = counters["decoded"]
    stats["kept"][i] = counters["kept"]
    stats["hw_final"][i] = use_hw


async def main(a):
    client = await protect_client()
    urls = low_urls(client)
    await client.close_session()
    if not urls:
        emit("substream_decode", {"blocker": "no RTSP-enabled channels on any camera"})
        return
    proc = psutil.Process()
    stop = threading.Event()
    stats = {"decoded": {}, "kept": {}, "errors": {}, "hw_fallback": [], "hw_final": {}, "reconnects": 0}
    net0 = psutil.net_io_counters().bytes_recv
    proc.cpu_percent(None); psutil.cpu_percent(None)
    ths = [threading.Thread(target=worker, args=(i, u, a.fps, stop, stats, not a.software), daemon=True)
           for i, (u, _) in enumerate(urls)]
    for t in ths:
        t.start()
    cpu, sys_cpu, rss, aborted = [], [], [], False
    t0 = time.time()
    while time.time() - t0 < a.seconds:
        await asyncio.sleep(a.sample)
        cpu.append(proc.cpu_percent(None)); sys_cpu.append(psutil.cpu_percent(None))
        rss.append(proc.memory_info().rss / 1e6)
        if not backend_healthy():
            aborted = True
            break
    stop.set()
    for t in ths:
        t.join(15)
    el = time.time() - t0
    mbps = (psutil.net_io_counters().bytes_recv - net0) * 8 / el / 1e6
    emit("substream_decode", {
        "streams": len(urls), "resolutions": [r for _, r in urls], "seconds": round(el),
        "hwaccel_requested": not a.software, "keep_fps": a.fps, "aborted_unhealthy": aborted,
        "process_cpu_pct_of_one_core": summary(cpu), "system_cpu_pct": summary(sys_cpu),
        "process_rss_mb": summary(rss), "host_rx_mbps_total": round(mbps, 2),
        "decoded_fps_per_stream": [round(stats["decoded"].get(i, 0) / el, 1) for i in range(len(urls))],
        "kept_frames": sum(stats["kept"].values()), "errors": stats["errors"],
        "hw_decode_streams": sum(1 for v in stats["hw_final"].values() if v), "reconnects": stats["reconnects"]})


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--seconds", type=int, default=3600)
    p.add_argument("--fps", type=float, default=1.0)
    p.add_argument("--sample", type=float, default=10.0)
    p.add_argument("--software", action="store_true")
    asyncio.run(main(p.parse_args()))
