#!/usr/bin/env python3
"""Local management dashboard for all channels/Pages.

Run:   python3 dashboard.py        then open http://127.0.0.1:8765

Pure standard library (no installs). Shows, per channel: token health, follower
count, and every topic's state (new / built / posted) with footage presence and —
for posted reels — a permalink plus live views/likes/comments. Build and Post
buttons run the pipeline right from the page.

Actions run synchronously: a Build+Post can take 20-40s, the page just waits then
refreshes. This binds to localhost only.
"""
import base64
import html
import http.server
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

import pipeline
from lib import util

CFG = pipeline.CFG
VER = CFG["facebook"]["graph_version"]
PORT = 8765
_cache = {}  # key -> (ts, value)
_jobs = {}   # "cid/topic" -> human status while a footage download runs
YTDLP = os.path.expanduser("~/.local/bin/yt-dlp")
OFFICIAL_MARKERS = ("wetv", "tencent", "腾讯", "made by bilibili", "哔哩哔哩",
                    "bilibili", "yuewen", "阅文")

_SEC = util.load_secrets()
AUTH_USER = _SEC.get("DASHBOARD_USER", "admin")
AUTH_PASS = _SEC.get("DASHBOARD_PASS", "")  # empty -> no auth (localhost only)


def _cached(key, ttl, fn):
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    val = fn()
    _cache[key] = (now, val)
    return val


def fb_get(path, params):
    url = "https://graph.facebook.com/%s/%s?%s" % (VER, path, urllib.parse.urlencode(params))
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def page_meta(cid):
    sec = pipeline.channel_secrets(cid)
    tok = sec.get("FB_PAGE_ACCESS_TOKEN")
    if not tok:
        return {"ok": False, "reason": "no token"}
    def _fetch():
        d = fb_get("me", {"fields": "name,followers_count,fan_count", "access_token": tok})
        if not d or "error" in (d or {}) or d is None:
            return {"ok": False, "reason": "token invalid"}
        if d is None:
            return {"ok": False, "reason": "no data"}
        return {"ok": True, "name": d.get("name", ""),
                "followers": d.get("followers_count") or d.get("fan_count") or 0}
    return _cached("meta:" + cid, 300, _fetch)


def reel_stats(cid, video_id):
    sec = pipeline.channel_secrets(cid)
    tok = sec.get("FB_PAGE_ACCESS_TOKEN")
    def _fetch():
        d = fb_get(video_id, {
            "fields": "permalink_url,likes.summary(true).limit(0),comments.summary(true).limit(0)",
            "access_token": tok})
        out = {"link": "", "likes": "-", "comments": "-", "views": "-"}
        if d and "error" not in d:
            out["link"] = d.get("permalink_url", "")
            out["likes"] = d.get("likes", {}).get("summary", {}).get("total_count", "-")
            out["comments"] = d.get("comments", {}).get("summary", {}).get("total_count", "-")
        ins = fb_get("%s/video_insights" % video_id,
                     {"metric": "post_video_views", "access_token": tok})
        try:
            out["views"] = ins["data"][0]["values"][0]["value"]
        except Exception:
            pass
        return out
    return _cached("stats:" + video_id, 180, _fetch)


def topic_state(cid, tp):
    p = pipeline._paths(cid, tp)
    meta, _ = util.parse_topic(tp)
    is_story = meta.get("mode", "").strip().lower() == "story"
    footage = meta.get("footage", "").strip()
    # story-mode topics need no footage file — they fetch images at build time
    has_footage = is_story or (bool(footage) and os.path.exists(os.path.join(p["footage_dir"], footage)))
    posted = os.path.exists(p["posted"])
    state = "posted" if posted else ("built" if os.path.exists(p["mp4"]) else "new")
    vid = ""
    if posted:
        try:
            with open(p["posted"], encoding="utf-8") as f:
                vid = json.load(f).get("video_id", "")
        except Exception:
            pass
    return {"file": os.path.basename(tp), "title": meta.get("title", ""),
            "state": state, "has_footage": has_footage, "video_id": vid,
            "is_story": is_story,
            "source": meta.get("source", "").strip(),
            "source_channel": meta.get("source_channel", "").strip()}


