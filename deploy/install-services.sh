#!/usr/bin/env bash
# Install + enable systemd services (dashboard, ngrok) and the daily-post cron.
# Run after bootstrap.sh and after filling secrets.env.
set -e
cd "$(dirname "$0")/.."
PROJ="$(pwd)"; U="$USER"; H="$HOME"

# guards
grep -q '^DASHBOARD_PASS=.\+' secrets.env 2>/dev/null \
  || { echo "ERROR: set a strong DASHBOARD_PASS in secrets.env (ngrok exposes the dashboard)."; exit 1; }
grep -q '^NGROK_DOMAIN=.\+' secrets.env 2>/dev/null \
  || { echo "ERROR: set NGROK_DOMAIN in secrets.env (your reserved ngrok static domain)."; exit 1; }
ngrok config check >/dev/null 2>&1 \
  || { echo "ERROR: run 'ngrok config add-authtoken <TOKEN>' first."; exit 1; }

chmod +x deploy/run-ngrok.sh run-cron.sh 2>/dev/null || true

echo "== installing systemd units =="
for svc in donghua-dashboard donghua-ngrok; do
  sed -e "s#__USER__#$U#g" -e "s#__PROJ__#$PROJ#g" -e "s#__HOME__#$H#g" \
      "deploy/$svc.service" | sudo tee "/etc/systemd/system/$svc.service" >/dev/null
done
sudo systemctl daemon-reload
sudo systemctl enable --now donghua-dashboard
sleep 2
sudo systemctl enable --now donghua-ngrok

echo "== daily post cron (20:00 VM time) =="
( crontab -l 2>/dev/null | grep -v 'run-cron.sh'; echo "0 20 * * * $PROJ/run-cron.sh" ) | crontab -

echo
echo "== status =="
systemctl --no-pager --full status donghua-dashboard donghua-ngrok 2>/dev/null | grep -E 'Active:|Loaded:' || true
echo
DOMAIN="$(grep '^NGROK_DOMAIN=' secrets.env | cut -d= -f2-)"
echo "Dashboard should now be live at:  https://$DOMAIN   (login: DASHBOARD_USER / DASHBOARD_PASS)"
echo "Logs:  journalctl -u donghua-dashboard -f   |   journalctl -u donghua-ngrok -f"
