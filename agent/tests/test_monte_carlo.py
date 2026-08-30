"""Unit test for Monte Carlo simulation engine."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent.monte_carlo import run_monte_carlo_simulation


def test_monte_carlo_simulation_runs():
    res = run_monte_carlo_simulation(num_paths=100, days=15, seed=123)
    assert res["num_paths"] == 100
    assert res["days_simulated"] == 15
    assert "mean_final_equity" in res
    assert "sortino_ratio" in res
    assert "kill_switch_halt_pct" in res
    assert 0.0 <= res["kill_switch_halt_pct"] <= 100.0
