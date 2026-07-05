#!/usr/bin/env bash
# Expose the dashboard to a public HTTPS URL (phone, anywhere).
# Cloudflare quick tunnel (outbound only — works through WSL2, no admin, no account).
# Safety: always restarts the dashboard fresh so it loads the CURRENT password, then
# verifies auth is actually enforced (HTTP 401 without login) BEFORE exposing it.
set -e
export PATH="$HOME/.local/bin:$PATH"
cd "$(dirname "$0")"

# 1. require a non-empty password
PW=$(grep '^DASHBOARD_PASS=' secrets.env 2>/dev/null | cut -d= -f2-)
if [ -z "$PW" ]; then
  echo "ERROR: DASHBOARD_PASS is empty in secrets.env. Set a strong password first."
  exit 1
fi

# 2. stop any existing dashboard + tunnel so we start clean (avoids stale no-auth proc)
fuser -k 8765/tcp 2>/dev/null || true
pkill -f 'cloudflared tunnel --url http://127.0.0.1:8765' 2>/dev/null || true
sleep 1

# 3. start a fresh dashboard (loads the current password from secrets.env)
nohup python3 dashboard.py >/tmp/dashboard.log 2>&1 &
sleep 2

# 4. PRE-FLIGHT: the dashboard MUST reject unauthenticated requests before we expose it
CODE=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8765/)
if [ "$CODE" != "401" ]; then
  echo "ABORT: dashboard is not requiring login (HTTP $CODE, expected 401)."
  echo "Refusing to expose. Check DASHBOARD_PASS and /tmp/dashboard.log."
  fuser -k 8765/tcp 2>/dev/null || true
  exit 1
fi
echo "Auth verified (401 without login). Opening public tunnel..."
echo "Look for https://*.trycloudflare.com below — log in with DASHBOARD_USER / DASHBOARD_PASS."

exec cloudflared tunnel --url http://127.0.0.1:8765
