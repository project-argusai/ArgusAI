# Local-first Phase 0 benchmarks

Read-only benchmarks for the local-first plan (see the linked issue). They never
write to the ArgusAI database, `.env`, or daemons, and they print numbers only:
no images, descriptions, camera names, IDs, or URLs.

Run from `backend/` with the backend venv. Put scratch output in a temp dir
outside the repo (`BENCH_DIR`, default `/tmp/argus-bench`) and delete it after.

| Script | Benchmark |
|---|---|
| `common.py` | read-only DB access, Protect client, `/health` guard, stats helpers |
| `protect_snapshot_bench.py` | (b) full-res snapshot latency/reliability, plus RTSP channel inventory (no URLs) |
| `vlm_blank_rate.py` | (a) blank-description rate: current prompt path vs Ollama JSON-schema `format` |
| `detector_coreml_bench.py` | (c) RF-DETR vs YOLOX (Apache-2.0) on CoreML: latency, memory |
| `substream_decode_bench.py` | (d) N x low-res RTSPS decode at full rate, keep 1-2 fps: CPU, RSS, network |
| `vlm_burst_bench.py` | (e) burst of N queued VLM requests (`--prompt production` default): queue wait, p50/p95, memory, swap |
| `frame_grab_bench.py` | on-demand full-res frame grab from High/Medium RTSPS: latency, resolution, CPU, RSS |
| `event_frame_collector.py`, `collector_ctl.sh` | collects High-stream frames + thumbnails for real person/vehicle events into `~/argus-bench-frames` (700, never leaves the host), capped at 300 events / 2 GB |

Every long-running script polls `http://127.0.0.1:8000/health` and stops if it
is not `healthy`.
