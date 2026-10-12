"""Shared helpers for the Phase 0 benchmarks. Read-only against prod."""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
import urllib.request
from pathlib import Path

BACKEND = Path(os.environ.get("ARGUS_BACKEND") or Path(__file__).resolve().parents[2])
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

BENCH_DIR = Path(os.environ.get("BENCH_DIR", "/tmp/argus-bench"))
HEALTH_URL = os.environ.get("ARGUS_HEALTH_URL", "http://127.0.0.1:8000/health")


def bench_dir(sub: str = "") -> Path:
    p = BENCH_DIR / sub if sub else BENCH_DIR
    p.mkdir(parents=True, exist_ok=True, mode=0o700)
    return p


def backend_healthy(timeout: float = 5.0) -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=timeout) as r:
            return json.loads(r.read()).get("status") == "healthy"
    except Exception:
        return False


def require_healthy() -> None:
    if not backend_healthy():
        print(json.dumps({"abort": "backend /health not healthy"}))
        sys.exit(3)


def readonly_session():
    """SQLAlchemy session on the prod SQLite DB opened with mode=ro."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.core.config import settings

    url = settings.DATABASE_URL
    if not url.startswith("sqlite:///"):
        raise SystemExit("only SQLite is supported by this harness")
    path = Path(url[len("sqlite:///"):])
    if not path.is_absolute():
        path = (BACKEND / path).resolve()
    eng = create_engine(f"sqlite:///file:{path}?mode=ro&uri=true", connect_args={"uri": True})
    return sessionmaker(bind=eng)()


async def protect_client():
    """A fresh uiprotect client for the first configured controller (read-only use)."""
    from uiprotect import ProtectApiClient
    from app.models.protect_controller import ProtectController

    db = readonly_session()
    try:
        c = db.query(ProtectController).first()
        if c is None:
            raise SystemExit("no Protect controller configured")
        client = ProtectApiClient(
            host=c.host, port=c.port, username=c.username,
            password=c.get_decrypted_password(), verify_ssl=c.verify_ssl,
        )
    finally:
        db.close()
    await client.update()
    return client


def summary(values):
    v = sorted(values)
    if not v:
        return {"n": 0}
    def pct(p):
        return round(v[min(len(v) - 1, int(round(p * (len(v) - 1))))], 1)
    return {"n": len(v), "min": round(v[0], 1), "p50": pct(0.5), "p95": pct(0.95),
            "max": round(v[-1], 1), "mean": round(statistics.fmean(v), 1)}


def emit(name: str, data: dict) -> None:
    data = {"bench": name, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **data}
    print(json.dumps(data, indent=1))
    with open(bench_dir() / f"{name}.json", "w") as f:
        json.dump(data, f, indent=1)


def rtsps_urls(client, channel: str):
    """{cam_index: (protect_camera_id, url, 'WxH')} for the named channel (High/Medium/Low).
    URLs carry a secret token: never print or log them."""
    out = {}
    cams = [c for c in client.bootstrap.cameras.values() if c.is_connected]
    for i, cam in enumerate(cams):
        for ch in cam.channels:
            if ch.name.lower() == channel.lower() and ch.is_rtsp_enabled:
                out[i] = (cam.id, ch.rtsps_url, f"{ch.width}x{ch.height}")
    return out


def grab_frame(url: str, timeout: float = 10.0):
    """Open an RTSPS stream, return (PIL.Image, seconds) for the first decoded frame."""
    import av
    t = time.perf_counter()
    c = av.open(url, options={"rtsp_transport": "tcp"}, timeout=timeout)
    try:
        for frame in c.decode(video=0):
            img = frame.to_image()
            return img, time.perf_counter() - t
    finally:
        c.close()
    raise RuntimeError("no frame")
