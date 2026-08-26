"""Tests for GET/PUT /strategy/config routes."""

import pytest


@pytest.fixture()
def restore_config():
    """Snapshot and restore the in-process singleton around each test."""
    from backend.app.routes import strategy as strategy_routes
    from agent.config import StrategyConfig

    original = strategy_routes._active_config
    yield strategy_routes
    strategy_routes._active_config = original
    assert StrategyConfig  # keep import meaningful


class TestGetStrategyConfig:
    def test_module_config_honors_environment_overrides(self, client, restore_config, monkeypatch):
        import importlib
        from backend.app.routes import strategy as strategy_routes

        monkeypatch.setenv(
            "STRATEGY_CONFIG_JSON",
            '{"take_profit_pct": 0.75, "delta_min": 0.10}',
        )
        importlib.reload(strategy_routes)

        cfg = client.get("/strategy/config").json()["config"]
        assert cfg["take_profit_pct"] == 0.75
        assert cfg["delta_min"] == 0.10

    def test_get_returns_all_fields(self, client, restore_config):
        resp = client.get("/strategy/config")
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        cfg = body["config"]
        for key in ("take_profit_pct", "stop_loss_mult", "roll_delta",
                    "roll_min_dte", "delta_min", "delta_max", "dte_min",
                    "dte_max", "max_concentration_pct", "min_cash_reserve_pct"):
            assert key in cfg

    def test_defaults(self, client, restore_config):
        cfg = client.get("/strategy/config").json()["config"]
        assert cfg["take_profit_pct"] == 0.60
        assert cfg["stop_loss_mult"] == 2.0


class TestPutStrategyConfig:
    def test_put_updates_singleton(self, client, restore_config):
        payload = {"take_profit_pct": 0.45, "delta_min": 0.10}
        resp = client.put("/strategy/config", json={
            **{k: v for k, v in client.get("/strategy/config").json()["config"].items()},
            **payload,
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        updated = client.get("/strategy/config").json()["config"]
        assert updated["take_profit_pct"] == 0.45
        assert updated["delta_min"] == 0.10

    def test_put_rejects_invalid_range(self, client, restore_config):
        current = client.get("/strategy/config").json()["config"]
        current["take_profit_pct"] = 1.5  # must be strictly between 0 and 1
        resp = client.put("/strategy/config", json=current)
        assert resp.status_code == 422
        assert any("take_profit_pct" in e for e in resp.json()["detail"]["errors"])
        # singleton untouched on rejection
        after = client.get("/strategy/config").json()["config"]
        assert after["take_profit_pct"] == 0.60

    def test_put_rejects_crossed_bands(self, client, restore_config):
        current = client.get("/strategy/config").json()["config"]
        current["dte_min"], current["dte_max"] = 40, 20
        resp = client.put("/strategy/config", json=current)
        assert resp.status_code == 422
