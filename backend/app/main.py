"""AutoOverlay AI backend entrypoint."""

from __future__ import annotations

import math
import os

from dotenv import load_dotenv

load_dotenv()

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

app = FastAPI(title="AutoOverlay AI Backend", version="0.1.0")


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
