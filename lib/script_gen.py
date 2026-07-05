"""Produce the narration script for a video.

Priority:
1. If the topic file already has a non-empty `## Script` section -> use it as-is.
   (This is the default path: Claude Code writes the scripts for you, for free.)
2. Else, if DASHSCOPE_API_KEY is set (secrets.env or env), generate via Qwen.
3. Else, if ANTHROPIC_API_KEY is set and the `anthropic` package is installed,
   generate the script automatically from the topic metadata.
4. Else raise, telling the user to fill in the Script section.
"""
import os

from . import qwen


SYSTEM = (
    "You write punchy, original English voiceover scripts for short vertical "
    "Facebook Reels about Chinese animation (donghua) and xianxia/cultivation anime. "
    "The script is YOUR commentary and analysis - it must stand on its own as "
    "original opinion/explanation, never just describe what is on screen. "
    "Open with a 1-line hook in the first 3 seconds. Be specific and have a take. "
    "No emojis, no stage directions, no markdown - just the words to be spoken."
)


def generate(meta, existing_script, cfg):
    if existing_script and existing_script.strip():
        return existing_script.strip()

    if qwen.api_key():
        try:
            return qwen.chat(SYSTEM, _prompt(meta, cfg), cfg, max_tokens=600)
        except Exception as e:
            raise RuntimeError("Qwen script generation failed: %s" % e)

    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        try:
            return _via_api(meta, cfg, key)
        except Exception as e:  # fall through to a clear error
            raise RuntimeError("API script generation failed: %s" % e)

    raise RuntimeError(
        "No script found. Add a `## Script` section to the topic file "
        "(ask Claude Code to write it), or set DASHSCOPE_API_KEY / "
        "ANTHROPIC_API_KEY for auto-generation."
    )


def _prompt(meta, cfg):
    words = cfg["script"]["target_words"]
    brief = "\n".join("%s: %s" % (k, v) for k, v in meta.items())
    return (
        "Write a %d-word voiceover script for a Reels commentary video.\n\n"
        "Brief:\n%s\n\n"
        "Requirements: strong hook line first, one clear opinion/insight, "
        "end with a question or call to engage. Output only the spoken words."
        % (words, brief)
    )


def _via_api(meta, cfg, key):
    import anthropic
    client = anthropic.Anthropic(api_key=key)
    prompt = _prompt(meta, cfg)
    msg = client.messages.create(
        model=cfg["script"]["model"],
        max_tokens=600,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()
