"""Qwen Cloud client (OpenAI-compatible endpoint, stdlib only).

Used for script writing and storyboarding. Needs DASHSCOPE_API_KEY in
secrets.env or the environment (key starts with `sk-`, from qwencloud.com).
"""
import json
import os
import re
import urllib.request

from . import util


def api_key():
    return (os.environ.get("DASHSCOPE_API_KEY")
            or util.load_secrets().get("DASHSCOPE_API_KEY", ""))


def chat(system, user, cfg, max_tokens=1200):
    """One-shot chat completion against Qwen Cloud. Returns the reply text."""
    q = cfg.get("qwen", {})
    url = q.get("base_url", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
    url = url.rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": q.get("model", "qwen3.7-plus"),
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer %s" % api_key(),
    })
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode())
    return data["choices"][0]["message"]["content"].strip()


def _json_block(text):
    """Parse the first JSON array/object out of a reply (tolerates ``` fences)."""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    m = re.search(r"[\[{].*[\]}]", text, re.S)
    if not m:
        raise ValueError("no JSON in Qwen reply: %s" % text[:200])
    return json.loads(m.group(0))


STORYBOARD_SYSTEM = (
    "You are a storyboard artist for short vertical AI-generated videos. "
    "Given a narration split into scenes, write one text-to-video shot prompt "
    "per scene for the Wan video model. Keep characters, art style, palette "
    "and mood CONSISTENT across every shot: restate the same style descriptor "
    "in each prompt. Vertical 9:16 framing, cinematic, no on-screen text. "
    "Reply with ONLY a JSON array of strings, one prompt per scene, same order."
)


def storyboard(scenes, meta, cfg):
    """Turn narration scenes into per-scene Wan shot prompts (same length/order)."""
    theme = meta.get("image_theme", "") or meta.get("title", "")
    user = ("Global theme: %s\n\nScenes:\n%s"
            % (theme, "\n".join("%d. %s" % (i + 1, s) for i, s in enumerate(scenes))))
    prompts = _json_block(chat(STORYBOARD_SYSTEM, user, cfg))
    if not isinstance(prompts, list) or len(prompts) != len(scenes):
        raise ValueError("storyboard returned %s prompts for %d scenes"
                         % (len(prompts) if isinstance(prompts, list) else "?", len(scenes)))
    return [str(p) for p in prompts]
