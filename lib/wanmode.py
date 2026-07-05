"""Wan mode: fully generative reels. Qwen storyboards the narration, Wan
renders each shot, then the usual voiceover + captions + concat assembly.

Used when a topic's frontmatter has `mode: wan` (no footage file needed).
Wan clips are cached in build/<name>/wan/ so re-runs never re-spend credits.
"""
import os

from . import qwen, storymode, tts, wan
from .util import run, probe_duration


def _fit(clip, out_mp4, dur, cfg):
    """Loop/trim a Wan clip to the exact scene duration at reel size, no audio."""
    r = cfg["reel"]
    vf = ("scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,fps=%d"
          % (r["width"], r["height"], r["width"], r["height"], r["fps"]))
    run([cfg["tools"]["ffmpeg"], "-y", "-v", "error",
         "-stream_loop", "-1", "-i", clip, "-t", "%.3f" % dur,
         "-vf", vf, "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", out_mp4])
    return out_mp4


def build_wan(script_text, meta, paths, bdir, cfg, secrets):
    """script -> voiceover -> Qwen storyboard -> Wan shots -> concat -> subs+audio."""
    ff = cfg["tools"]["ffmpeg"]

    print("[wan] voiceover ...")
    dur = tts.synth(script_text, paths["voice"], cfg)
    print("        narration = %.1fs" % dur)

    max_scenes = int(meta.get("max_scenes", cfg["wan"].get("max_scenes", 6)))
    scenes = storymode.split_scenes(script_text, max_scenes)
    print("[wan] storyboarding %d scenes (qwen) ..." % len(scenes))
    prompts = qwen.storyboard(scenes, meta, cfg)

    wan_dir = os.path.join(bdir, "wan")
    os.makedirs(wan_dir, exist_ok=True)
    total_chars = sum(len(s) for s in scenes) or 1
    clips, t_acc = [], 0.0
    for i, (sc, pr) in enumerate(zip(scenes, prompts)):
        if i == len(scenes) - 1:
            sdur = max(0.5, dur - t_acc)
        else:
            sdur = max(0.5, dur * (len(sc) / total_chars))
            t_acc += sdur
        raw = os.path.join(wan_dir, "raw%02d.mp4" % i)
        if not (os.path.exists(raw) and os.path.getsize(raw) > 10000):
            print("    scene %d (%.1fs): %s" % (i + 1, sdur, pr[:70]))
            wan.generate(pr, min(sdur, cfg["wan"].get("max_scene_seconds", 8)), raw, cfg)
        else:
            print("    scene %d (%.1fs): cached" % (i + 1, sdur))
        clip = os.path.join(wan_dir, "fit%02d.mp4" % i)
        _fit(raw, clip, sdur, cfg)
        clips.append(clip)

    listf = os.path.join(bdir, "concat.txt")
    with open(listf, "w", encoding="utf-8") as f:
        for c in clips:
            f.write("file '%s'\n" % c.replace("'", "'\\''"))
    joined = os.path.join(bdir, "joined.mp4")
    run([ff, "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", listf, "-c", "copy", joined])

    print("[wan] captions + mux ...")
    tts.build_ass(script_text, dur, paths["subs"], cfg,
                  cfg["reel"]["width"], cfg["reel"]["height"])
    subs_path = paths["subs"].replace("\\", "/").replace(":", r"\:")
    run([ff, "-y", "-v", "error", "-i", joined, "-i", paths["voice"],
         "-vf", "subtitles=filename='%s':fontsdir='%s'" % (subs_path, cfg["captions"]["font_dir"]),
         "-map", "0:v", "-map", "1:a", "-t", "%.3f" % dur,
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", paths["mp4"]])
    return probe_duration(cfg["tools"]["ffprobe"], paths["mp4"])
