"""Monte Carlo portfolio stress simulation — STANDALONE, NOT WIRED IN.

Read this before quoting any number this module produces.

WHAT IT IS
    A stdlib-only Monte Carlo over ACCOUNT EQUITY: geometric Brownian motion with
    Merton jump diffusion, a crude two-state volatility regime, and the real
    ``evaluate_kill_switch`` applied on every simulated day. Useful for asking
    "how often would the kill-switch fire under these dynamics".

WHAT IT IS NOT
    1. Not part of screening. Nothing imports it — ``git grep monte_carlo --
       agent backend`` returns this file and its test. It does not influence any
       directive, and it must not be described as "integrated into strategy
       screening" until it is.
    2. Not a model of options. Equity follows a single price process; there are
       no strikes, deltas, gamma, assignment or per-contract theta. Premium
       enters as a flat ``overlay_yield_pct / 252`` credit. It therefore CANNOT
       evaluate the 60% take-profit / 200% stop-loss asymmetry, whose
       justification is the implied-minus-realised volatility premium — there is
       no implied volatility anywhere in here.
    3. Not calibrated. With defaults it halts ~87% of paths within 30 days
       (~755 single-day-loss breaches per 1000 paths). A live system halting 87%
       of the time would never trade. Either the volatility inputs or the 2%
       daily kill threshold is wrong; this is unresolved and the figure should
       not be presented as a system property.
    4. Not exercising the whole kill-switch. ``consecutive_stop_losses`` is fixed
       at 0 below, so that trigger never fires on any path.

Honest use: a sensitivity tool for the kill-switch thresholds. Dishonest use:
evidence that the strategy parameters are sound.

See ``docs/RISK_EVALUATION.md`` §1C and ``docs/AI-ENGINEER.md`` §1C.
"""


from __future__ import annotations

import math
import random
from typing import Dict, List, Any

try:
    from agent.council.risk_mitigation import evaluate_kill_switch
except ImportError:
    from council.risk_mitigation import evaluate_kill_switch


def _gaussian_random() -> float:
    """Box-Muller transform for standard normal random variable N(0,1)."""
    u1 = max(1e-10, random.random())
    u2 = random.random()
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def simulate_merton_jump_step(
    price: float,
    mu: float,
    sigma: float,
    dt: float,
    jump_lambda: float = 0.05,  # 5% annual probability of a shock jump
    jump_mu: float = -0.05,     # Average -5% drop on jump
    jump_sigma: float = 0.08,    # Jump volatility
) -> float:
    """Simulate next price step using Merton's Jump Diffusion Model."""
    # Standard diffusion component
    z = _gaussian_random()
    diffusion = (mu - 0.5 * sigma ** 2) * dt + sigma * math.sqrt(dt) * z

    # Poisson Jump component
    jump_factor = 0.0
    if random.random() < (jump_lambda * dt):
        jump_z = _gaussian_random()
        jump_factor = jump_mu + jump_sigma * jump_z

    return price * math.exp(diffusion + jump_factor)


