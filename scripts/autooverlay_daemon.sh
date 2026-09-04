#!/bin/bash
# AutoOverlay AI autonomous daemon — runs every 5 minutes during market hours
set -uo pipefail

LOG="/root/autooverlay-ai/autooverlay_production.log"
API="http://127.0.0.1:8000"

mkdir -p /root/autooverlay-ai

echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] Daemon started" >> "$LOG"

while true; do
  HOUR=$(date -u +%H)
  MIN=$(date -u +%M)
  # Market hours: 14:00-20:59 UTC = 9:30 AM - 4:59 PM EST
  if [ "$HOUR" -ge 14 ] && [ "$HOUR" -lt 21 ]; then
    echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] Running agent cycle..." >> "$LOG"
    RESP=$(curl -s -X POST "$API/api/agent/run" \
      -H "Content-Type: application/json" \
      -d '{"candidates": ["SPY", "AAPL"]}')
    echo "$RESP" >> "$LOG"
    sleep 300
  else
    echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] Market closed. Sleeping 60s..." >> "$LOG"
    sleep 60
  fi
done
