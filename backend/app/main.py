"""AutoOverlay AI backend entrypoint."""

from __future__ import annotations

import math
import os

from dotenv import load_dotenv

load_dotenv()

# Ensure the project root is importable so backend routes can resolve the
# top-level ``agent`` package without relying on external PYTHONPATH.
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from app.logging_config import configure

configure()

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import router as auth_router
from .routes.council import router as council_router
from .routes.agent import router as agent_router
from .routes.portfolio import router as portfolio_router
from .routes.strategy import router as strategy_router
from .routes.trade import router as trade_router
from .routes.bot import router as bot_router
from .scheduler import get_bot_scheduler

app = FastAPI(title="AutoOverlay AI Backend", version="0.1.0")


@app.on_event("startup")
def startup_event():
    # Initializes and starts the 1-hour autonomous scheduler if configured
    get_bot_scheduler()


@app.on_event("shutdown")
def shutdown_event():
    scheduler = get_bot_scheduler()
    scheduler.stop()


def _cors_origins() -> list[str]:
    raw = (os.getenv("CORS_ORIGINS") or "").strip()
    if not raw:
        return ["http://localhost:3000", "http://127.0.0.1:3000"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router, prefix="/api", tags=["auth"])
app.include_router(portfolio_router, prefix="/api", tags=["portfolio"])
app.include_router(trade_router, prefix="/api", tags=["trading"])
app.include_router(strategy_router, prefix="/api", tags=["strategy"])
app.include_router(council_router, prefix="/api", tags=["council"])
app.include_router(agent_router, prefix="/api", tags=["agent"])
app.include_router(bot_router, prefix="/api", tags=["bot"])


def _sanitize(obj):
    """Make error payloads JSON-safe: NaN/Infinity cannot be JSON-encoded and
    used to crash the default RequestValidationError handler into a 500."""
    if isinstance(obj, float) and not math.isfinite(obj):
        return repr(obj)
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return obj


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    try:
        detail = _sanitize(exc.errors())
        return JSONResponse(status_code=422, content={"detail": detail})
    except Exception:
        return JSONResponse(status_code=422, content={"detail": "validation error"})


@app.get("/health")
@app.get("/api/health")
async def health() -> dict:
    from .alpaca_client import is_configured

    return {"status": "ok", "alpaca_configured": is_configured()}