def set_meta(cid, topic_file, key, value):
    """Write/replace a `key:` field in a topic's frontmatter."""
    path = os.path.join(pipeline.channel_dir(cid), "topics", topic_file)
    txt = open(path, encoding="utf-8").read()
    line = "%s: %s" % (key, value)
    pat = r"(?m)^%s:.*$" % re.escape(key)
    if re.search(pat, txt):
        txt = re.sub(pat, lambda m: line, txt, count=1)
    else:
        txt = re.sub(r"(?m)^(footage:.*)$", lambda m: m.group(1) + "\n" + line, txt, count=1)
    open(path, "w", encoding="utf-8").write(txt)


def fetch_footage(cid, topic_file, url):
    """Verify the source channel, download it to the topic's footage file, and
    record source + source_channel. Returns {ok, channel, msg}."""
    tpath = os.path.join(pipeline.channel_dir(cid), "topics", topic_file)
    meta, _ = util.parse_topic(tpath)
    fname = meta.get("footage", "").strip()
    if not fname:
        return {"ok": False, "msg": "topic has no footage: filename", "channel": ""}
    # 1. probe the uploading channel (don't download yet)
    chan = ""
    try:
        p = subprocess.run([YTDLP, "--no-warnings", "--skip-download",
                            "--print", "%(channel)s", url],
                           capture_output=True, text=True, timeout=60)
        chan = (p.stdout.strip().splitlines() or [""])[0]
    except Exception:
        pass
    official = any(m in chan.lower() for m in OFFICIAL_MARKERS)
    label = "%s (%s)" % (chan or "unknown", "official" if official else "UNVERIFIED")
    # 2. record source + channel into the topic frontmatter
    set_meta(cid, topic_file, "source", url)
    set_meta(cid, topic_file, "source_channel", label)
    # 3. download to footage/<fname>
    fdir = os.path.join(pipeline.channel_dir(cid), "footage")
    os.makedirs(fdir, exist_ok=True)
    out = os.path.join(fdir, fname)
    ffdir = os.path.dirname(CFG["tools"]["ffmpeg"])
    try:
        subprocess.run([YTDLP, "--no-warnings", "--force-overwrites",
                        "--ffmpeg-location", ffdir,
                        "-f", "bv*[ext=mp4][height<=1080]+ba[ext=m4a]/b[ext=mp4]/b",
                        "--merge-output-format", "mp4", "-o", out, url],
                       capture_output=True, text=True, timeout=300)
    except Exception as e:
        return {"ok": False, "msg": "download error: %s" % e, "channel": label}
    if not os.path.exists(out):
        return {"ok": False, "msg": "download produced no file", "channel": label}
    return {"ok": True, "channel": label, "official": official}


def fetch_footage_job(cid, topic_file, url):
    key = cid + "/" + topic_file
    try:
        res = fetch_footage(cid, topic_file, url)
        _jobs[key] = ("done: " + res["channel"]) if res["ok"] else ("failed: " + res["msg"])
    except Exception as e:
        _jobs[key] = "failed: %s" % e
    _cache.clear()


