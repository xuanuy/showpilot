"""Text-to-speech (Piper) + caption (.srt) generation.

Piper has no word-level timestamps, so captions are timed by distributing the
measured audio duration across caption chunks proportional to their length.
This is accurate enough for short reels and needs no extra dependencies.
"""
import re

from .util import run, probe_duration


def synth(script_text, out_wav, cfg):
    """Synthesize narration to a WAV file. Returns its duration in seconds."""
    # Collapse to a single line; Piper splits on sentence punctuation internally.
    text = re.sub(r"\s+", " ", script_text).strip()
    proc = run([cfg["tools"]["piper"],
                "--model", cfg["tools"]["piper_voice"],
                "--output_file", out_wav],
               input=text)
    return probe_duration(cfg["tools"]["ffprobe"], out_wav)


def _chunks(text, max_words):
    """Split into caption-sized chunks, respecting sentence boundaries first."""
    sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text).strip())
    out = []
    for s in sentences:
        words = s.split()
        for i in range(0, len(words), max_words):
            piece = " ".join(words[i:i + max_words]).strip()
            if piece:
                out.append(piece)
    return out


def _ts(seconds):
    """ASS timestamp: H:MM:SS.cs (centiseconds)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs == 100:
        cs = 99
    return "%d:%02d:%02d.%02d" % (h, m, s, cs)


def build_ass(script_text, duration, out_ass, cfg, width, height):
    """Write an .ass subtitle file with explicit PlayRes so font size and MarginV
    are in real pixels. Timed proportionally to chunk character length."""
    c = cfg["captions"]
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: %d\nPlayResY: %d\n"
        "WrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,%s,%d,%s,&H000000FF,%s,&H64000000,1,0,0,0,100,100,0,0,1,"
        "%d,%d,2,60,60,%d,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        % (width, height, c["font_name"], c["font_size"], c["primary_color"],
           c["outline_color"], c["outline"], c["shadow"], c["margin_v"])
    )
    chunks = _chunks(script_text, c["max_words_per_caption"])
    total_chars = sum(len(x) for x in chunks) or 1
    t = 0.0
    events = []
    for chunk in chunks:
        dur = duration * (len(chunk) / total_chars)
        start, end = t, min(t + dur, duration)
        t = end
        events.append("Dialogue: 0,%s,%s,Default,,0,0,0,,%s"
                      % (_ts(start), _ts(end), chunk))
    with open(out_ass, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events) + "\n")
    return out_ass
