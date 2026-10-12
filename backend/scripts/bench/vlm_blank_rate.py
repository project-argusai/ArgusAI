"""(a) Local VLM blank-description rate: current path vs JSON-schema output.

Variant "current": the production LocalVLMProvider with the production prompt
(OpenAI-compatible endpoint, response_format=json_object). Counted blank when
the provider fails with "no description" / empty reply.
Variant "schema": the same prompt sent to Ollama /api/chat with `format` set to
a JSON schema that requires a non-empty `description`.
Images are read from --images (on this host only). Only counts and timings are
printed; descriptions are never printed or stored.
"""
import argparse
import asyncio
import base64
import json
import time
import urllib.request
from pathlib import Path

from common import backend_healthy, emit, summary

SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string", "minLength": 1},
        "object_type": {"type": "string", "enum": ["person", "vehicle", "animal", "package", "none", "other"]},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
    },
    "required": ["description", "object_type", "confidence"],
}


def build_prompt():
    from app.services.ai_prompt_service import AIPromptService
    from app.services.identification import ensure_identification_prompt
    prompt, _ = AIPromptService().select_and_build_prompt(
        camera_id="bench", camera_name="Camera", custom_prompt=None, detected_objects=[],
        timestamp="12:00 PM", analysis_mode="single_image")
    return ensure_identification_prompt(prompt)


def ollama_schema_call(base, model, system, prompt, img_b64, timeout):
    body = {"model": model, "stream": False, "format": SCHEMA, "keep_alive": "10m",
            "options": {"temperature": 0.2, "num_predict": 1024},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt, "images": [img_b64]}]}
    req = urllib.request.Request(f"{base}/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    raw = out.get("message", {}).get("content", "")
    d = json.loads(raw)
    desc = (d.get("description") or "").strip()
    return bool(desc), d.get("object_type")


async def main(a):
    from app.services.ai_providers.local_provider import LocalVLMProvider, downscale_image_base64
    imgs = sorted(p for p in Path(a.images).iterdir() if p.suffix.lower() in (".jpg", ".jpeg"))[: a.limit]
    prov = LocalVLMProvider(base_url=f"{a.ollama}/v1", model=a.model, max_image_side=1024)
    prompt = build_prompt()
    res = {v: {"ok": 0, "blank": 0, "error": 0, "ms": [], "errors": {}, "object_type": {}} for v in a.variants}
    aborted = False
    for i, p in enumerate(imgs):
        if not backend_healthy():
            aborted = True
            break
        b64 = base64.b64encode(p.read_bytes()).decode()
        small = downscale_image_base64(b64, 1024)
        for v in a.variants:
            t = time.perf_counter()
            r = res[v]
            try:
                if v == "current":
                    out = await prov.generate_description(small, "Camera", "12:00 PM", [], custom_prompt=prompt,
                                                          request_timeout_s=a.timeout)
                    if out.success and out.description.strip():
                        r["ok"] += 1
                    elif "no description" in (out.error or "") or "empty response" in (out.error or ""):
                        r["blank"] += 1
                    else:
                        r["error"] += 1
                        k = (out.error or "?").split(":")[0]
                        r["errors"][k] = r["errors"].get(k, 0) + 1
                else:
                    has, ot = await asyncio.to_thread(ollama_schema_call, a.ollama, a.model, prov.system_prompt,
                                                      prompt, small, a.timeout)
                    r["ok" if has else "blank"] += 1
                    r["object_type"][str(ot)] = r["object_type"].get(str(ot), 0) + 1
            except Exception as e:  # noqa: BLE001
                r["error"] += 1
                r["errors"][type(e).__name__] = r["errors"].get(type(e).__name__, 0) + 1
            r["ms"].append((time.perf_counter() - t) * 1000)
        print(f"{i+1}/{len(imgs)}", flush=True)
    out = {"model": a.model, "images": len(imgs), "aborted_unhealthy": aborted}
    for v, r in res.items():
        n = r["ok"] + r["blank"] + r["error"]
        out[v] = {"n": n, "ok": r["ok"], "blank": r["blank"], "error": r["error"],
                  "blank_rate": round(r["blank"] / n, 3) if n else None,
                  "usable_rate": round(r["ok"] / n, 3) if n else None,
                  "latency_ms": summary(r["ms"][1:] if len(r["ms"]) > 1 else r["ms"]),
                  "errors": r["errors"], "object_type": r["object_type"]}
    emit("vlm_blank_rate", out)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--images", required=True)
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--model", default="qwen3-vl:4b-instruct")
    p.add_argument("--ollama", default="http://127.0.0.1:11434")
    p.add_argument("--timeout", type=float, default=90)
    p.add_argument("--variants", nargs="+", default=["current", "schema"])
    asyncio.run(main(p.parse_args()))
