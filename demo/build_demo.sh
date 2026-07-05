#!/usr/bin/env bash
# Assemble the final Devpost demo video from screen recordings + narration.
#   demo/rec/01.mp4 .. 07.mp4   your screen recordings (any resolution)
#   demo/vo/01.wav  .. 07.wav   narration from make_vo.sh
# Each segment lasts exactly as long as its narration; the recording is
# sped up to fit if it runs longer. Output: demo/showpilot-demo.mp4 (1080p).
set -euo pipefail
cd "$(dirname "$0")"
FFMPEG=$(python3 -c "import json;print(json.load(open('../config.json'))['tools']['ffmpeg'])")
FFPROBE=$(python3 -c "import json;print(json.load(open('../config.json'))['tools']['ffprobe'])")
mkdir -p seg

dur() { "$FFPROBE" -v error -show_entries format=duration -of csv=p=0 "$1"; }

for w in vo/*.wav; do
  n=$(basename "$w" .wav)
  r="rec/$n.mp4"
  [ -f "$r" ] || { echo "missing $r — record it (see SCRIPT.md)"; exit 1; }
  vd=$(dur "$w"); rd=$(dur "$r")
  # speed factor so the recording exactly covers the narration (+0.5s tail)
  sp=$(python3 -c "print(max(1.0, $rd/($vd+0.5)))")
  "$FFMPEG" -y -v error -i "$r" -i "$w" \
    -filter_complex "[0:v]setpts=PTS/$sp,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30[v]" \
    -map "[v]" -map 1:a -t "$(python3 -c "print($vd+0.5)")" \
    -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p -c:a aac -b:a 128k \
    "seg/$n.mp4"
  echo "seg/$n.mp4 (${vd%s}s, speed x$sp)"
done

: > seg/list.txt
for s in seg/0*.mp4; do echo "file '$(basename "$s")'" >> seg/list.txt; done
(cd seg && "$FFMPEG" -y -v error -f concat -safe 0 -i list.txt -c copy ../showpilot-demo.mp4)
echo "DONE -> demo/showpilot-demo.mp4 ($(dur showpilot-demo.mp4)s)"
