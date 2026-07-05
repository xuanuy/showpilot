#!/usr/bin/env bash
# Provision a fresh Oracle Cloud Ubuntu VM (ARM Ampere A1 or AMD micro) for the
# donghua pipeline. Installs portable ffmpeg/piper/yt-dlp/ngrok (arch-aware),
# fixes config paths, and re-downloads footage from each topic's recorded source.
# Idempotent — safe to re-run.
set -e
cd "$(dirname "$0")/.."
PROJ="$(pwd)"
ARCH="$(uname -m)"
echo "== bootstrap ==  arch=$ARCH  home=$HOME  project=$PROJ"

case "$ARCH" in
  aarch64|arm64) FF=linuxarm64; PIPER=aarch64; YT=yt-dlp_linux_aarch64; NG=arm64 ;;
  x86_64|amd64)  FF=linux64;    PIPER=x86_64;  YT=yt-dlp_linux;         NG=amd64 ;;
  *) echo "unsupported arch: $ARCH"; exit 1 ;;
esac

echo "== system packages =="
sudo apt-get update -y
sudo apt-get install -y python3 cron xz-utils ca-certificates curl wget tar
# cron 20:00 should mean Singapore time
sudo timedatectl set-timezone Asia/Singapore || true

mkdir -p ~/.local/bin ~/.local/opt ~/.local/opt/piper-voices

echo "== ffmpeg =="
if [ ! -e ~/.local/bin/ffmpeg ]; then
  wget -qO /tmp/ff.tar.xz "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-${FF}-gpl.tar.xz"
  tar -xf /tmp/ff.tar.xz -C ~/.local/opt
  D="$(ls -d ~/.local/opt/ffmpeg-master-latest-${FF}-gpl* | head -1)"
  ln -sf "$D/bin/ffmpeg" ~/.local/bin/ffmpeg
  ln -sf "$D/bin/ffprobe" ~/.local/bin/ffprobe
fi

echo "== piper + voice =="
if [ ! -e ~/.local/bin/piper ]; then
  wget -qO /tmp/piper.tgz "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_${PIPER}.tar.gz"
  tar -xf /tmp/piper.tgz -C ~/.local/opt
  ln -sf ~/.local/opt/piper/piper ~/.local/bin/piper
fi
V=~/.local/opt/piper-voices/en_US-ryan-high.onnx
if [ ! -f "$V" ]; then
  wget -qO "$V"      "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx?download=true"
  wget -qO "$V.json" "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx.json?download=true"
fi

echo "== yt-dlp =="
if [ ! -e ~/.local/bin/yt-dlp ]; then
  wget -qO ~/.local/bin/yt-dlp "https://github.com/yt-dlp/yt-dlp/releases/latest/download/${YT}"
  chmod +x ~/.local/bin/yt-dlp
fi

echo "== ngrok =="
if [ ! -e ~/.local/bin/ngrok ]; then
  wget -qO /tmp/ngrok.tgz "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-${NG}.tgz"
  tar -xf /tmp/ngrok.tgz -C ~/.local/bin
  chmod +x ~/.local/bin/ngrok
fi

echo "== point config.json tool paths at this machine =="
python3 - "$PROJ/config.json" "$HOME" <<'PY'
import json, sys
p, home = sys.argv[1], sys.argv[2]
c = json.load(open(p)); t = c["tools"]
t["ffmpeg"]  = home + "/.local/bin/ffmpeg"
t["ffprobe"] = home + "/.local/bin/ffprobe"
t["piper"]   = home + "/.local/bin/piper"
t["piper_voice"] = home + "/.local/opt/piper-voices/en_US-ryan-high.onnx"
json.dump(c, open(p, "w"), indent=2)
print("  ->", home)
PY

export PATH="$HOME/.local/bin:$PATH"
python3 pipeline.py init >/dev/null 2>&1 || true

echo "== re-download footage from recorded sources =="
python3 "$PROJ/deploy/refetch_footage.py" || true

echo
echo "== installed =="
for b in ffmpeg ffprobe yt-dlp ngrok; do printf "  %-8s %s\n" "$b" "$("$HOME/.local/bin/$b" --version 2>&1 | head -1)"; done
[ -x ~/.local/bin/piper ] && echo "  piper    installed"
echo
echo "NEXT:"
echo "  1) cp secrets.env.example secrets.env   # fill FB tokens, DASHBOARD_PASS, NGROK_DOMAIN"
echo "  2) ngrok config add-authtoken <YOUR_TOKEN>"
echo "  3) bash deploy/install-services.sh"
