"""(c) RF-DETR vs YOLOX on CoreML: per-frame latency and memory. Apache-2.0
models only (RF-DETR base nano/small, YOLOX-nano/tiny/s). No Ultralytics.

Run in a separate venv (not the backend venv):
  python -m venv $BENCH_DIR/venv && $BENCH_DIR/venv/bin/pip install \
      coremltools onnx onnxruntime rfdetr psutil numpy pillow
YOLOX ONNX files come from the official release (Megvii-BaseDetection/YOLOX
v0.1.1rc0, *.onnx). Convert with --convert, then benchmark the .mlpackage
on ALL / CPU_AND_NE / CPU_ONLY compute units with synthetic input (no camera
images needed for latency).
"""
import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
import psutil


def bench_onnx_coreml_ep(path, shape, iters):
    import onnxruntime as ort
    res = {}
    for name, provs in {"ort_coreml": [("CoreMLExecutionProvider", {"MLComputeUnits": "ALL"}), "CPUExecutionProvider"],
                        "ort_cpu": ["CPUExecutionProvider"]}.items():
        try:
            s = ort.InferenceSession(str(path), providers=provs)
            inp = s.get_inputs()[0]
            x = np.random.rand(*shape).astype(np.float32)
            for _ in range(5):
                s.run(None, {inp.name: x})
            ts = []
            for _ in range(iters):
                t = time.perf_counter(); s.run(None, {inp.name: x}); ts.append((time.perf_counter() - t) * 1000)
            ts.sort()
            res[name] = {"p50_ms": round(ts[len(ts) // 2], 2), "p95_ms": round(ts[int(len(ts) * .95)], 2),
                         "rss_mb": round(psutil.Process().memory_info().rss / 1e6)}
        except Exception as e:  # noqa: BLE001
            res[name] = {"error": f"{type(e).__name__}: {str(e)[:120]}"}
    return res


def bench_mlpackage(path, shape, iters):
    import coremltools as ct
    res = {}
    for cu in ("ALL", "CPU_AND_NE", "CPU_ONLY"):
        try:
            m = ct.models.MLModel(str(path), compute_units=getattr(ct.ComputeUnit, cu))
            name = m.get_spec().description.input[0].name
            x = {name: np.random.rand(*shape).astype(np.float32)}
            for _ in range(5):
                m.predict(x)
            ts = []
            for _ in range(iters):
                t = time.perf_counter(); m.predict(x); ts.append((time.perf_counter() - t) * 1000)
            ts.sort()
            res[cu] = {"p50_ms": round(ts[len(ts) // 2], 2), "p95_ms": round(ts[int(len(ts) * .95)], 2),
                       "rss_mb": round(psutil.Process().memory_info().rss / 1e6)}
        except Exception as e:  # noqa: BLE001
            res[cu] = {"error": f"{type(e).__name__}: {str(e)[:120]}"}
    return res


def main(a):
    out = {}
    for spec in a.models:
        name, path, size = spec.split(":")
        size = int(size)
        shape = (1, 3, size, size)
        p = Path(path)
        r = {"input": size}
        if p.suffix == ".onnx":
            r.update(bench_onnx_coreml_ep(p, shape, a.iters))
            if a.convert:
                try:
                    import coremltools as ct
                    import onnx  # noqa: F401
                    r["convert_note"] = "coremltools>=7 no longer converts ONNX; use the ORT CoreML EP numbers"
                except Exception:
                    pass
        else:
            r.update(bench_mlpackage(p, shape, a.iters))
        out[name] = r
        print(json.dumps({name: r}), flush=True)
    d = Path(os.environ.get("BENCH_DIR", "/tmp/argus-bench")); d.mkdir(parents=True, exist_ok=True)
    (d / "detector_coreml.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("models", nargs="+", help="name:path:input_size (onnx or mlpackage)")
    p.add_argument("--iters", type=int, default=100)
    p.add_argument("--convert", action="store_true")
    main(p.parse_args())
