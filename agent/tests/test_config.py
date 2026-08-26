"""Tests for StrategyConfig parsing, env overrides and validation."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent.config import StrategyConfig  # noqa: E402


class TestDefaults:
    def test_defaults_match_hardcoded_values(self):
        cfg = StrategyConfig()
        assert cfg.take_profit_pct == 0.60
        assert cfg.stop_loss_mult == 2.0
        assert cfg.roll_delta == 0.40
        assert cfg.roll_min_dte == 7
        assert cfg.delta_min == 0.15
        assert cfg.delta_max == 0.35
        assert cfg.dte_min == 7
        assert cfg.dte_max == 45
        assert cfg.max_concentration_pct == 25.0
        assert cfg.min_cash_reserve_pct == 10.0

    def test_defaults_validate_clean(self):
        assert StrategyConfig().validate() == []


class TestFromDict:
    def test_overrides_applied(self):
        cfg = StrategyConfig.from_dict({"take_profit_pct": 0.5, "dte_max": 60})
        assert cfg.take_profit_pct == 0.5
        assert cfg.dte_max == 60
        assert cfg.stop_loss_mult == 2.0  # untouched

    def test_unknown_keys_ignored(self):
        cfg = StrategyConfig.from_dict({"bogus_key": 123, "stop_loss_mult": 3})
        assert not hasattr(cfg, "bogus_key")
        assert cfg.stop_loss_mult == 3

    def test_bad_types_ignored(self):
        cfg = StrategyConfig.from_dict({"stop_loss_mult": "abc", "dte_min": None})
        assert cfg.stop_loss_mult == 2.0
        assert cfg.dte_min == 7


class TestFromEnv:
    def test_env_override(self, monkeypatch):
        monkeypatch.setenv(
            "STRATEGY_CONFIG_JSON",
            json.dumps({"take_profit_pct": 0.75, "delta_min": 0.10}))
        cfg = StrategyConfig.from_env()
        assert cfg.take_profit_pct == 0.75
        assert cfg.delta_min == 0.10

    def test_malformed_json_ignored_gracefully(self, monkeypatch):
        monkeypatch.setenv("STRATEGY_CONFIG_JSON", "{not valid json")
        assert StrategyConfig.from_env() == StrategyConfig()

    def test_non_object_json_ignored(self, monkeypatch):
        monkeypatch.setenv("STRATEGY_CONFIG_JSON", "[1, 2, 3]")
        assert StrategyConfig.from_env() == StrategyConfig()

    def test_unset_env_gives_defaults(self, monkeypatch):
        monkeypatch.delenv("STRATEGY_CONFIG_JSON", raising=False)
        assert StrategyConfig.from_env() == StrategyConfig()


class TestValidation:
    @pytest.mark.parametrize("field,value", [
        ("take_profit_pct", 0.0),
        ("take_profit_pct", 1.0),
        ("roll_delta", -0.1),
        ("max_concentration_pct", 150.0),
        ("min_cash_reserve_pct", -5),
        ("delta_max", 0.0),
        ("stop_loss_mult", 0),
    ])
    def test_out_of_range_rejected(self, field, value):
        kwargs = {field: value}
        cfg = StrategyConfig(**kwargs)
        errors = cfg.validate()
        assert any(field in e for e in errors), f"{field}={value} should be invalid"

    def test_band_crossing_rejected(self):
        assert any("delta" in e for e in StrategyConfig(delta_min=0.4, delta_max=0.2).validate())
        assert any("dte" in e for e in StrategyConfig(dte_min=30, dte_max=10).validate())