# ---------- HTML ----------
CSS = """
*{box-sizing:border-box} body{margin:0;font:15px/1.5 system-ui,Segoe UI,Arial;background:#0f1115;color:#e6e8eb}
header{padding:14px 20px;background:#161a22;border-bottom:1px solid #232936;position:sticky;top:0;z-index:5}
header h1{margin:0;font-size:17px} header .sub{color:#8b94a7;font-size:12px;margin-top:2px}
.layout{display:flex;align-items:flex-start;gap:0}
.side{width:240px;flex:0 0 240px;border-right:1px solid #232936;min-height:calc(100vh - 56px);padding:10px 0;background:#12161e}
.side a{display:flex;align-items:center;gap:9px;padding:11px 18px;color:#cdd3df;text-decoration:none;font-size:14px;border-left:3px solid transparent}
.side a:hover{background:#1a1f2a;text-decoration:none}
.side a.active{background:#1c2330;border-left-color:#2d6cdf;color:#fff;font-weight:600}
.side .cnt{margin-left:auto;color:#6b7585;font-size:12px}
.dot{width:8px;height:8px;border-radius:50%;flex:0 0 8px} .dot.g{background:#5fd38d} .dot.r{background:#f08a9b}
.main{flex:1;padding:20px;min-width:0;max-width:1100px}
@media(max-width:720px){
  .layout{flex-direction:column}
  .side{width:100%;flex:none;min-height:0;border-right:0;border-bottom:1px solid #232936;display:flex;overflow-x:auto;padding:6px}
  .side a{border-left:0;border-bottom:3px solid transparent;white-space:nowrap;padding:9px 12px}
  .side a.active{border-left:0;border-bottom-color:#2d6cdf}
  .side .cnt{display:none} .main{padding:14px}
}
.card{background:#161a22;border:1px solid #232936;border-radius:12px;margin:0 0 18px;overflow:hidden}
.chead{display:flex;align-items:center;gap:12px;padding:14px 18px;border-bottom:1px solid #232936;flex-wrap:wrap}
.chead h2{margin:0;font-size:16px} .handle{color:#8b94a7;font-size:13px}
.pill{font-size:12px;padding:3px 9px;border-radius:20px;font-weight:600}
.ok{background:#10331f;color:#5fd38d} .bad{background:#3a1d22;color:#f08a9b}
.foll{margin-left:auto;color:#cdd3df;font-size:13px}
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch;width:100%}
table{width:100%;min-width:680px;border-collapse:collapse} td,th{padding:10px 12px;text-align:left;border-top:1px solid #20262f;font-size:13px;vertical-align:top}
th{color:#8b94a7;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.s-posted{color:#5fd38d} .s-built{color:#e7c24b} .s-new{color:#8b94a7}
.muted{color:#6b7585} a{color:#6ea8fe;text-decoration:none} a:hover{text-decoration:underline}
button{font:inherit;border:0;border-radius:8px;padding:6px 12px;cursor:pointer;color:#fff}
.b-post{background:#2d6cdf} .b-build{background:#3a4255} .b-drip{background:#1f7a4d}
form{display:inline} .stat{font-variant-numeric:tabular-nums}
.srcin{width:130px;padding:5px;border-radius:6px;border:1px solid #2a3140;background:#0f1115;color:#e6e8eb;font:inherit}
.note{color:#6b7585;font-size:12px;padding:10px 18px}
"""


def esc(x):
    return html.escape(str(x))


def _sidebar(selected):
    items = []
    for ch in pipeline.load_channels():
        cid = ch["id"]
        meta = page_meta(cid)
        dot = "g" if meta.get("ok") else "r"
        n = len(pipeline._topic_files(cid))
        cls = " class=active" if cid == selected else ""
        items.append(
            "<a href='/?c=%s'%s><span class='dot %s'></span>%s<span class=cnt>%d</span></a>"
            % (esc(cid), cls, dot, esc(ch["name"]), n))
    return "<nav class=side>" + "".join(items) + "</nav>"


def render(selected=None):
    chans = pipeline.load_channels()
    ids = [c["id"] for c in chans]
    if selected not in ids:
        selected = ids[0] if ids else None
    out = ["<!doctype html><meta charset=utf-8><title>Pipeline Dashboard</title>",
           "<meta name=viewport content='width=device-width,initial-scale=1'>",
           ("<meta http-equiv=refresh content=6>"
            if any(s.startswith("downloading") for s in _jobs.values()) else ""),
           "<style>%s</style>" % CSS,
           "<header><h1>Pipeline — Dashboard</h1>",
           "<div class=sub>%s · build/post run on this machine</div></header>"
           % esc(time.strftime("%Y-%m-%d %H:%M:%S")),
           "<div class=layout>", _sidebar(selected), "<div class=main>"]
    ch = next((c for c in chans if c["id"] == selected), None)
    if ch:
        out.append(render_channel(ch))
    out.append("</div></div>")
    return "".join(out)


