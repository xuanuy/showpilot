"""Shared helpers: config loading, command execution, topic parsing."""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config():
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def load_secrets():
    """Load secrets.env (KEY=VALUE lines) into a dict. Missing file -> {}."""
    path = os.path.join(ROOT, "secrets.env")
    env = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def run(cmd, **kw):
    """Run a command, streaming nothing, raising on failure with captured output."""
    proc = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise RuntimeError("command failed (%d): %s" % (proc.returncode, " ".join(cmd[:4]) + " ..."))
    return proc


def probe_duration(ffprobe, path):
    out = run([ffprobe, "-v", "error", "-show_entries", "format=duration",
               "-of", "csv=p=0", path]).stdout.strip()
    return float(out)


def parse_topic(path):
    """Parse a topic .md file: simple `key: value` frontmatter between --- fences,
    then a `## Script` section (the narration). Returns (meta_dict, script_text)."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    meta = {}
    body = text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        body = m.group(2)
    # Extract the Script section (everything after a "## Script" heading).
    script = ""
    sm = re.search(r"##\s*Script\s*\n(.*?)(?:\n##\s|\Z)", body, re.S | re.I)
    if sm:
        script = sm.group(1).strip()
    return meta, script


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