def run_monte_carlo_simulation(
    initial_equity: float = 100_000.0,
    days: int = 30,
    num_paths: int = 1_000,
    mu: float = 0.08,                # Annual expected return (8%)
    sigma: float = 0.20,             # Base annual volatility (20%)
    overlay_yield_pct: float = 0.15,    # Annualized option premium yield (15%)
    enable_jumps: bool = True,       # Enable Merton jump diffusion for black swans
    seed: int = 42,
) -> Dict[str, Any]:
    """Execute Monte Carlo simulation across N paths with Merton Jump Diffusion."""
    random.seed(seed)
    dt = 1.0 / 252.0  # Daily step in trading year
    daily_overlay_yield = (overlay_yield_pct * initial_equity) / 252.0

    paths_final_equity: List[float] = []
    paths_max_drawdown: List[float] = []
    kill_switch_triggers = 0
    drawdown_breaches = 0
    daily_loss_breaches = 0

    for _ in range(num_paths):
        equity = initial_equity
        peak_equity = initial_equity
        prev_equity = initial_equity
        max_dd = 0.0
        halted = False

        for day in range(1, days + 1):
            # Dynamic Regime: 10% probability of elevated volatility spike (e.g. VIX > 30)
            current_sigma = sigma * 1.8 if random.random() < 0.10 else sigma

            # Price step using Jump Diffusion or standard GBM
            if enable_jumps:
                equity = simulate_merton_jump_step(equity, mu, current_sigma, dt)
            else:
                z = _gaussian_random()
                equity = equity * math.exp((mu - 0.5 * current_sigma ** 2) * dt + current_sigma * math.sqrt(dt) * z)

            # Add daily option premium income (Theta decay capture) if active
            if not halted:
                equity += daily_overlay_yield

            # Track peak equity and drawdown
            if equity > peak_equity:
                peak_equity = equity

            dd = (equity / peak_equity - 1.0) * 100.0
            if dd < max_dd:
                max_dd = dd

            # Evaluate the real kill-switch on this simulated day.
            # NOTE: consecutive_stop_losses is fixed at 0, so that trigger is
            # never exercised here. The simulation has no per-contract exits, so
            # there is nothing to derive a stop-loss run from — a limitation, not
            # a choice. See the module docstring.
            state = {
                "equity": equity,
                "peak_equity": peak_equity,
                "prev_equity": prev_equity,
                "consecutive_stop_losses": 0,
            }

            res = evaluate_kill_switch(state)
            if res["halted"]:
                halted = True
                kill_switch_triggers += 1
                for r in res["reasons"]:
                    if "drawdown" in r:
                        drawdown_breaches += 1
                    if "single-day" in r:
                        daily_loss_breaches += 1
                break  # Trading halted for this path

            prev_equity = equity

        paths_final_equity.append(equity)
        paths_max_drawdown.append(max_dd)

    # Compute Statistics
    paths_final_equity.sort()
    paths_max_drawdown.sort()

    mean_final = sum(paths_final_equity) / num_paths
    var5 = paths_final_equity[int(num_paths * 0.05)]  # 5th percentile (Value at Risk)
    cvar5 = sum(paths_final_equity[:int(num_paths * 0.05)]) / max(1, int(num_paths * 0.05))

    returns = [(e / initial_equity - 1.0) for e in paths_final_equity]
    avg_return = sum(returns) / num_paths
    std_return = math.sqrt(sum((r - avg_return) ** 2 for r in returns) / num_paths)

    # Risk-Free Rate (4% annual rate scaled to period)
    rf_period = 0.04 * (days / 365.0)
    sharpe_ratio = (avg_return - rf_period) / max(1e-6, std_return)

    # Sortino Ratio (downside deviation only)
    downside_returns = [min(0.0, r - rf_period) ** 2 for r in returns]
    downside_std = math.sqrt(sum(downside_returns) / num_paths)
    sortino_ratio = (avg_return - rf_period) / max(1e-6, downside_std)

    return {
        "num_paths": num_paths,
        "days_simulated": days,
        "initial_equity": initial_equity,
        "mean_final_equity": round(mean_final, 2),
        "median_final_equity": round(paths_final_equity[num_paths // 2], 2),
        "var_95_equity": round(var5, 2),
        "cvar_95_equity": round(cvar5, 2),
        "expected_return_pct": round(avg_return * 100, 2),
        "sharpe_ratio": round(sharpe_ratio, 2),
        "sortino_ratio": round(sortino_ratio, 2),
        "worst_drawdown_pct": round(paths_max_drawdown[0], 2),
        "median_drawdown_pct": round(paths_max_drawdown[num_paths // 2], 2),
        "kill_switch_halt_pct": round((kill_switch_triggers / num_paths) * 100, 2),
        "drawdown_breaches": drawdown_breaches,
        "daily_loss_breaches": daily_loss_breaches,
    }


if __name__ == "__main__":
    import json
    report = run_monte_carlo_simulation(num_paths=1000, days=30)
    print(json.dumps(report, indent=2))
