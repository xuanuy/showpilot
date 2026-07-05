"""Fetch a stock image per scene from Pexels (free API), by keywords.

Needs PEXELS_API_KEY in secrets.env (free at https://www.pexels.com/api/).
Falls back to a gradient placeholder if the key is missing or a search returns
nothing, so story builds never crash.
"""
import json
import os
import re
import urllib.parse
import urllib.request

from .util import run

STOP = set("""a an the of to and or but in on at for with from by as is are was were be been
being this that these those it its their his her your our my you we they he she i me him them
us not no yes do does did has have had will would can could should may might must over under
into out up down off about than then so very just more most some any all each every who what
which when where why how a's it's i'm you're they're""".split())


def keywords(text, theme="", n=3):
    """Pick a short search query from a scene's text + optional global theme."""
    words = re.findall(r"[A-Za-z]+", text.lower())
    picked = [w for w in words if w not in STOP and len(w) > 3]
    # keep order, dedupe
    seen, out = set(), []
    for w in picked:
        if w not in seen:
            seen.add(w); out.append(w)
        if len(out) >= n:
            break
    q = " ".join(out) if out else "cinematic background"
    return (theme + " " + q).strip()


def pexels_search(query, api_key, orientation="portrait"):
    url = "https://api.pexels.com/v1/search?" + urllib.parse.urlencode(
        {"query": query, "per_page": 1, "orientation": orientation})
    # Pexels blocks the default "Python-urllib" User-Agent (403), so set one.
    req = urllib.request.Request(url, headers={
        "Authorization": api_key, "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode())
    photos = data.get("photos", [])
    if not photos:
        return None
    src = photos[0]["src"]
    # prefer a large portrait render
    return src.get("portrait") or src.get("large2x") or src.get("large") or src.get("original")


def _download(img_url, path):
    req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r, open(path, "wb") as f:
        f.write(r.read())


def _placeholder(path, cfg, idx):
    """Gradient fallback so a missing image never breaks the build."""
    palette = ["0x1b2a4a:0x4a6fa5", "0x3a1b4a:0xa54a8f", "0x1b4a2a:0x6fa54a",
               "0x4a3a1b:0xa5894a", "0x1b3a4a:0x4a93a5"]
    c0, c1 = palette[idx % len(palette)].split(":")
    run([cfg["tools"]["ffmpeg"], "-y", "-v", "error",
         "-f", "lavfi", "-i",
         "gradients=s=1080x1920:c0=%s:c1=%s:duration=1" % (c0, c1),
         "-frames:v", "1", path])
    return path


def fetch_scene_image(scene_text, theme, idx, out_path, cfg, secrets):
    """Return out_path with a fetched (or placeholder) image. Never raises."""
    api_key = secrets.get("PEXELS_API_KEY", "")
    if api_key:
        try:
            q = keywords(scene_text, theme)
            url = pexels_search(q, api_key)
            if url:
                _download(url, out_path)
                if os.path.getsize(out_path) > 1000:
                    return out_path, q
        except Exception as e:
            print("    [pexels] %s -> fallback (%s)" % (scene_text[:30], e))
    _placeholder(out_path, cfg, idx)
    return out_path, "(placeholder)"
