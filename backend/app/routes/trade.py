"""POST /trade — submit an option or equity order to Alpaca paper API.

Every mutating path here passes the pre-trade risk gate first
(``backend/app/risk/``). Before that gate existed this route validated syntax
only and accepted 500 naked short calls on an unheld symbol
(docs/BRIEF-BACKEND-V2.md D4).
"""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from ..auth import get_current_user, require_csrf
from ..alpaca_client import AlpacaClient, parse_occ_symbol
from ..mock_data import mock_orders
from ..risk import TradeIntent, evaluate_trade, fetch_snapshot
from ..store import get_store, idempotency_key

router = APIRouter()

VALID_TIF = {"day", "gtc", "opg", "cls", "ioc", "fok"}


class TradeRequest(BaseModel):
    # Security bounds: qty/limit_price reject NaN & Infinity (allow_inf_nan=False)
    # and absurd magnitudes; symbol / client_order_id are length-capped so a
    # hostile client cannot push multi-MB strings into the order pipeline.
    symbol: str = Field(..., max_length=64, description="Equity ticker or OCC option symbol (e.g. AAPL240621C00175000)")
    qty: float = Field(..., gt=0, allow_inf_nan=False, le=1_000_000_000)
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"] = Field(default="market", alias="type")
    time_in_force: str = Field(default="day", max_length=16)
    limit_price: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False, le=10_000_000)
    extended_hours: bool = False
    client_order_id: Optional[str] = Field(default=None, max_length=128)

    # Provenance: which agent run and directive produced this order. Absent
    # provenance is allowed only with an explicit, audited manual override.
    run_id: Optional[str] = Field(default=None, max_length=128)
    directive_ref: Optional[str] = Field(default=None, max_length=128)
    manual_override: bool = False
    override_reason: Optional[str] = Field(default=None, max_length=500)

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_order(self) -> "TradeRequest":
        import re

        self.symbol = self.symbol.upper().strip()
        # Accept a valid OCC option symbol before applying the shorter equity
        # ticker rule. This keeps option contracts usable for covered calls/CSPs.
        try:
            parse_occ_symbol(self.symbol)
            is_option = True
        except ValueError:
            is_option = False

        # Security: equity symbols must be plain tickers (A-Z, digits, dot,
        # hyphen). Anything else (SQL fragments, shell/unicode junk) is rejected.
        if not is_option and not re.fullmatch(r"[A-Z0-9.\-]{1,15}", self.symbol):
            raise ValueError(f"invalid symbol format: {self.symbol!r}")
        if self.time_in_force.lower() not in VALID_TIF:
            raise ValueError(f"time_in_force must be one of {sorted(VALID_TIF)}")
        if self.order_type == "limit" and self.limit_price is None:
            raise ValueError("limit_price is required when order_type is 'limit'")
        if self.order_type == "market" and self.limit_price is not None:
            raise ValueError("limit_price should only be set for limit orders")
        # Option symbols must be traded with day TIF on Alpaca.
        if is_option:
            if self.time_in_force.lower() != "day":
                raise ValueError("option orders require time_in_force='day'")
            if self.limit_price is not None and not (0.01 <= self.limit_price <= 10000):
                raise ValueError("option limit_price must be between 0.01 and 10000")
        return self


def _intent_from_request(req: TradeRequest) -> TradeIntent:
    return TradeIntent(
        symbol=req.symbol,
        qty=req.qty,
        side=req.side,
        order_type=req.order_type,
        time_in_force=req.time_in_force.lower(),
        limit_price=req.limit_price,
        client_order_id=req.client_order_id,
        run_id=req.run_id,
        directive_ref=req.directive_ref,
        manual_override=req.manual_override,
        override_reason=req.override_reason,
    )


def _quote_price(symbol: str) -> float | None:
    """Current mid for a contract, or None. Never raises.

    A missing quote makes the price-sanity check report itself unevaluated
    rather than silently passing.
    """
    from ..adapters.options import normalize_snapshot
    from ..alpaca_client import is_configured

    if not is_configured():
        return None
    try:
        occ = parse_occ_symbol(symbol)
    except ValueError:
        return None
    try:
        snapshots = AlpacaClient().get_option_snapshots(occ["underlying"])
    except Exception:  # noqa: BLE001 - a quote is best-effort context
        return None
    for snap in snapshots:
        if str(snap.get("symbol", "")).upper() != symbol.upper():
            continue
        quote = normalize_snapshot(symbol, snap)
        return quote.price if quote else None
    return None


@router.post("/trade/preflight")
async def preflight_trade(
    req: TradeRequest,
    _user: dict = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
) -> dict:
    """Run the risk gate without submitting anything.

    Lets the UI disable a submit button and show why, instead of the user
    discovering the rejection after clicking.
    """
    intent = _intent_from_request(req)
    snapshot = fetch_snapshot(config=_active_strategy_config())
    decision = evaluate_trade(
        intent, snapshot, _active_strategy_config(), quote_price=_quote_price(req.symbol)
    )
    return {
        "mode": snapshot.mode,
        "submitted": False,
        "risk": decision.to_dict(),
    }


def _active_strategy_config():
    """The live strategy config, so the gate uses the same thresholds as screening."""
    from .strategy import _active_config

    return _active_config


