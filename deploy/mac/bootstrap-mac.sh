#!/usr/bin/env bash
# Provision a Mac (Intel, macOS) to run the donghua pipeline 24/7.
# Installs portable ffmpeg/piper/yt-dlp/ngrok into ~/.local, clears Gatekeeper
# quarantine, fixes config paths, and re-downloads footage from recorded sources.
# Idempotent.
set -e
cd "$(dirname "$0")/../.."
PROJ="$(pwd)"
echo "== macOS bootstrap ==  home=$HOME  project=$PROJ"

command -v python3 >/dev/null 2>&1 || {
  echo "python3 not found. Install Xcode Command Line Tools first:"
  echo "  xcode-select --install"
  echo "then re-run this script."; exit 1; }

mkdir -p ~/.local/bin ~/.local/opt ~/.local/opt/piper-voices
cd /tmp

echo "== ffmpeg + ffprobe (evermeet static, Intel) =="
if [ ! -e ~/.local/bin/ffmpeg ]; then
  curl -fL -o ff.zip "https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip"
  unzip -o ff.zip -d ~/.local/bin >/dev/null
  curl -fL -o fp.zip "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip"
  unzip -o fp.zip -d ~/.local/bin >/dev/null
  chmod +x ~/.local/bin/ffmpeg ~/.local/bin/ffprobe
fi

echo "== piper + voice =="
if [ ! -e ~/.local/bin/piper ]; then
  curl -fL -o piper.tgz "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_macos_x64.tar.gz"
  tar -xf piper.tgz -C ~/.local/opt
  ln -sf ~/.local/opt/piper/piper ~/.local/bin/piper
fi
V=~/.local/opt/piper-voices/en_US-ryan-high.onnx
[ -f "$V" ]      || curl -fL -o "$V"      "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx?download=true"
[ -f "$V.json" ] || curl -fL -o "$V.json" "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx.json?download=true"

echo "== yt-dlp =="
if [ ! -e ~/.local/bin/yt-dlp ]; then
  curl -fL -o ~/.local/bin/yt-dlp "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos"
  chmod +x ~/.local/bin/yt-dlp
fi

echo "== ngrok =="
if [ ! -e ~/.local/bin/ngrok ]; then
  curl -fL -o ngrok.zip "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-darwin-amd64.zip"
  unzip -o ngrok.zip -d ~/.local/bin >/dev/null
  chmod +x ~/.local/bin/ngrok
fi

echo "== clear Gatekeeper quarantine (so unsigned binaries can run) =="
xattr -dr com.apple.quarantine ~/.local/bin ~/.local/opt/piper 2>/dev/null || true

echo "== point config.json at this machine =="
python3 - "$PROJ/config.json" "$HOME" <<'PY'
import json, sys
p, home = sys.argv[1], sys.argv[2]
c = json.load(open(p)); t = c["tools"]
t["ffmpeg"]  = home + "/.local/bin/ffmpeg"
t["ffprobe"] = home + "/.local/bin/ffprobe"
t["piper"]   = home + "/.local/bin/piper"
t["piper_voice"] = home + "/.local/opt/piper-voices/en_US-ryan-high.onnx"
json.dump(c, open(p, "w"), indent=2); print("  ->", home)
PY

export PATH="$HOME/.local/bin:$PATH"
python3 pipeline.py init >/dev/null 2>&1 || true
echo "== re-download footage from recorded sources =="
python3 "$PROJ/deploy/refetch_footage.py" || true

echo; echo "== installed =="
~/.local/bin/ffmpeg -version 2>&1 | head -1
echo "yt-dlp $(~/.local/bin/yt-dlp --version 2>&1)"
~/.local/bin/ngrok --version 2>&1 | head -1
echo
echo "NEXT:"
echo "  1) cp secrets.env.example secrets.env   # fill FB tokens, DASHBOARD_PASS, NGROK_DOMAIN"
echo "  2) ~/.local/bin/ngrok config add-authtoken <YOUR_TOKEN>"
echo "  3) bash deploy/mac/install-mac.sh"
