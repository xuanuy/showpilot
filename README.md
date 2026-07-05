# ShowPilot — the autonomous AI showrunner

**Qwen Cloud Global AI Hackathon 2026 · Track: AI Showrunner**

Give ShowPilot a one-line topic and it writes, storyboards, renders, voices,
edits, publishes, and grows short-drama channels — every day, no humans on set.
It doesn't make *a video*; it runs a **fleet of channels on a daily schedule**.

```
topic.md ─► Qwen (script) ─► Qwen (storyboard) ─► Wan (video shots)
        └────────────────────────► Piper TTS (voiceover)
                                        │
        ffmpeg (fit/concat/captions/mux) ◄─┘
                                        │
        Facebook Graph API (Reel + first-comment CTA + 24h Story)
                                        │
        dashboard (per-channel metrics) + daily cron drip
```

## What makes it a *showrunner*, not a generator

- **Multi-channel**: every Facebook Page is a "channel" with its own voice,
  topic queue, and credentials (`channels.json` + `channels/<id>/`).
- **Daily schedule**: a cron drip posts one un-posted topic per channel per day;
  per-topic failures are logged and skipped so an unattended run never dies.
- **Audience growth built in**: after publishing, the agent posts the script's
  CTA question as the first comment and re-shares the Reel as a 24 h Story.
- **Ops dashboard**: token health, followers, per-reel views/likes/comments,
  one-click build/post (`dashboard.py`, ngrok tunnel for remote/mobile).

## Qwen Cloud integration

| Stage | Model | Where |
|---|---|---|
| Scriptwriting | `qwen3.7-plus` (OpenAI-compatible endpoint) | `lib/qwen.py`, `lib/script_gen.py` |
| Storyboarding (scene → shot prompts, style continuity) | `qwen3.7-plus` | `lib/qwen.py` |
| Video generation (async task API, 9:16) | `wan2.6-t2v` | `lib/wan.py`, `lib/wanmode.py` |

Wan shots are cached per scene (`build/<topic>/wan/`) so a re-run never
re-spends credits; video URLs are downloaded immediately (they expire in 24 h).

## Quick start

```bash
cp secrets.env.example secrets.env   # add DASHSCOPE_API_KEY (+ FB page creds to publish)
python3 pipeline.py init
python3 pipeline.py build donghua-realm the-sword-that-refused.md   # Wan demo topic
python3 pipeline.py post  donghua-realm the-sword-that-refused.md   # publish it
python3 pipeline.py all-channels                                    # the daily drip
```

Tools (no admin needed, all portable): `ffmpeg`, `piper` (+ an en_US voice),
optional `yt-dlp` — paths in `config.json`. `deploy/bootstrap.sh` installs
everything into `~/.local` on a fresh Linux box.

## Content modes

| Frontmatter | Pipeline |
|---|---|
| `mode: wan` | Qwen storyboard → Wan generated shots (fully generative) |
| `mode: story` | stock stills (Pexels) + Ken Burns motion |
| `footage: x.mp4` | commentary over licensed/owned footage |

## Deploy (Alibaba Cloud)

See [`deploy/alibaba/README.md`](deploy/alibaba/README.md) — ECS Ubuntu 22.04 in
ap-southeast-1, `deploy/bootstrap.sh`, systemd units for the dashboard/tunnel,
and the daily cron.

## Honest-content rules

Only generated content, official trailers/PV used under commentary, or our own
recordings are ever published. No scraped/reuploaded clips — the pipeline
refuses topics whose footage isn't present locally, and `mode: wan` needs none.

## Layout

```
pipeline.py        CLI: init | channels | list | build | post | all | all-channels
lib/qwen.py        Qwen Cloud chat + storyboard client (stdlib only)
lib/wan.py         Wan async text-to-video client (create → poll → download)
lib/wanmode.py     mode:wan build (storyboard → shots → fit/concat → captions/mux)
lib/storymode.py   mode:story build (Pexels stills + Ken Burns)
lib/script_gen.py  script priority: topic file → Qwen → (fallback) Claude
lib/tts.py         Piper voiceover + proportional ASS captions
lib/assemble.py    footage-mode ffmpeg assembly
lib/fb_post.py     Reels/Story/comment publishing (Graph API)
dashboard.py       ops dashboard (stdlib http.server + Basic Auth)
deploy/            Linux bundle + alibaba/ (ECS) + mac/ (launchd)
```

## License

MIT — see [LICENSE](LICENSE).
