# I built an AI showrunner on Qwen Cloud — it publishes a new episode every day, and no human is on set

*Built for the Qwen Cloud Global AI Hackathon 2026, AI Showrunner track. Code: https://github.com/xuanuy/showpilot*

## The problem isn't making videos. It's making them every day.

I run a small fleet of Facebook Pages about donghua (Chinese animation). The
lesson from months of running them is brutal and simple: **channels don't die
from bad content — they die from missed days.** The algorithm rewards
consistency, and no solo creator sustains a daily episode across nine pages.

I already had a pipeline that could assemble commentary reels from licensed
footage. But the creative core — writing, visualizing, producing — was still
me. For the hackathon I asked: what if the *entire studio* was one agent?

## What ShowPilot does

Give it a topic file with a title and a theme — one line of human input — and it:

1. **Writes** the script (Qwen `qwen3.7-plus`): a 130-word voiceover with a
   hook in the first three seconds and a cliffhanger question at the end.
2. **Storyboards** it (Qwen again, different hat): the script is split into
   scenes, and Qwen writes one Wan shot-prompt per scene.
3. **Renders** every shot (Wan `wan2.6-t2v`): vertical 9:16, via the async
   task API.
4. **Voices, edits, captions** (Piper TTS + ffmpeg): each shot is fitted to
   the narration timing, concatenated, subtitled, muxed.
5. **Publishes and grows**: posts the Reel through the Facebook Graph API,
   drops the script's closing question as the first comment (comments are
   what the algorithm rewards), and re-shares it as a 24-hour Story.
6. **Repeats tomorrow**: a cron drip publishes one new episode per channel
   per day. Failures are logged and skipped — one bad topic never kills the
   nightly run.

## Three things I learned building on Qwen Cloud

**1. Style continuity is a prompt-engineering problem, not a model problem.**
My first storyboards gave every scene a different hero and palette. The fix
was embarrassingly simple: make Qwen restate the same style descriptor in
*every* shot prompt ("cinematic 3D animation, high fantasy xianxia, white-robed
cultivator, glowing teal sword..."). Wan then kept the character consistent
across all six shots of my demo episode. The storyboard system prompt does
this automatically now.

**2. Respect the async task lifecycle — and cache aggressively.**
Wan tasks take 1–5 minutes and return a video URL that expires in 24 hours.
ShowPilot downloads every shot the moment it succeeds and caches it per scene
(`build/<topic>/wan/`). A crashed build resumes for free; a retry never
re-spends credits. If you build on Wan, do this on day one — my whole Wan
client is ~70 lines of stdlib Python (`lib/wan.py`) and half of it is this.

**3. The OpenAI-compatible endpoint makes adoption trivial.**
Swapping my script generator to Qwen was a 20-line change: point at
`dashscope-intl.aliyuncs.com/compatible-mode/v1`, send the same messages
array. No SDK, no new dependency — `urllib` from the standard library.

## The result

My first fully-generative episode — *"The Sword That Refused Its Master"* —
went from a one-line topic to a published Facebook Reel in a single command:
40 seconds, six Wan-generated shots with a consistent hero, burned captions,
voiceover, engagement comment and Story, all unattended. It's live on the
page next to weeks of earlier daily reels the same pipeline published.

The backend runs on an Alibaba Cloud ECS instance in Singapore (same region
as the Qwen endpoint), provisioned entirely from the CLI
(`deploy/alibaba/provision.sh`), with systemd keeping the ops dashboard and
the daily schedule alive.

## The one-sentence takeaway

An agent that ships daily beats a better agent that ships once. Qwen writes,
Wan shoots, the agent runs the channel — the human just reads the metrics.

*ShowPilot is MIT-licensed: https://github.com/xuanuy/showpilot — demo video
and architecture diagram in the Devpost submission.*
