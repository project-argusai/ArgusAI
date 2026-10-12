"""(e) Burst load on the local VLM: N requests queued at once, served one at a
time (matching LOCAL_VLM concurrency 1). Reports queue wait, service time,
end-to-end latency, peak Ollama RSS, swap delta. Numbers only. Stops on
unhealthy /health.
"""
import argparse
import asyncio
import base64
import json
import time
import urllib.request
from pathlib import Path

import psutil

from common import backend_healthy, emit, summary


def call(base, model, img):
    body = {"model": model, "stream": False, "keep_alive": "10m", "options": {"num_predict": 300},
            "messages": [{"role": "user", "content": "Describe this security camera image in one sentence.",
                          "images": [img]}]}
    req = urllib.request.Request(f"{base}/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        r.read()


def ollama_rss_mb():
    tot = 0
    for p in psutil.process_iter(["name", "memory_info"]):
        if "ollama" in (p.info["name"] or "").lower():
            tot += p.info["memory_info"].rss
    return tot / 1e6


async def main(a):
    from app.services.ai_providers.local_provider import downscale_image_base64
    imgs = sorted(Path(a.images).glob("*.jpg"))
    b64s = [downscale_image_base64(base64.b64encode(p.read_bytes()).decode(), 1024) for p in imgs]
    await asyncio.to_thread(call, a.ollama, a.model, b64s[0])  # warm
    swap0 = psutil.swap_memory().used
    peak = {"rss": 0.0, "sys_used_pct": 0.0}
    stop = False

    async def sampler():
        while not stop:
            peak["rss"] = max(peak["rss"], ollama_rss_mb())
            peak["sys_used_pct"] = max(peak["sys_used_pct"], psutil.virtual_memory().percent)
            await asyncio.sleep(1)

    s = asyncio.create_task(sampler())
    t0 = time.perf_counter()
    q = asyncio.Queue()
    for i in range(a.burst):
        q.put_nowait((i, t0))
    waits, svc, e2e, aborted = [], [], [], False
    while not q.empty():
        if not backend_healthy():
            aborted = True
            break
        i, enq = await q.get()
        st = time.perf_counter()
        await asyncio.to_thread(call, a.ollama, a.model, b64s[i % len(b64s)])
        en = time.perf_counter()
        waits.append(st - enq); svc.append(en - st); e2e.append(en - enq)
    stop = True
    await s
    emit("vlm_burst", {"model": a.model, "burst": a.burst, "completed": len(svc), "aborted_unhealthy": aborted,
                       "queue_wait_s": summary(waits), "service_s": summary(svc), "end_to_end_s": summary(e2e),
                       "drain_s": round(time.perf_counter() - t0, 1),
                       "throughput_per_min": round(60 * len(svc) / max(1e-6, sum(svc)), 2),
                       "ollama_peak_rss_mb": round(peak["rss"]), "system_mem_peak_pct": peak["sys_used_pct"],
                       "swap_delta_mb": round((psutil.swap_memory().used - swap0) / 1e6)})


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--images", required=True)
    p.add_argument("--burst", type=int, default=10)
    p.add_argument("--model", default="qwen3-vl:4b-instruct")
    p.add_argument("--ollama", default="http://127.0.0.1:11434")
    asyncio.run(main(p.parse_args()))