def render_channel(ch):
    out = []
    cid = ch["id"]
    meta = page_meta(cid)
    if meta.get("ok"):
        badge = "<span class='pill ok'>token ok</span>"
        foll = "<span class=foll>%s followers</span>" % esc(meta.get("followers", 0))
    else:
        badge = "<span class='pill bad'>%s</span>" % esc(meta.get("reason", "no token"))
        foll = "<span class=foll>—</span>"
    out.append("<div class=card><div class=chead>")
    out.append("<h2>%s</h2><span class=handle>%s</span>%s%s</div>"
               % (esc(ch["name"]), esc(ch.get("handle", "")), badge, foll))

    if True:
        topics = pipeline._topic_files(cid)
        if topics:
            out.append("<div class=tw><table><tr><th>Topic</th><th>State</th><th>Footage</th>"
                       "<th>Source</th><th>Reel</th><th>Views</th><th>♥</th><th>💬</th><th>Action</th></tr>")
            for tp in topics:
                t = topic_state(cid, tp)
                if t["is_story"]:
                    foot = "🖼 story"
                elif t["has_footage"]:
                    foot = "✓"
                else:
                    foot = "<span class=muted>missing</span>"
                link = views = likes = comments = "<span class=muted>—</span>"
                if t["state"] == "posted" and t["video_id"]:
                    st = reel_stats(cid, t["video_id"])
                    if st["link"]:
                        link = "<a href='https://facebook.com%s' target=_blank>open</a>" % esc(st["link"])
                    views = "<span class=stat>%s</span>" % esc(st["views"])
                    likes = "<span class=stat>%s</span>" % esc(st["likes"])
                    comments = "<span class=stat>%s</span>" % esc(st["comments"])
                job = _jobs.get(cid + "/" + t["file"], "")
                act = ""
                if t["state"] != "posted":
                    if t["has_footage"]:
                        act += ("<form method=post action=/do>"
                                "<input type=hidden name=action value=post>"
                                "<input type=hidden name=channel value='%s'>"
                                "<input type=hidden name=topic value='%s'>"
                                "<button class=b-post>Post</button></form> " % (esc(cid), esc(t["file"])))
                        act += ("<form method=post action=/do>"
                                "<input type=hidden name=action value=build>"
                                "<input type=hidden name=channel value='%s'>"
                                "<input type=hidden name=topic value='%s'>"
                                "<button class=b-build>Build</button></form>" % (esc(cid), esc(t["file"])))
                    elif job.startswith("downloading"):
                        act = "<span class=muted>⏳ downloading…</span>"
                    elif t["source"].startswith("http"):
                        act = ("<form method=post action=/do>"
                               "<input type=hidden name=action value=fetch>"
                               "<input type=hidden name=channel value='%s'>"
                               "<input type=hidden name=topic value='%s'>"
                               "<button class=b-post>⬇ Download footage</button></form>"
                               % (esc(cid), esc(t["file"])))
                    else:
                        act = "<span class=muted>add source first</span>"
                form = ("<form method=post action=/do>"
                        "<input type=hidden name=action value=set_source>"
                        "<input type=hidden name=channel value='%s'>"
                        "<input type=hidden name=topic value='%s'>"
                        "<input class=srcin name=source placeholder='paste official URL'>"
                        "<button class=b-build>+</button></form>" % (esc(cid), esc(t["file"])))
                if t["is_story"]:
                    src = "<span class=muted>auto (stock)</span>"
                elif job.startswith("downloading"):
                    src = "<span class=muted>⏳ checking + downloading…</span>"
                elif t["source"].startswith("http"):
                    src = "<a href='%s' target=_blank title='%s'>src</a>" % (
                        esc(t["source"]), esc(t["source_channel"] or "source"))
                    if "UNVERIFIED" in t["source_channel"]:
                        src += " <span class=bad style='padding:1px 6px'>unverified</span>"
                elif job.startswith("failed"):
                    src = "<div class=muted>✗ %s</div>%s" % (esc(job[8:]), form)
                else:
                    src = form
                out.append("<tr><td>%s<div class=muted>%s</div></td>"
                           "<td class=s-%s>%s</td><td>%s</td><td>%s</td><td>%s</td>"
                           "<td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                           % (esc(t["title"] or t["file"]), esc(t["file"]),
                              t["state"], t["state"], foot, src, link, views, likes, comments, act))
            out.append("</table></div>")
        else:
            out.append("<div class=note>No topics yet — add .md files to channels/%s/topics/</div>" % esc(cid))

        out.append("<div class=note>"
                   "<form method=post action=/do>"
                   "<input type=hidden name=action value=drip>"
                   "<input type=hidden name=channel value='%s'>"
                   "<button class=b-drip>Post next (drip 1)</button></form> "
                   "&nbsp; build/post may take ~30s.</div>" % esc(cid))
    out.append("</div>")
    return "".join(out)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _authed(self):
        if not AUTH_PASS:
            return True
        hdr = self.headers.get("Authorization", "")
        if not hdr.startswith("Basic "):
            return False
        try:
            u, _, p = base64.b64decode(hdr[6:]).decode().partition(":")
        except Exception:
            return False
        return u == AUTH_USER and p == AUTH_PASS

    def _need_auth(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Donghua Dashboard"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if not self._authed():
            return self._need_auth()
        parts = urllib.parse.urlparse(self.path)
        if parts.path in ("/", "/index.html"):
            q = urllib.parse.parse_qs(parts.query)
            self._send(200, render(q.get("c", [None])[0]))
        else:
            self._send(404, "not found")

    def do_POST(self):
        if not self._authed():
            return self._need_auth()
        if self.path != "/do":
            self._send(404, "not found"); return
        n = int(self.headers.get("Content-Length", 0))
        form = urllib.parse.parse_qs(self.rfile.read(n).decode())
        action = form.get("action", [""])[0]
        cid = form.get("channel", [""])[0]
        topic = form.get("topic", [""])[0]
        try:
            if action == "post":
                pipeline.post(cid, topic)
            elif action == "build":
                pipeline.build(cid, topic)
            elif action == "drip":
                pipeline.all_in_channel(cid, limit=1)
            elif action == "set_source":
                url = form.get("source", [""])[0].strip()
                if url:
                    _jobs[cid + "/" + topic] = "downloading…"
                    threading.Thread(target=fetch_footage_job,
                                     args=(cid, topic, url), daemon=True).start()
            elif action == "fetch":
                tp = os.path.join(pipeline.channel_dir(cid), "topics", topic)
                meta, _ = util.parse_topic(tp)
                url = meta.get("source", "").strip()
                if url.startswith("http"):
                    _jobs[cid + "/" + topic] = "downloading…"
                    threading.Thread(target=fetch_footage_job,
                                     args=(cid, topic, url), daemon=True).start()
            _cache.clear()
        except (SystemExit, Exception) as e:
            print("[dashboard] action %s failed: %s" % (action, e))
        self.send_response(303)
        self.send_header("Location", "/?c=" + urllib.parse.quote(cid) if cid else "/")
        self.end_headers()


def main():
    host, port = "127.0.0.1", PORT
    a = sys.argv[1:]
    for i, x in enumerate(a):
        if x == "--host" and i + 1 < len(a):
            host = a[i + 1]
        if x == "--port" and i + 1 < len(a):
            port = int(a[i + 1])
    # Safety: never bind to a public interface without a password.
    if host != "127.0.0.1" and not AUTH_PASS:
        sys.exit("Refusing to bind %s with no DASHBOARD_PASS set in secrets.env — "
                 "that would expose your Pages to anyone. Set DASHBOARD_PASS first." % host)
    if AUTH_PASS:
        print("Auth: ON (user=%s). Safe to expose via tunnel." % AUTH_USER)
    else:
        print("Auth: OFF — localhost only. Set DASHBOARD_PASS to expose remotely.")
    print("Dashboard: http://%s:%d   (Ctrl-C to stop)" % (host, port))
    http.server.HTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
