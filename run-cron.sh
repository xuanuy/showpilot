#!/usr/bin/env bash
# Cron entrypoint: post every channel's un-posted topics. Logs to cron.log.
# Tools (ffmpeg/piper/yt-dlp/python) live in ~/.local/bin — put it on PATH.
export PATH="$HOME/.local/bin:$PATH"
cd "$(dirname "$0")" || exit 1
echo "===== run $(date '+%Y-%m-%d %H:%M:%S') =====" >> cron.log
python3 pipeline.py all-channels >> cron.log 2>&1
echo "----- done $(date '+%Y-%m-%d %H:%M:%S') -----" >> cron.log
