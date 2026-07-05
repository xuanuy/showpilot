#!/usr/bin/env bash
# Run LOCALLY (on your WSL machine) to package the project for upload to the VM.
# Excludes heavy/regenerable files (footage mp4s, build, output mp4s) and secrets,
# but KEEPS topics (with their source: URLs) and posted.json markers (so the cloud
# box knows what's already posted and re-downloads footage from sources).
set -e
cd "$(dirname "$0")/.."
OUT=/tmp/fb-anime-pipeline.tgz
tar czf "$OUT" \
  --exclude='./channels/*/footage/*.mp4' \
  --exclude='./channels/*/build' \
  --exclude='./channels/*/output/*.mp4' \
  --exclude='./secrets.env' \
  --exclude='*.pyc' --exclude='__pycache__' \
  --exclude='./.git' \
  .
echo "bundle: $OUT  ($(du -h "$OUT" | cut -f1))"
echo
echo "Upload + unpack on the VM:"
echo "  scp $OUT ubuntu@<VM_PUBLIC_IP>:~/"
echo "  ssh ubuntu@<VM_PUBLIC_IP>"
echo "  mkdir -p ~/fb-anime-pipeline && tar xzf ~/fb-anime-pipeline.tgz -C ~/fb-anime-pipeline"
