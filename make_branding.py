#!/usr/bin/env python3
"""Generate a Facebook avatar (500x500) + cover/banner (1640x924) for each channel.

Avatar  = themed gradient + the page name (clean, readable inside a circle).
Cover   = a Pexels stock photo (darkened) + page name + tagline.

Output: assets/branding/<channel-id>/{avatar.png, cover.png}
Run:    python3 make_branding.py [channel-id ...]   (default: all channels)
Needs PEXELS_API_KEY for cover photos; falls back to a gradient cover without it.
"""
import os
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipeline
from lib import util, images
from lib.util import run

CFG = pipeline.CFG
ROOT = util.ROOT
FF = CFG["tools"]["ffmpeg"]
FONT = CFG["captions"]["font_file"] if os.path.exists(
    CFG["captions"].get("font_file", "")) else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# per-channel look: gradient colors (avatar) + a cover photo search theme
LOOK = {
    "donghua-decoded":        ("0x10243f:0x2d6cdf", "chinese mountains mist fantasy"),
    "qi-and-swords":          ("0x3a0d12:0xc0392b", "dramatic storm clouds lightning"),
    "donghua-realm":          ("0x16121f:0x6c3fb5", "starry night sky galaxy"),
    "xianxia-daily":          ("0x0d2a26:0x16a085", "misty bamboo forest morning"),
    "cultivation-chronicles": ("0x2a1f0d:0xb5893f", "ancient temple mountains sunrise"),
    "immortal-path":          ("0x0d1a2a:0x3f7fb5", "lone mountain peak clouds"),
    "dao-of-donghua":         ("0x241a0d:0xd98c1f", "ink painting landscape china"),
    "heavenly-donghua":       ("0x1a0d2a:0x9b59b6", "aurora dramatic sky cinematic"),
    "life-stories":           ("0x2a1c0d:0xd9893f", "warm cozy sunset window"),
}


def _textfile(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path.replace("\\", "/").replace(":", r"\:")


def avatar(cid, name, c0, c1, out, tmp):
    """500x500 gradient + page name (wrapped, centered)."""
    wrapped = "\n".join(textwrap.wrap(name, width=10)) or name
    tf = _textfile(os.path.join(tmp, "av.txt"), wrapped)
    run([FF, "-y", "-v", "error",
         "-f", "lavfi", "-i", "gradients=s=500x500:c0=%s:c1=%s:duration=1" % (c0, c1),
         "-frames:v", "1",
         "-vf", ("drawtext=textfile='%s':fontfile=%s:fontcolor=white:fontsize=64:"
                 "line_spacing=8:x=(w-text_w)/2:y=(h-text_h)/2:"
                 "shadowcolor=black@0.6:shadowx=2:shadowy=2" % (tf, FONT)),
         out])
    return out


def cover(cid, name, tagline, c0, c1, theme, out, tmp, secrets):
    """1640x924 stock photo (darkened) + name + tagline; text kept center-safe."""
    W, H = 1640, 924
    photo = os.path.join(tmp, "cover_src.jpg")
    got = False
    api = secrets.get("PEXELS_API_KEY", "")
    if api:
        try:
            url = images.pexels_search(theme, api, orientation="landscape")
            if url:
                images._download(url, photo)
                got = os.path.getsize(photo) > 1000
        except Exception as e:
            print("  cover photo fallback (%s)" % e)
    name_tf = _textfile(os.path.join(tmp, "cn.txt"), name)
    tag_tf = _textfile(os.path.join(tmp, "ct.txt"), "\n".join(textwrap.wrap(tagline, width=42)))
    draw = ("drawbox=x=0:y=0:w=%d:h=%d:color=black@0.45:t=fill," % (W, H) +
            "drawtext=textfile='%s':fontfile=%s:fontcolor=white:fontsize=92:"
            "x=(w-text_w)/2:y=h*0.30:shadowcolor=black@0.7:shadowx=3:shadowy=3," % (name_tf, FONT) +
            "drawtext=textfile='%s':fontfile=%s:fontcolor=white@0.92:fontsize=40:"
            "line_spacing=8:x=(w-text_w)/2:y=h*0.52:shadowcolor=black@0.7:shadowx=2:shadowy=2"
            % (tag_tf, FONT))
    if got:
        run([FF, "-y", "-v", "error", "-i", photo,
             "-vf", "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,%s"
             % (W, H, W, H, draw), "-frames:v", "1", out])
    else:
        run([FF, "-y", "-v", "error",
             "-f", "lavfi", "-i", "gradients=s=%dx%d:c0=%s:c1=%s:duration=1" % (W, H, c0, c1),
             "-frames:v", "1", "-vf", draw, out])
    return out


def main():
    secrets = util.load_secrets()
    want = sys.argv[1:]
    for ch in pipeline.load_channels():
        cid = ch["id"]
        if want and cid not in want:
            continue
        grad, theme = LOOK.get(cid, ("0x222222:0x555555", "abstract background"))
        c0, c1 = grad.split(":")
        odir = os.path.join(ROOT, "assets", "branding", cid)
        tmp = os.path.join(odir, "_tmp")
        os.makedirs(tmp, exist_ok=True)
        tagline = ch.get("bio", "").split(".")[0].strip()
        print("== %s ==" % ch["name"])
        avatar(cid, ch["name"], c0, c1, os.path.join(odir, "avatar.png"), tmp)
        cover(cid, ch["name"], tagline, c0, c1, theme, os.path.join(odir, "cover.png"), tmp, secrets)
        print("   -> %s/avatar.png + cover.png" % odir)


if __name__ == "__main__":
    main()
