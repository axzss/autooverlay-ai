"""
Strategy configuration model.

A single place for every tunable overlay-strategy parameter. Defaults match
the previously hardcoded values so behavior is unchanged out of the box.

Overrides can be supplied without any code change via the optional
STRATEGY_CONFIG_JSON environment variable containing a JSON object of
field overrides. Malformed JSON or unknown/invalid fields are ignored
gracefully.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, asdict, fields


@dataclass
class StrategyConfig:
    # Exit rules
    take_profit_pct: float = 0.60        # close when >= 60% of premium captured
    stop_loss_mult: float = 2.0          # stop at loss >= 2x initial premium
    roll_delta: float = 0.40             # roll when |delta| > 0.40
    roll_min_dte: int = 7                # roll when DTE < 7

    # Entry screening bands
    delta_min: float = 0.15
    delta_max: float = 0.35
    dte_min: int = 7
    dte_max: int = 45

    # Portfolio guards
    max_concentration_pct: float = 25.0  # max % of portfolio per ticker
    min_cash_reserve_pct: float = 10.0   # min % cash remaining after collateral
    # Council §6 correlation rule: tech complex (AAPL/MSFT/NVDA/QQQ) combined
    # exposure cap as % of deployed overlay capital.
    max_sector_concentration_pct: float = 40.0
    sector_cap_group: tuple = ("AAPL", "MSFT", "NVDA", "QQQ")

    # Kill-switch thresholds (agent halt conditions)
    kill_max_drawdown_pct: float = 5.0           # peak-to-current drawdown that halts
    kill_max_single_day_loss_pct: float = 2.0    # worst one-day loss that halts
    kill_consecutive_stop_losses: int = 3        # consecutive stop-loss exits before halt

    # Overlay drawdown mode
    overlay_only_drawdown: bool = True           # drawdown from overlay positions only when True

    # ------------------------------------------------------------------ #
    # Validation                                                          #
    # ------------------------------------------------------------------ #
    def validate(self) -> list[str]:
        """Return a list of human-readable validation errors (empty = valid)."""
        errors: list[str] = []

        def _check(name: str, *, low=None, high=None, positive=False):
            val = getattr(self, name)
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                errors.append(f"{name} must be numeric")
                return
            # Security: reject NaN / +/-Infinity — comparisons with NaN are all
            # False, so an unfixed _check would silently accept poisoned values.
            if not math.isfinite(val):
                errors.append(f"{name} must be finite")
                return
            if positive and val <= 0:
                errors.append(f"{name} must be > 0")
            if low is not None and val <= low:
                errors.append(f"{name} must be > {low}")
            if high is not None and val >= high:
                errors.append(f"{name} must be < {high}")

        _check("take_profit_pct", low=0.0, high=1.0)
        _check("stop_loss_mult", low=0.0, high=1000.0)
        _check("roll_delta", low=0.0, high=1.0)
        _check("delta_min", low=0.0, high=1.0)
        _check("delta_max", low=0.0, high=1.0)
        _check("dte_min", positive=True)
        _check("dte_max", positive=True)
        _check("max_concentration_pct", low=0.0, high=100.0)
        _check("max_sector_concentration_pct", low=0.0, high=100.0)
        _check("min_cash_reserve_pct", low=0.0, high=100.0)

        if self.delta_min >= self.delta_max:
            errors.append("delta_min must be < delta_max")
        if self.dte_min >= self.dte_max:
            errors.append("dte_min must be < dte_max")
        return errors

    # ------------------------------------------------------------------ #
    # Serialization                                                       #
    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "StrategyConfig":
        """Build a config from a dict, ignoring unknown/mistyped keys."""
        known = {f.name: f.type for f in fields(cls)}
        clean = {}
        for key, value in (data or {}).items():
            if key not in known:
                continue
            if key == "sector_cap_group":
                try:
                    clean[key] = tuple(str(s).upper() for s in value)
                except (TypeError, ValueError):
                    continue
                continue
            try:
                if key in ("roll_min_dte", "dte_min", "dte_max"):
                    clean[key] = int(value)
                else:
                    if isinstance(value, bool):
                        continue
                    num = float(value)
                    # Security: reject non-finite values (NaN/Infinity) coming
                    # from env JSON or API payloads — validate() comparisons
                    # cannot catch them.
                    if not math.isfinite(num):
                        continue
                    clean[key] = num
            except (TypeError, ValueError):
                continue  # ignore bad types gracefully
        return cls(**clean)

    @classmethod
    def from_env(cls, env_var: str = "STRATEGY_CONFIG_JSON") -> "StrategyConfig":
        """Load overrides from an env var holding JSON. Errors are ignored."""
        raw = os.environ.get(env_var)
        if not raw:
            return cls()
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        return cls.from_dict(data)
