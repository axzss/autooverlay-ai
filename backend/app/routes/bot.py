"""AI Trading Bot & Autonomous Execution Routes.

Provides REST and MCP-compatible control endpoints for the autonomous trading bot:
- Scheduler status, next run time, execution mode
- Start / stop / configure the 1-hour background scheduler
- Trigger immediate autonomous trading cycles
- Autonomous execution history & audit inspection
- MCP tool descriptors for agent interoperability
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import get_current_user, require_csrf
from ..scheduler import get_bot_scheduler

router = APIRouter()


class BotConfigRequest(BaseModel):
    interval_hours: Optional[float] = Field(default=None, ge=0.1, le=24.0)
    autonomous_execution: Optional[bool] = None


@router.get("/bot/status")
async def bot_status() -> Dict[str, Any]:
    """Get the current autonomous scheduler and trading bot status."""
    scheduler = get_bot_scheduler()
    return scheduler.get_status()


@router.post("/bot/start")
async def bot_start(
    _user: dict = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
) -> Dict[str, Any]:
    """Start or resume the autonomous scheduler."""
    scheduler = get_bot_scheduler()
    scheduler.start()
    return {
        "status": "started",
        "message": f"Autonomous trading bot scheduler active (every {scheduler.interval_hours}h)",
        "bot": scheduler.get_status(),
    }


@router.post("/bot/stop")
async def bot_stop(
    _user: dict = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
) -> Dict[str, Any]:
    """Stop or pause the autonomous scheduler."""
    scheduler = get_bot_scheduler()
    scheduler.stop()
    return {
        "status": "stopped",
        "message": "Autonomous trading bot scheduler stopped",
        "bot": scheduler.get_status(),
    }


@router.post("/bot/config")
async def bot_config(
    req: BotConfigRequest,
    _user: dict = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
) -> Dict[str, Any]:
    """Update autonomous scheduler interval and execution settings."""
    scheduler = get_bot_scheduler()
    if req.interval_hours is not None:
        scheduler.set_interval_hours(req.interval_hours)
    if req.autonomous_execution is not None:
        scheduler.set_autonomous_execution(req.autonomous_execution)

    return {
        "status": "updated",
        "bot": scheduler.get_status(),
    }


@router.post("/bot/cycle")
async def bot_cycle(
    _user: dict = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
) -> Dict[str, Any]:
    """Trigger an immediate autonomous cycle on demand."""
    scheduler = get_bot_scheduler()
    result = scheduler.execute_cycle(manual=True)
    return {
        "status": "completed",
        "result": result,
    }


@router.get("/bot/history")
async def bot_history(
    _user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Retrieve history of autonomous runs and decisions."""
    scheduler = get_bot_scheduler()
    return {
        "count": len(scheduler.get_history()),
        "history": scheduler.get_history(),
    }


@router.get("/bot/mcp/tools")
async def bot_mcp_tools() -> Dict[str, Any]:
    """MCP tool manifest exposing AutoOverlay AI agent capabilities."""
    return {
        "mcp_version": "1.0",
        "server_name": "autooverlay-ai-agent",
        "tools": [
            {
                "name": "run_autonomous_cycle",
                "description": "Execute one complete autonomous options overlay trading cycle with 6-persona council assessment and pre-trade risk gating.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "force_manual": {"type": "boolean", "default": True}
                    }
                }
            },
            {
                "name": "get_bot_status",
                "description": "Retrieve active status, scheduler interval, and last execution metrics of the AI trading bot.",
                "inputSchema": {"type": "object", "properties": {}}
            },
            {
                "name": "get_portfolio_summary",
                "description": "Fetch portfolio cash, equity, open option overlays, and short-option exposure.",
                "inputSchema": {"type": "object", "properties": {}}
            },
            {
                "name": "screen_options_overlay",
                "description": "Screen current portfolio holdings for Covered Calls and Cash-Secured Puts per Investment Council volatility tiers.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "symbols": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of symbols to screen"
                        }
                    }
                }
            },
            {
                "name": "evaluate_risk_gate",
                "description": "Run an order intent through the Pre-Trade Risk Gate without submitting it to the broker.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "OCC option symbol"},
                        "qty": {"type": "number"},
                        "side": {"type": "string", "enum": ["buy", "sell"]},
                        "limit_price": {"type": "number"}
                    },
                    "required": ["symbol", "qty", "side"]
                }
            }
        ]
    }
