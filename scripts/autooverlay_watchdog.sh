#!/usr/bin/env bash
# AutoOverlay AI 24/7 watchdog.
#
# Checks the three systemd user units that make the demo publicly reachable,
# restarts anything that is down, resolves the current public tunnel URL and
# prints a short status report. Designed to be run by a Hermes cron job:
# stdout IS the delivered message, so it stays quiet-ish and single-purpose.
#
# Exit code is always 0 — the report itself carries the state.

set -uo pipefail

TUNNEL_LOG="/root/.local/state/cloudflared/tunnel.log"
UNITS=(autooverlay-backend.service autooverlay-frontend.service autooverlay-tunnel.service)

restarted=()

for unit in "${UNITS[@]}"; do
  if ! systemctl --user is-active --quiet "$unit"; then
    systemctl --user restart "$unit" >/dev/null 2>&1
    restarted+=("$unit")
  fi
done

# Give a restarted tunnel time to register and publish its URL.
if [ ${#restarted[@]} -gt 0 ]; then
  sleep 25
fi

backend_health=$(curl -s --max-time 10 http://127.0.0.1:8000/health || echo 'UNREACHABLE')
frontend_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:3000/ || echo '000')

# cloudflared prints the quick-tunnel hostname once at startup; take the last one.
url=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" 2>/dev/null | tail -1)
[ -z "$url" ] && url='(not published yet)'

public_code='000'
if [ "$url" != '(not published yet)' ]; then
  public_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$url/api/health" || echo '000')
fi

echo "AutoOverlay AI status $(date -u '+%Y-%m-%d %H:%M UTC')"
echo "public url : $url"
echo "public /api/health : HTTP $public_code"
echo "backend  : $backend_health"
echo "frontend : HTTP $frontend_code"
for unit in "${UNITS[@]}"; do
  echo "unit $unit : $(systemctl --user is-active "$unit")"
done
if [ ${#restarted[@]} -gt 0 ]; then
  echo "RESTARTED: ${restarted[*]}"
  echo "NOTE: a tunnel restart changes the public URL — reshare the one above."
fi
