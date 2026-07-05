#!/usr/bin/env python3
"""fb-anime-pipeline (multi-page): per-channel topic -> script -> voiceover ->
captioned Reel -> Facebook.

Each Facebook Page is a "channel" with its own folder under channels/<id>/
(topics, footage, build, output) and its own credentials in secrets.env.

Usage:
  python pipeline.py init                         Create folders for every channel
  python pipeline.py channels                     List channels (name, handle, bio)
  python pipeline.py list [<channel>]             Topic status (all channels, or one)
  python pipeline.py build <channel> <topic.md>   Build the .mp4 only
  python pipeline.py post  <channel> <topic.md>   Build if needed, then publish
  python pipeline.py all   <channel>              Build + post every un-posted topic
  python pipeline.py all-channels                 Run `all` for every channel

<topic.md> may be a bare filename (resolved in the channel's topics/) or a path.
Footage referenced in a topic must live in that channel's footage/ folder and be
content you have the right to use (official trailers/PV, your own recordings).
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import util, script_gen, tts, assemble, fb_post, storymode, wanmode
from lib.fb_post import FBError

CFG = util.load_config()
ROOT = util.ROOT


def load_channels():
    with open(os.path.join(ROOT, "channels.json"), encoding="utf-8") as f:
        return json.load(f)["channels"]


def get_channel(cid):
    for ch in load_channels():
        if ch["id"] == cid:
            return ch
    raise SystemExit("Unknown channel '%s'. See `pipeline.py channels`." % cid)


def channel_dir(cid):
    return os.path.join(ROOT, "channels", cid)


def channel_secrets(cid):
    """Per-channel creds from secrets.env, keyed <UPPER_ID>_PAGE_ID / _TOKEN."""
    s = util.load_secrets()
    key = cid.upper().replace("-", "_")
    return {
        "FB_PAGE_ID": s.get(key + "_PAGE_ID", ""),
        "FB_PAGE_ACCESS_TOKEN": s.get(key + "_TOKEN", ""),
    }


def resolve_topic(cid, topic):
    if os.path.sep in topic or os.path.exists(topic):
        return topic
    return os.path.join(channel_dir(cid), "topics", topic)


def _paths(cid, topic_path):
    cdir = channel_dir(cid)
    name = util.slug(os.path.splitext(os.path.basename(topic_path))[0])
    bdir = os.path.join(cdir, "build", name)
    odir = os.path.join(cdir, "output")
    os.makedirs(bdir, exist_ok=True)
    os.makedirs(odir, exist_ok=True)
    return {
        "name": name,
        "bdir": bdir,
        "footage_dir": os.path.join(cdir, "footage"),
        "voice": os.path.join(bdir, "voice.wav"),
        "subs": os.path.join(bdir, "captions.ass"),
        "mp4": os.path.join(odir, "%s.mp4" % name),
        "caption": os.path.join(odir, "%s.caption.txt" % name),
        "posted": os.path.join(odir, "%s.posted.json" % name),
    }


def _caption_text(meta, script):
    """Engagement-optimized caption: hook title + the closing CTA question
    (drives comments, which the Reels algorithm rewards) + hashtags."""
    title = meta.get("title", "").strip()
    tags = meta.get("hashtags", "").strip()
    questions = re.findall(r"[^.!?]*\?", script)
    cta = questions[-1].strip() if questions else ""
    parts = [p for p in [title, cta, tags] if p]
    return "\n\n".join(parts) if parts else script[:200]


def build(cid, topic):
    topic_path = resolve_topic(cid, topic)
    meta, raw_script = util.parse_topic(topic_path)
    p = _paths(cid, topic_path)

    print("[%s] [1/4] script ..." % cid)
    script = script_gen.generate(meta, raw_script, CFG)

    mode = meta.get("mode", "").strip().lower()
    if mode == "wan":
        # Wan mode: Qwen storyboard + Wan generated shots, fully generative.
        final = wanmode.build_wan(script, meta, p, p["bdir"], CFG, channel_secrets(cid))
    elif mode == "story":
        # Story mode: stock images + Ken Burns, no footage file needed.
        secrets = dict(channel_secrets(cid))
        secrets["PEXELS_API_KEY"] = util.load_secrets().get("PEXELS_API_KEY", "")
        final = storymode.build_story(script, meta, p, p["bdir"], CFG, secrets)
    else:
        footage_name = meta.get("footage", "").strip()
        if not footage_name:
            raise SystemExit("Topic missing `footage:` (or set `mode: story`).")
        footage = os.path.join(p["footage_dir"], footage_name)
        if not os.path.exists(footage):
            raise SystemExit("Footage not found: %s (drop a legal clip there)" % footage)
        print("[%s] [2/4] voiceover (piper) ..." % cid)
        dur = tts.synth(script, p["voice"], CFG)
        print("        narration = %.1fs" % dur)
        print("[%s] [3/4] captions ..." % cid)
        tts.build_ass(script, dur, p["subs"], CFG, CFG["reel"]["width"], CFG["reel"]["height"])
        print("[%s] [4/4] assemble (ffmpeg) ..." % cid)
        final = assemble.assemble(footage, p["voice"], p["subs"], p["mp4"], dur, CFG)

    with open(p["caption"], "w", encoding="utf-8") as f:
        f.write(_caption_text(meta, script))
    print("DONE -> %s  (%.1fs)" % (p["mp4"], final))
    return p, meta, script


def post(cid, topic):
    topic_path = resolve_topic(cid, topic)
    p = _paths(cid, topic_path)
    if not os.path.exists(p["mp4"]):
        build(cid, topic_path)
    with open(p["caption"], encoding="utf-8") as f:
        caption = f.read().strip()

    secrets = channel_secrets(cid)
    for k in ("FB_PAGE_ID", "FB_PAGE_ACCESS_TOKEN"):
        if not secrets.get(k):
            raise SystemExit(
                "Missing creds for '%s' in secrets.env (need %s_PAGE_ID / %s_TOKEN)."
                % (cid, cid.upper().replace("-", "_"), cid.upper().replace("-", "_")))

    print("[%s] [FB] uploading reel ..." % cid)
    res = fb_post.publish_reel(p["mp4"], caption, CFG, secrets)
    with open(p["posted"], "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)
    print("POSTED -> %s : video_id=%s" % (cid, res["video_id"]))

    # Organic boosts (best-effort: never let these fail a successful post).
    boost = CFG.get("boost", {})
    if boost.get("first_comment"):
        _, script = util.parse_topic(topic_path)
        qs = re.findall(r"[^.!?]*\?", script)
        if qs:
            try:
                fb_post.post_comment(res["video_id"], qs[-1].strip(), CFG, secrets)
                print("[%s]   + first comment posted" % cid)
            except Exception as e:
                print("[%s]   ! comment skipped: %s" % (cid, e))
    if boost.get("share_to_story"):
        try:
            fb_post.publish_story(p["mp4"], CFG, secrets)
            print("[%s]   + shared to story" % cid)
        except Exception as e:
            print("[%s]   ! story skipped: %s" % (cid, e))


def _topic_files(cid):
    tdir = os.path.join(channel_dir(cid), "topics")
    if not os.path.isdir(tdir):
        return []
    return [os.path.join(tdir, f) for f in sorted(os.listdir(tdir)) if f.endswith(".md")]


def all_in_channel(cid, limit=None):
    """Post un-posted topics. limit=N stops after N successful posts (drip).
    Per-topic errors (missing footage/creds, FB errors) are logged and skipped
    so one bad topic never aborts an unattended run."""
    get_channel(cid)
    files = _topic_files(cid)
    if not files:
        print("[%s] no topics" % cid)
        return 0
    done = 0
    for tp in files:
        if limit is not None and done >= limit:
            break
        p = _paths(cid, tp)
        if os.path.exists(p["posted"]):
            print("[%s] skip (posted): %s" % (cid, os.path.basename(tp)))
            continue
        print("=== [%s] %s ===" % (cid, os.path.basename(tp)))
        try:
            post(cid, tp)
            done += 1
        except (SystemExit, Exception) as e:
            print("[%s] SKIP %s: %s" % (cid, os.path.basename(tp), e))
    return done


def all_channels(per_channel=1):
    """Drip: post up to `per_channel` un-posted topics for every channel."""
    for ch in load_channels():
        try:
            all_in_channel(ch["id"], limit=per_channel)
        except Exception as e:
            print("[%s] channel error: %s" % (ch["id"], e))


def init():
    for ch in load_channels():
        for sub in ("topics", "footage", "build", "output"):
            os.makedirs(os.path.join(channel_dir(ch["id"]), sub), exist_ok=True)
        readme = os.path.join(channel_dir(ch["id"]), "footage", "README.txt")
        if not os.path.exists(readme):
            with open(readme, "w", encoding="utf-8") as f:
                f.write("Drop legal clips for %s here (official trailers/PV or your "
                        "own recordings). Reference them via `footage:` in a topic.\n"
                        % ch["name"])
        print("ready: channels/%s/" % ch["id"])


def list_channels():
    for ch in load_channels():
        print("%-22s %-24s %s" % (ch["id"], ch["handle"], ch["category"]))
        print("    %s" % ch["bio"])


def list_status(cid=None):
    chans = [get_channel(cid)] if cid else load_channels()
    for ch in chans:
        files = _topic_files(ch["id"])
        print("== %s (%s) ==" % (ch["name"], ch["id"]))
        if not files:
            print("   (no topics)")
        for tp in files:
            p = _paths(ch["id"], tp)
            state = "posted" if os.path.exists(p["posted"]) else (
                "built" if os.path.exists(p["mp4"]) else "new")
            print("   %-38s %s" % (os.path.basename(tp), state))


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    cmd = a[0]
    if cmd == "init":
        init()
    elif cmd == "channels":
        list_channels()
    elif cmd == "list":
        list_status(a[1] if len(a) > 1 else None)
    elif cmd == "build" and len(a) >= 3:
        build(a[1], a[2])
    elif cmd == "post" and len(a) >= 3:
        post(a[1], a[2])
    elif cmd == "all" and len(a) >= 2:
        all_in_channel(a[1])
    elif cmd == "all-channels":
        all_channels()
    else:
        print(__doc__)


if __name__ == "__main__":
    try:
        main()
    except FBError as e:
        sys.exit("Facebook API error -> %s" % e)
