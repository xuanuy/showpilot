"""Story mode: turn a narration script + per-scene stock images into a vertical
reel using the Ken Burns effect (slow zoom/pan over still images).

Used when a topic's frontmatter has `mode: story` (instead of `footage:`).
"""
import os
import re

from . import images, tts
from .util import run, probe_duration


def split_scenes(script_text, max_scenes=8):
    """One scene per sentence, merged so we don't exceed max_scenes."""
    text = re.sub(r"\s+", " ", script_text).strip()
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if len(sents) <= max_scenes:
        return sents
    # merge adjacent sentences evenly down to max_scenes
    per = (len(sents) + max_scenes - 1) // max_scenes
    return [" ".join(sents[i:i + per]) for i in range(0, len(sents), per)]


def ken_burns(image, out_mp4, dur, idx, cfg):
    """Render one still image as a moving clip. Alternates zoom-in / pan / zoom-out."""
    r = cfg["reel"]
    W, H, fps = r["width"], r["height"], r["fps"]
    frames = max(1, int(round(dur * fps)))
    mode = idx % 3
    if mode == 0:      # slow zoom IN
        z = "min(zoom+0.0010,1.4)"
        x = "iw/2-(iw/zoom/2)"; y = "ih/2-(ih/zoom/2)"
    elif mode == 1:    # pan across at a held zoom
        z = "1.25"
        x = "iw/2-(iw/zoom/2)+(on/%d)*260" % frames; y = "ih/2-(ih/zoom/2)"
    else:              # slow zoom OUT
        z = "if(eq(on,1),1.4,max(zoom-0.0010,1.0))"
        x = "iw/2-(iw/zoom/2)"; y = "ih/2-(ih/zoom/2)"
    vf = ("scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,"
          "scale=4000:-1,zoompan=z='%s':x='%s':y='%s':d=%d:s=%dx%d:fps=%d"
          % (W, H, W, H, z, x, y, frames, W, H, fps))
    run([cfg["tools"]["ffmpeg"], "-y", "-v", "error",
         "-loop", "1", "-i", image, "-t", "%.3f" % dur,
         "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", out_mp4])
    return out_mp4


def build_story(script_text, meta, paths, bdir, cfg, secrets):
    """script -> voiceover -> per-scene images -> ken burns -> concat -> subs+audio.
    Returns the final mp4 path (paths['mp4'])."""
    theme = meta.get("image_theme", "").strip()
    ff = cfg["tools"]["ffmpeg"]

    print("[story] voiceover (piper) ...")
    dur = tts.synth(script_text, paths["voice"], cfg)
    print("        narration = %.1fs" % dur)

    scenes = split_scenes(script_text, int(meta.get("max_scenes", 8)))
    total_chars = sum(len(s) for s in scenes) or 1
    print("[story] %d scenes; fetching images + ken burns ..." % len(scenes))

    img_dir = os.path.join(bdir, "img")
    os.makedirs(img_dir, exist_ok=True)
    clips, t_acc = [], 0.0
    for i, sc in enumerate(scenes):
        # last scene absorbs rounding so total matches narration exactly
        if i == len(scenes) - 1:
            sdur = max(0.5, dur - t_acc)
        else:
            sdur = max(0.5, dur * (len(sc) / total_chars))
            t_acc += sdur
        img = os.path.join(img_dir, "s%02d.jpg" % i)
        _, q = images.fetch_scene_image(sc, theme, i, img, cfg, secrets)
        print("    scene %d (%.1fs) <- %s" % (i + 1, sdur, q))
        clip = os.path.join(img_dir, "c%02d.mp4" % i)
        ken_burns(img, clip, sdur, i, cfg)
        clips.append(clip)

    # concat clips
    listf = os.path.join(bdir, "concat.txt")
    with open(listf, "w", encoding="utf-8") as f:
        for c in clips:
            f.write("file '%s'\n" % c.replace("'", "'\\''"))
    joined = os.path.join(bdir, "joined.mp4")
    run([ff, "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", listf, "-c", "copy", joined])

    print("[story] captions + mux ...")
    tts.build_ass(script_text, dur, paths["subs"], cfg, cfg["reel"]["width"], cfg["reel"]["height"])
    subs_path = paths["subs"].replace("\\", "/").replace(":", r"\:")
    run([ff, "-y", "-v", "error", "-i", joined, "-i", paths["voice"],
         "-vf", "subtitles=filename='%s':fontsdir='%s'" % (subs_path, cfg["captions"]["font_dir"]),
         "-map", "0:v", "-map", "1:a", "-t", "%.3f" % dur,
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", paths["mp4"]])
    return probe_duration(cfg["tools"]["ffprobe"], paths["mp4"])
