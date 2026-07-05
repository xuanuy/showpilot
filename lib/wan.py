"""Wan text-to-video client (Qwen Cloud / DashScope async task API, stdlib only).

Create task -> poll -> download. Generated clips are cached by the caller
(each Wan second costs real credits), so a re-run never re-renders a scene.
"""
import json
import time
import urllib.request

from .qwen import api_key


def _req(url, body=None, headers=None):
    h = {"Authorization": "Bearer %s" % api_key()}
    h.update(headers or {})
    data = json.dumps(body).encode() if body is not None else None
    if data:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def create_task(prompt, duration, cfg):
    w = cfg["wan"]
    base = w.get("base_url", "https://dashscope-intl.aliyuncs.com/api/v1").rstrip("/")
    body = {
        "model": w.get("model", "wan2.6-t2v"),
        "input": {"prompt": prompt},
        "parameters": {
            "resolution": w.get("resolution", "720P"),
            "ratio": w.get("ratio", "9:16"),
            "duration": int(duration),
            "prompt_extend": True,
            "watermark": False,
        },
    }
    res = _req(base + "/services/aigc/video-generation/video-synthesis",
               body, {"X-DashScope-Async": "enable"})
    return res["output"]["task_id"]


def wait(task_id, cfg):
    """Poll until SUCCEEDED, return the (24h-valid) video URL."""
    w = cfg["wan"]
    base = w.get("base_url", "https://dashscope-intl.aliyuncs.com/api/v1").rstrip("/")
    interval = int(w.get("poll_seconds", 15))
    deadline = time.time() + int(w.get("timeout_seconds", 900))
    while time.time() < deadline:
        out = _req(base + "/tasks/" + task_id)["output"]
        st = out.get("task_status")
        if st == "SUCCEEDED":
            return out["video_url"]
        if st in ("FAILED", "CANCELED", "UNKNOWN"):
            raise RuntimeError("Wan task %s: %s (%s)"
                               % (st, out.get("message", ""), out.get("code", "")))
        time.sleep(interval)
    raise RuntimeError("Wan task timed out: %s" % task_id)


def generate(prompt, duration, out_mp4, cfg):
    """Render one shot. duration is clamped to the model's 2..15s range."""
    duration = max(2, min(15, int(round(duration))))
    tid = create_task(prompt, duration, cfg)
    print("    [wan] task %s (%ds) ..." % (tid[:16], duration))
    url = wait(tid, cfg)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=300) as r, open(out_mp4, "wb") as f:
        f.write(r.read())
    return out_mp4
