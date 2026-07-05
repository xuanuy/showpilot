#!/usr/bin/env bash
# Generate the demo narration wavs (demo/vo/01.wav .. 07.wav) with Piper,
# reading the quoted narration blocks out of SCRIPT.md.
set -euo pipefail
cd "$(dirname "$0")"
PIPER=$(python3 -c "import json;print(json.load(open('../config.json'))['tools']['piper'])")
VOICE=$(python3 -c "import json;print(json.load(open('../config.json'))['tools']['piper_voice'])")
mkdir -p vo

python3 - <<'EOF'
import re
text = open("SCRIPT.md", encoding="utf-8").read()
sections = re.findall(r"## (\d+) ·.*?\n\n((?:> .*\n?)+)", text)
for num, block in sections:
    vo = " ".join(l[2:].strip() for l in block.splitlines() if l.startswith("> "))
    open("vo/%s.txt" % num, "w", encoding="utf-8").write(vo + "\n")
    print(num, len(vo.split()), "words")
EOF

for t in vo/*.txt; do
  n=$(basename "$t" .txt)
  "$PIPER" --model "$VOICE" --output_file "vo/$n.wav" < "$t"
  echo "vo/$n.wav"
done
