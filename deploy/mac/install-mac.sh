#!/usr/bin/env bash
# Install launchd agents (dashboard, ngrok, daily-post, caffeinate) on macOS.
# Run after bootstrap-mac.sh and after filling secrets.env + ngrok authtoken.
set -e
cd "$(dirname "$0")/../.."
PROJ="$(pwd)"; H="$HOME"; LA="$HOME/Library/LaunchAgents"

grep -q '^DASHBOARD_PASS=.\+' secrets.env 2>/dev/null \
  || { echo "ERROR: set a strong DASHBOARD_PASS in secrets.env (ngrok exposes the dashboard)."; exit 1; }
grep -q '^NGROK_DOMAIN=.\+' secrets.env 2>/dev/null \
  || { echo "ERROR: set NGROK_DOMAIN in secrets.env (your reserved ngrok static domain)."; exit 1; }
~/.local/bin/ngrok config check >/dev/null 2>&1 \
  || { echo "ERROR: run '~/.local/bin/ngrok config add-authtoken <TOKEN>' first."; exit 1; }

chmod +x deploy/run-ngrok.sh run-cron.sh 2>/dev/null || true
mkdir -p "$LA"

for p in dashboard ngrok post caffeinate; do
  dst="$LA/com.donghua.$p.plist"
  sed -e "s#__PROJ__#$PROJ#g" -e "s#__HOME__#$H#g" "deploy/mac/com.donghua.$p.plist" > "$dst"
  launchctl unload "$dst" 2>/dev/null || true
  launchctl load "$dst"
  echo "loaded: com.donghua.$p"
done

echo
echo "Services running. Logs: /tmp/donghua-dashboard.log , /tmp/donghua-ngrok.log , cron.log"
DOMAIN="$(grep '^NGROK_DOMAIN=' secrets.env | cut -d= -f2-)"
echo "Dashboard: https://$DOMAIN   (login: DASHBOARD_USER / DASHBOARD_PASS)"
echo
echo "Keep it awake & alive:"
echo "  - caffeinate agent prevents sleep while the LID IS OPEN + on power."
echo "  - For LID-CLOSED 24/7:   sudo pmset -c disablesleep 1"
echo "  - System Settings > Users & Groups: enable AUTOMATIC LOGIN so agents start after a reboot."
echo "  - Keep it plugged in. Don't run ngrok anywhere else (free = 1 agent)."
