"""AutoOverlay AI backend entrypoint."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes.portfolio import router as portfolio_router
from .routes.strategy import router as strategy_router
from .routes.trade import router as trade_router

app = FastAPI(title="AutoOverlay AI Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(portfolio_router, tags=["portfolio"])
app.include_router(trade_router, tags=["trading"])
app.include_router(strategy_router, tags=["strategy"])
# Compatibility aliases for frontend clients that use the conventional /api prefix.
app.include_router(portfolio_router, prefix="/api", tags=["portfolio"])
app.include_router(trade_router, prefix="/api", tags=["trading"])
app.include_router(strategy_router, prefix="/api", tags=["strategy"])


@app.get("/health")
async def health() -> dict:
    from .alpaca_client import is_configured

    return {"status": "ok", "alpaca_configured": is_configured()}
