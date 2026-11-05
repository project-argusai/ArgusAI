"""On-demand full-res frame grab from the High/Medium RTSPS channel (software
decode, first decodable frame). Measures latency, resolution, success, and
this process's CPU and RSS. Frames are discarded. Numbers only."""
import argparse
import asyncio
import time

import psutil

from common import backend_healthy, emit, grab_frame, protect_client, require_healthy, rtsps_urls, summary


async def main(a):
    require_healthy()
    client = await protect_client()
    out = {"rounds": a.rounds}
    proc = psutil.Process()
    for chan in a.channels:
        urls = rtsps_urls(client, chan)
        lat, res, errs, per, cpu_s, rss = [], {}, {}, [], [], []
        for i, (_, url, cfg) in urls.items():
            cl = []
            for _ in range(a.rounds):
                if not backend_healthy():
                    out["aborted_unhealthy"] = True
                    break
                c0 = proc.cpu_times()
                try:
                    img, s = await asyncio.to_thread(grab_frame, url)
                    cl.append(s * 1000); lat.append(s * 1000)
                    k = f"{img.width}x{img.height}"; res[k] = res.get(k, 0) + 1
                except Exception as e:  # noqa: BLE001
                    errs[type(e).__name__] = errs.get(type(e).__name__, 0) + 1
                c1 = proc.cpu_times()
                cpu_s.append((c1.user + c1.system - c0.user - c0.system) * 1000)
                rss.append(proc.memory_info().rss / 1e6)
                await asyncio.sleep(a.gap)
            per.append({"cam": f"cam{i+1}", "configured": cfg, "ok": len(cl), "of": a.rounds, "latency_ms": summary(cl)})
        n = len(urls) * a.rounds
        out[chan] = {"attempts": n, "success": len(lat), "success_rate": round(len(lat) / n, 3) if n else None,
                     "latency_ms": summary(lat), "resolutions": res, "errors": errs,
                     "cpu_ms_per_grab": summary(cpu_s), "process_rss_mb": summary(rss), "per_camera": per}
    await client.close_session()
    emit("frame_grab", out)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--channels", nargs="+", default=["High", "Medium"])
    p.add_argument("--rounds", type=int, default=5)
    p.add_argument("--gap", type=float, default=3.0)
    asyncio.run(main(p.parse_args()))
