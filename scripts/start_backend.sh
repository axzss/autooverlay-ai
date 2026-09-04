#!/bin/bash
# AutoOverlay AI backend starter with proper env vars
export BOT_EXECUTE_ORDERS=true
export BOT_AUTONOMOUS_ENABLED=true
export BOT_ENFORCE_MARKET_HOURS=true
export ALPACA_PAPER_MODE=true

cd /root/autooverlay-ai/backend
exec /root/autooverlay-ai/backend/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >> /tmp/backend.log 2>&1