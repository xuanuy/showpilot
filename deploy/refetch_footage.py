#!/usr/bin/env python3
"""Re-download footage for every topic that has an http `source:` but no footage
file yet. Lets a fresh machine rebuild its footage from recorded sources instead
of transferring large mp4s. Idempotent (skips topics that already have footage).
"""
import glob
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import util

ROOT = util.ROOT
CFG = util.load_config()
YT = os.path.expanduser("~/.local/bin/yt-dlp")
FFDIR = os.path.dirname(CFG["tools"]["ffmpeg"])

for tp in sorted(glob.glob(os.path.join(ROOT, "channels", "*", "topics", "*.md"))):
    meta, _ = util.parse_topic(tp)
    src = meta.get("source", "").strip()
    fn = meta.get("footage", "").strip()
    if not fn or not src.startswith("http"):
        continue
    cdir = os.path.dirname(os.path.dirname(tp))      # channels/<id>
    out = os.path.join(cdir, "footage", fn)
    if os.path.exists(out):
        print("have:", out)
        continue
    os.makedirs(os.path.dirname(out), exist_ok=True)
    print("download:", fn, "<-", src)
    try:
        subprocess.run([YT, "--no-warnings", "--force-overwrites",
                        "--ffmpeg-location", FFDIR,
                        "-f", "bv*[ext=mp4][height<=1080]+ba[ext=m4a]/b[ext=mp4]/b",
                        "--merge-output-format", "mp4", "-o", out, src], timeout=600)
    except Exception as e:
        print("  ! failed:", e)
