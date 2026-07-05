#!/usr/bin/env bash
# Tunnel ngrok -> local dashboard at the fixed NGROK_DOMAIN. Used by the systemd
# service. Does NOT touch the dashboard (donghua-dashboard.service owns that).
export PATH="$HOME/.local/bin:$PATH"
cd "$(dirname "$0")/.."
DOMAIN="$(grep '^NGROK_DOMAIN=' secrets.env 2>/dev/null | cut -d= -f2-)"
[ -z "$DOMAIN" ] && { echo "NGROK_DOMAIN empty in secrets.env"; exit 1; }
exec ngrok http --url="https://$DOMAIN" 8765
