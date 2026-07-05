#!/usr/bin/env bash
# Expose the dashboard at a FIXED free URL via ngrok (no domain ownership needed).
# Free ngrok gives one static domain like  abc-123.ngrok-free.app  that never changes.
# Same safety as tunnel.sh: restart dashboard fresh + verify auth (401) before exposing.
set -e
export PATH="$HOME/.local/bin:$PATH"
cd "$(dirname "$0")"

PW=$(grep '^DASHBOARD_PASS=' secrets.env 2>/dev/null | cut -d= -f2-)
[ -z "$PW" ] && { echo "ERROR: set a strong DASHBOARD_PASS in secrets.env first."; exit 1; }

DOMAIN=$(grep '^NGROK_DOMAIN=' secrets.env 2>/dev/null | cut -d= -f2-)
[ -z "$DOMAIN" ] && { echo "ERROR: set NGROK_DOMAIN in secrets.env (your free static domain, e.g. abc-123.ngrok-free.app)."; exit 1; }

# authtoken configured + config valid?
if ! ngrok config check >/dev/null 2>&1; then
  echo "ERROR: ngrok config invalid or missing authtoken. Run once:"
  echo "  ngrok config add-authtoken <YOUR_TOKEN>   (https://dashboard.ngrok.com)"
  exit 1
fi

# restart dashboard so it loads the current password, then verify auth before exposing
fuser -k 8765/tcp 2>/dev/null || true
sleep 1
nohup python3 dashboard.py >/tmp/dashboard.log 2>&1 &
sleep 2
CODE=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8765/)
if [ "$CODE" != "401" ]; then
  echo "ABORT: dashboard is not requiring login (HTTP $CODE, expected 401). Not exposing."
  fuser -k 8765/tcp 2>/dev/null || true
  exit 1
fi

echo "Auth verified. Fixed URL:  https://$DOMAIN"
echo "Open it on your phone and log in with DASHBOARD_USER / DASHBOARD_PASS."
exec ngrok http --url="https://$DOMAIN" 8765
