"""Compose the final vertical Reel with ffmpeg.

Layout: footage is centered on a blurred, zoomed copy of itself (so landscape
trailers fill a 1080x1920 frame cleanly), burned-in captions, and an audio mix
of ducked original audio + the loud voiceover.
"""
import os

from .util import run, probe_duration


def _has_audio(ffprobe, path):
    out = run([ffprobe, "-v", "error", "-select_streams", "a",
               "-show_entries", "stream=index", "-of", "csv=p=0", path]).stdout.strip()
    return bool(out)


def assemble(footage, voice_wav, subs, out_mp4, duration, cfg):
    r = cfg["reel"]
    c = cfg["captions"]
    W, H = r["width"], r["height"]
    dur = min(duration, r["max_seconds"])

    # ffmpeg filter path: escape backslashes and colons.
    subs_path = subs.replace("\\", "/").replace(":", r"\:")

    vfilter = (
        "[0:v]split=2[a][b];"
        "[a]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,"
        "boxblur=%d:1,setsar=1[bg];"
        "[b]scale=%d:-2,setsar=1[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2[ov];"
        "[ov]subtitles=filename='%s':fontsdir='%s'[v]"
        % (W, H, W, H, r["bg_blur"], W, subs_path, c["font_dir"])
    )

    have_orig = _has_audio(cfg["tools"]["ffprobe"], footage)
    if have_orig:
        afilter = (
            "[0:a]volume=%s[a0];[1:a]volume=%s[a1];"
            "[a0][a1]amix=inputs=2:duration=longest:normalize=0[aout]"
            % (r["orig_audio_volume"], r["voice_volume"])
        )
        filter_complex = vfilter + ";" + afilter
        amap = "[aout]"
    else:
        filter_complex = vfilter + ";[1:a]volume=%s[aout]" % r["voice_volume"]
        amap = "[aout]"

    cmd = [
        cfg["tools"]["ffmpeg"], "-y",
        "-stream_loop", "-1", "-i", footage,   # loop footage to cover narration
        "-i", voice_wav,
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", amap,
        "-t", "%.3f" % dur,
        "-r", str(r["fps"]),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        out_mp4,
    ]
    run(cmd)
    return probe_duration(cfg["tools"]["ffprobe"], out_mp4)