@router.post("/trade")
async def submit_trade(
    req: TradeRequest,
    _user: dict = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
) -> dict:
    intent = _intent_from_request(req)
    config = _active_strategy_config()
    snapshot = fetch_snapshot(config=config)
    decision = evaluate_trade(
        intent, snapshot, config, quote_price=_quote_price(req.symbol)
    )

    order_payload: dict = {
        "symbol": req.symbol,
        "qty": req.qty,
        "side": req.side,
        "type": req.order_type,
        "time_in_force": req.time_in_force.lower(),
        "extended_hours": req.extended_hours,
    }
    if req.order_type == "limit":
        order_payload["limit_price"] = req.limit_price
    if req.client_order_id:
        order_payload["client_order_id"] = req.client_order_id

    store = get_store()
    key = idempotency_key(order_payload, req.client_order_id)

    if not decision.allowed:
        # Record the rejection before raising: a blocked order is exactly the
        # event an audit trail exists to preserve.
        store.record_intent(
            key=key, payload=order_payload, risk=decision.to_dict(),
            mode=snapshot.mode, status="rejected",
            run_id=req.run_id, directive_ref=req.directive_ref,
        )
        store.record_audit(
            route="POST /api/trade", action="submit_order", outcome="blocked",
            detail={"symbol": req.symbol, "hard_failures": decision.hard_failures},
        )
        # 409, not 422: the request is well-formed and the *state* forbids it.
        # The frontend must be able to tell "you sent nonsense" from "this
        # trade is unsafe right now".
        raise HTTPException(
            status_code=409,
            detail={
                "message": "order blocked by the pre-trade risk gate",
                "risk": decision.to_dict(),
            },
        )

    # Idempotency: an identical payload inside the window returns the ORIGINAL
    # response and does not call the broker again. Returning an error on retry
    # would not be idempotency — a client retrying after a network timeout must
    # be able to converge.
    duplicate = store.find_recent_intent(key)
    if duplicate is not None:
        store.record_audit(
            route="POST /api/trade", action="submit_order", outcome="duplicate",
            detail={"symbol": req.symbol, "idempotency_key": key,
                    "original_intent_id": duplicate.get("id")},
        )
        original = duplicate.get("response") or {}
        return {
            **original,
            "duplicate": True,
            "idempotency_key": key,
            "original_submitted_at": duplicate.get("created_at"),
            "risk": decision.to_dict(),
        }

    from ..alpaca_client import is_configured

    if not is_configured():
        # Graceful fallback: echo the validated order without submitting. The
        # gate still ran — a demo that skips it proves nothing about it.
        response = {
            "mode": "mock",
            "submitted": False,
            "reason": "Alpaca credentials not configured; order validated but not submitted",
            "order": {**order_payload, "status": "simulated"},
        }
        intent_id = store.record_intent(
            key=key, payload=order_payload, risk=decision.to_dict(),
            mode="mock", status="pending",
            run_id=req.run_id, directive_ref=req.directive_ref,
        )
        store.complete_intent(intent_id, status="simulated", response=response)
        store.record_audit(
            route="POST /api/trade", action="submit_order", outcome="simulated",
            detail={"symbol": req.symbol},
        )
        return {**response, "risk": decision.to_dict(), "duplicate": False,
                "idempotency_key": key}

    # Write the intent BEFORE the broker call. Reverse this and a timeout leaves
    # a live order nothing in this system has a record of.
    intent_id = store.record_intent(
        key=key, payload=order_payload, risk=decision.to_dict(),
        mode="live", status="pending",
        run_id=req.run_id, directive_ref=req.directive_ref,
    )

    client = AlpacaClient()
    try:
        result = client.submit_order(order_payload)
    except RuntimeError as exc:
        store.complete_intent(intent_id, status="failed", error=str(exc))
        store.record_audit(
            route="POST /api/trade", action="submit_order", outcome="broker_error",
            detail={"symbol": req.symbol, "error": str(exc)},
        )
        raise HTTPException(status_code=502, detail=str(exc))

    response = {
        "mode": "live",
        "submitted": True,
        "order": {
            "id": result.get("id"),
            "client_order_id": result.get("client_order_id"),
            "symbol": result.get("symbol"),
            "qty": result.get("qty"),
            "side": result.get("side"),
            "type": result.get("type"),
            "time_in_force": result.get("time_in_force"),
            "limit_price": result.get("limit_price"),
            "status": result.get("status"),
            "submitted_at": result.get("submitted_at"),
        },
    }
    store.complete_intent(
        intent_id, status="submitted", response=response,
        broker_order_id=str(result.get("id") or "") or None,
    )
    store.record_audit(
        route="POST /api/trade", action="submit_order", outcome="submitted",
        detail={"symbol": req.symbol, "broker_order_id": result.get("id")},
    )
    return {**response, "risk": decision.to_dict(), "duplicate": False,
            "idempotency_key": key}


@router.get("/trade/ledger")
async def order_ledger(limit: int = 50) -> dict:
    """Every order this backend attempted, blocked or submitted.

    The audit answer to "what did the system do at 14:32?". ``pending`` rows are
    surfaced separately: a pending row means an intent was written, the broker
    call never resolved, and an order may exist that this system does not know
    the outcome of. Reconcile those against `/api/trade/orders` — do not assume.
    """
    store = get_store()
    return {
        "degraded": store.degraded,
        "degraded_reason": store.degraded_reason,
        "schema_version": store.schema_version,
        "pending": store.pending_intents(),
        "intents": store.recent_intents(limit=max(1, min(int(limit), 500))),
    }


@router.get("/trade/audit")
async def audit_trail(limit: int = 50) -> dict:
    store = get_store()
    return {
        "degraded": store.degraded,
        "events": store.recent_audit(limit=max(1, min(int(limit), 500))),
    }


@router.get("/trade/orders")
async def list_orders(status: str = "open") -> dict:
    from ..alpaca_client import is_configured

    if not is_configured():
        return {"mode": "mock", "orders": mock_orders()}
    try:
        orders = AlpacaClient().list_orders(status=status)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"mode": "live", "orders": orders}
