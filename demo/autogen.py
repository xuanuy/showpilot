#!/usr/bin/env python3
"""Auto-generate the Devpost demo screen segments (demo/rec/NN.mp4) from real
artifacts: the actual build/post logs, real reels, and real Wan shots.
Run with the SYSTEM python (needs Pillow): /usr/bin/python3 autogen.py [NN ...]
Segment 05 (dashboard) is produced separately — see make_dash.sh notes.
"""
import os
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
PIPE = "/mnt/d/Workspaces/personal/ask/fb-anime-pipeline"
FFMPEG = "/home/xuanuy/.local/bin/ffmpeg"
REC = os.path.join(HERE, "rec")
TMP = os.path.join(HERE, ".frames")
FPS = 12

MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
SANS_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

BG = (13, 17, 23)
FG = (230, 237, 243)
GREEN = (63, 185, 80)
CYAN = (57, 197, 207)
YELLOW = (210, 168, 60)
DIM = (139, 148, 158)
ORANGE = (219, 109, 40)


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        sys.stderr.write(p.stderr)
        raise SystemExit("ffmpeg failed: %s" % " ".join(map(str, cmd[:6])))


def frames_to_mp4(pattern, out, fps=FPS):
    run([FFMPEG, "-y", "-v", "error", "-framerate", str(fps), "-i", pattern,
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", out])


def line_color(text):
    if text.startswith("$ "):
        return FG
    if "DONE" in text or "POSTED" in text or "+ first comment" in text or "+ shared" in text:
        return GREEN
    if text.strip().startswith("[wan] task") or "scene " in text:
        return YELLOW
    if text.startswith("[") or text.strip().startswith("[wan]"):
        return CYAN
    return FG


class Term:
    """Typewriter terminal renderer -> numbered PNG frames."""

    def __init__(self, title="uy@showpilot: ~/showpilot"):
        self.f_txt = ImageFont.truetype(MONO, 26)
        self.f_bold = ImageFont.truetype(MONO_B, 26)
        self.f_hdr = ImageFont.truetype(SANS, 22)
        self.title = title
        self.LH = 38
        self.top = 96
        self.left = 70
        self.max_rows = (1080 - self.top - 50) // self.LH

    def frame(self, lines, partial, cursor=True):
        img = Image.new("RGB", (1920, 1080), BG)
        d = ImageDraw.Draw(img)
        # window chrome
        d.rounded_rectangle([20, 14, 1900, 66], 12, fill=(32, 39, 48))
        for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
            d.ellipse([48 + i * 36, 30, 68 + i * 36, 50], fill=c)
        d.text((960, 40), self.title, font=self.f_hdr, fill=DIM, anchor="mm")
        # scroll
        show = (lines + [partial])[-self.max_rows:] if partial is not None else lines[-self.max_rows:]
        y = self.top
        for ln in show:
            font = self.f_bold if ln.startswith("$ ") else self.f_txt
            d.text((self.left, y), ln, font=font, fill=line_color(ln))
            y += self.LH
        if cursor and partial is not None:
            w = d.textlength(partial, font=self.f_bold)
            d.rectangle([self.left + w + 4, y - self.LH + 4,
                         self.left + w + 18, y - 8], fill=FG)
        return img

    def render(self, events, total, out_mp4):
        """events: (kind, text, weight) kind: cmd|out|pause. Durations are the
        weights scaled so the whole clip lasts `total` seconds."""
        wsum = sum(e[2] for e in events)
        os.makedirs(TMP, exist_ok=True)
        for f in os.listdir(TMP):
            os.remove(os.path.join(TMP, f))
        lines, n = [], 0

        def emit(img, dur):
            nonlocal n
            for _ in range(max(1, int(round(dur * FPS)))):
                img.save(os.path.join(TMP, "f%05d.png" % n))
                n += 1

        for kind, text, w in events:
            dur = total * w / wsum
            if kind == "cmd":
                steps = max(1, len(text) - 2)
                for i in range(2, len(text) + 1):
                    emit(self.frame(lines, text[:i]), dur / steps)
                lines.append(text)
            elif kind == "out":
                lines.append(text)
                emit(self.frame(lines, None, cursor=False), dur)
            else:  # pause
                emit(self.frame(lines, "" if text == "cursor" else None), dur)
        frames_to_mp4(os.path.join(TMP, "f%05d.png"), out_mp4)


def dt_escape(text):
    """Escape drawtext specials (colon/comma/quote) inside a filter string."""
    return text.replace("\\", "").replace("'", "").replace(":", r"\:").replace(",", r"\,")


def reel_on_stage(src, start, dur, out, label=None):
    """A 9:16 reel centered on its own blurred cover as a 1920x1080 stage."""
    lbl = ""
    if label:
        lbl = (",drawtext=fontfile=%s:text='%s':fontcolor=white:fontsize=42:"
               "box=1:boxcolor=black@0.45:boxborderw=18:x=(w-text_w)/2:y=60"
               % (SANS_B, dt_escape(label)))
    fc = ("[0:v]scale=1920:1080:force_original_aspect_ratio=increase,"
          "crop=1920:1080,gblur=sigma=32,eq=brightness=-0.12[bg];"
          "[0:v]scale=-2:1080[fg];[bg][fg]overlay=(W-w)/2:0,fps=30%s[v]" % lbl)
    run([FFMPEG, "-y", "-v", "error", "-ss", str(start), "-t", str(dur), "-i", src,
         "-filter_complex", fc, "-map", "[v]", "-an",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", out])


def concat(parts, out):
    lst = os.path.join(TMP, "cat.txt")
    os.makedirs(TMP, exist_ok=True)
    with open(lst, "w") as f:
        for p in parts:
            f.write("file '%s'\n" % p)
    run([FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", lst, "-c", "copy", out])


# ---------------------------------------------------------------- segments

def seg01():  # hook: montage of real reels (VO 14.8s)
    picks = [
        ("channels/donghua-realm/output/the-sword-that-refused.mp4", 2.5, "mode: wan — fully AI-generated"),
        ("channels/donghua-realm/output/top5-strongest-cultivators.mp4", 5, "daily commentary reel"),
        ("channels/life-stories/output/the-bread-father.mp4", 5, "mode: story"),
        ("channels/qi-and-swords/output/hanli-vs-xiaoyan.mp4", 5, "published to Facebook"),
    ]
    parts = []
    for i, (rel, ss, label) in enumerate(picks):
        p = os.path.join(TMP, "m%d.mp4" % i)
        reel_on_stage(os.path.join(PIPE, rel), ss, 4.1, p, label)
        parts.append(p)
    concat(parts, os.path.join(REC, "01.mp4"))


def seg02():  # what it is: architecture reveal (VO 18.8s)
    rows = [
        ("ShowPilot", SANS_B, 92, FG, 120),
        ("the autonomous AI showrunner", SANS, 40, DIM, 60),
        ("", None, 0, FG, 40),
        ("topic.md ──► Qwen: script ──► Qwen: storyboard ──► Wan: video shots", MONO, 34, CYAN, 62),
        ("        └───────────────────────► Piper TTS: voiceover", MONO, 34, CYAN, 62),
        ("                                        │", MONO, 34, DIM, 50),
        ("        ffmpeg: fit · concat · captions · mux ◄──┘", MONO, 34, CYAN, 62),
        ("                                        │", MONO, 34, DIM, 50),
        ("        Facebook: Reel + first-comment CTA + 24h Story", MONO, 34, GREEN, 62),
        ("                                        │", MONO, 34, DIM, 50),
        ("        dashboard: metrics  ·  cron: one episode per channel, daily", MONO, 34, YELLOW, 62),
        ("", None, 0, FG, 30),
        ("a fleet of channels — not one video on demand", SANS_B, 44, FG, 80),
    ]
    total, n = 20.3, 0
    os.makedirs(TMP, exist_ok=True)
    for f in os.listdir(TMP):
        os.remove(os.path.join(TMP, f))
    per = total / len(rows)
    for upto in range(1, len(rows) + 1):
        img = Image.new("RGB", (1920, 1080), (11, 15, 25))
        d = ImageDraw.Draw(img)
        y = 150
        for (text, fp, fs, col, adv) in rows[:upto]:
            if text:
                d.text((150, y), text, font=ImageFont.truetype(fp, fs), fill=col)
            y += adv
        hold = per * (4 if upto == len(rows) else 1)
        for _ in range(int(hold * FPS)):
            img.save(os.path.join(TMP, "f%05d.png" % n)); n += 1
    # scale: last row holds longer -> recompute nothing, total close enough
    frames_to_mp4(os.path.join(TMP, "f%05d.png"), os.path.join(REC, "02.mp4"))


def seg03():  # live build: real log, typewriter (VO 41.7s)
    ev = [("cmd", "$ python3 pipeline.py build donghua-realm the-sword-that-refused.md", 3.0),
          ("out", "[donghua-realm] [1/4] script ...", 2.2),
          ("out", "[wan] voiceover ...", 1.4),
          ("out", "        narration = 40.2s", 1.6),
          ("out", "[wan] storyboarding 6 scenes (qwen) ...", 2.6)]
    scenes = [("8.2", "b6fb589d-d67f-46", 8), ("5.4", "5981d2bb-9d5c-44", 5),
              ("9.3", "56803b37-01dc-45", 8), ("9.9", "bcbce597-8e60-4e", 8),
              ("5.9", "637640ca-b9ed-4a", 6), ("1.5", "4093c6df-5981-4d", 2)]
    for i, (sd, tid, req) in enumerate(scenes):
        ev.append(("out", "    scene %d (%ss): Vertical 9:16, cinematic 3D animation, xianxia ..." % (i + 1, sd), 1.1))
        ev.append(("out", "    [wan] task %s (%ds) ..." % (tid, req), 2.9))
    ev += [("out", "[wan] captions + mux ...", 2.4),
           ("out", "DONE -> channels/donghua-realm/output/the-sword-that-refused.mp4  (40.2s)", 1.0),
           ("pause", "cursor", 3.0)]
    Term().render(ev, 43.5, os.path.join(REC, "03.mp4"))


def seg04():  # publish + grow: real post log, then the reel (VO 18.7s)
    ev = [("cmd", "$ python3 pipeline.py post donghua-realm the-sword-that-refused.md", 2.6),
          ("out", "[donghua-realm] [FB] uploading reel ...", 2.6),
          ("out", "POSTED -> donghua-realm : video_id=1051937230512311", 1.6),
          ("out", "[donghua-realm]   + first comment posted", 1.4),
          ("out", "[donghua-realm]   + shared to story", 1.2),
          ("pause", "cursor", 1.6)]
    a = os.path.join(TMP, "04a.mp4")
    Term().render(ev, 8.5, a)
    b = os.path.join(TMP, "04b.mp4")
    reel_on_stage(os.path.join(PIPE, "channels/donghua-realm/output/the-sword-that-refused.mp4"),
                  6, 11.5, b, "live on the page — comment CTA + story auto-posted")
    concat([a, b], os.path.join(REC, "04.mp4"))


def seg06():  # architecture + deploy (VO 14.7s)
    ev = [("cmd", "$ ls lib/", 1.6),
          ("out", "qwen.py      Qwen Cloud chat + storyboard (stdlib only)", 0.9),
          ("out", "wan.py       Wan async t2v: create -> poll -> download", 0.9),
          ("out", "wanmode.py   storyboard -> shots -> fit/concat -> captions", 0.9),
          ("out", "script_gen.py  tts.py  assemble.py  storymode.py  fb_post.py", 1.0),
          ("cmd", "$ head deploy/alibaba/README.md", 1.8),
          ("out", "# Deploy to Alibaba Cloud ECS (hackathon target)", 0.9),
          ("out", "Region: Singapore (ap-southeast-1) - same region as Qwen Cloud", 0.9),
          ("out", "systemd: dashboard + tunnel   cron: daily all-channels drip", 0.9),
          ("cmd", "$ systemctl status showpilot-dashboard --no-pager | head -3", 1.9),
          ("out", "  showpilot-dashboard.service - ShowPilot ops dashboard", 0.8),
          ("out", "     Active: active (running)", 1.0),
          ("pause", "cursor", 2.4)]
    Term().render(ev, 15.8, os.path.join(REC, "06.mp4"))


def seg07():  # close: best Wan shot + title card (VO 8.5s)
    src = os.path.join(PIPE, "channels/donghua-realm/build/the-sword-that-refused/wan/fit03.mp4")
    fc = ("[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
          "eq=brightness=-0.25,fps=30,"
          "drawtext=fontfile=%s:text='ShowPilot':fontcolor=white:fontsize=150:"
          "x=(w-text_w)/2:y=340,"
          "drawtext=fontfile=%s:text='the showrunner that never misses a day':"
          "fontcolor=white@0.85:fontsize=48:x=(w-text_w)/2:y=540,"
          "drawtext=fontfile=%s:text='github.com/xuanuy/showpilot   ·   Built on Qwen Cloud':"
          "fontcolor=white@0.7:fontsize=40:x=(w-text_w)/2:y=920[v]"
          % (SANS_B, SANS, SANS))
    run([FFMPEG, "-y", "-v", "error", "-stream_loop", "-1", "-t", "9.5", "-i", src,
         "-filter_complex", fc, "-map", "[v]", "-an",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", os.path.join(REC, "07.mp4")])


ALL = {"01": seg01, "02": seg02, "03": seg03, "04": seg04, "06": seg06, "07": seg07}

if __name__ == "__main__":
    os.makedirs(REC, exist_ok=True)
    os.makedirs(TMP, exist_ok=True)
    want = sys.argv[1:] or sorted(ALL)
    for k in want:
        print("== segment", k)
        ALL[k]()
        print("   ->", os.path.join(REC, k + ".mp4"))
    shutil.rmtree(TMP, ignore_errors=True)
    print("done (05 = dashboard, made separately)")
