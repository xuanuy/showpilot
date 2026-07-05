"""Publish to a Facebook Page via the Graph API (resumable upload), plus organic
boost helpers (first comment, share-to-Story). Standard library only.

Reel/Story flow per Meta docs:
  1) start  -> {video_id, upload_url}
  2) upload -> POST raw bytes to upload_url with OAuth + offset/file_size headers
  3) finish -> publish

Requires (in secrets.env, per channel): FB_PAGE_ID, FB_PAGE_ACCESS_TOKEN.
Reels/Stories need pages_manage_posts; first comment needs pages_manage_engagement.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request


class FBError(RuntimeError):
    pass


def _read_err(e):
    try:
        body = e.read().decode()
    except Exception:
        body = ""
    try:
        j = json.loads(body)
        err = j.get("error", {})
        return "FB %s: %s (type=%s code=%s subcode=%s) trace=%s" % (
            e.code, err.get("message", ""), err.get("type", ""),
            err.get("code", ""), err.get("error_subcode", ""),
            err.get("fbtrace_id", ""))
    except Exception:
        return "HTTP %s: %s" % (e.code, body[:500])


def _graph(url, params, method="POST"):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise FBError(_read_err(e))


def _upload_file(upload_url, token, mp4_path):
    """Phase 2: push the whole file in one shot (reels/stories are small)."""
    size = os.path.getsize(mp4_path)
    with open(mp4_path, "rb") as f:
        body = f.read()
    req = urllib.request.Request(upload_url, data=body, method="POST")
    req.add_header("Authorization", "OAuth %s" % token)
    req.add_header("offset", "0")
    req.add_header("file_size", str(size))
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise FBError(_read_err(e))


def publish_reel(mp4_path, description, cfg, secrets):
    page_id = secrets["FB_PAGE_ID"]
    token = secrets["FB_PAGE_ACCESS_TOKEN"]
    ver = cfg["facebook"]["graph_version"]
    base = "https://graph.facebook.com/%s/%s/video_reels" % (ver, page_id)

    start = _graph(base, {"upload_phase": "start", "access_token": token})
    video_id = start["video_id"]
    up = _upload_file(start["upload_url"], token, mp4_path)
    if not up.get("success", True):
        raise FBError("upload failed: %s" % up)
    fin = _graph(base, {
        "upload_phase": "finish",
        "video_id": video_id,
        "video_state": cfg["facebook"]["publish_state"],
        "description": description,
        "access_token": token,
    })
    return {"video_id": video_id, "finish": fin}


def publish_story(mp4_path, cfg, secrets):
    """Publish the same vertical video as a 24h Story (extra reach). Needs
    pages_manage_posts. Video must be vertical and <=60s (our reels qualify)."""
    page_id = secrets["FB_PAGE_ID"]
    token = secrets["FB_PAGE_ACCESS_TOKEN"]
    ver = cfg["facebook"]["graph_version"]
    base = "https://graph.facebook.com/%s/%s/video_stories" % (ver, page_id)

    start = _graph(base, {"upload_phase": "start", "access_token": token})
    video_id = start["video_id"]
    up = _upload_file(start["upload_url"], token, mp4_path)
    if not up.get("success", True):
        raise FBError("story upload failed: %s" % up)
    fin = _graph(base, {
        "upload_phase": "finish",
        "video_id": video_id,
        "access_token": token,
    })
    return {"story_video_id": video_id, "finish": fin}


def post_comment(video_id, message, cfg, secrets):
    """Post a comment as the Page on its own reel. Needs pages_manage_engagement."""
    token = secrets["FB_PAGE_ACCESS_TOKEN"]
    ver = cfg["facebook"]["graph_version"]
    url = "https://graph.facebook.com/%s/%s/comments" % (ver, video_id)
    return _graph(url, {"message": message, "access_token": token})
