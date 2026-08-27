"""Security regression tests — red-team findings from the pentest (docs/security_review.md).

Each test maps to a confirmed or verified-safe attack vector.
"""

import math

from fastapi.testclient import TestClient

VALID_CFG = {
    "take_profit_pct": 0.60,
    "stop_loss_mult": 2.0,
    "roll_delta": 0.40,
    "roll_min_dte": 7,
    "delta_min": 0.15,
    "delta_max": 0.35,
    "dte_min": 7,
    "dte_max": 45,
    "max_concentration_pct": 25.0,
    "min_cash_reserve_pct": 10.0,
}


def _cfg(**over):
    return {**VALID_CFG, **over}


class TestStrategyConfigInjection:
    def test_nan_take_profit_rejected(self, client: TestClient):
        import json as _json

        body = _json.dumps(_cfg()).replace("0.6", "NaN")
        r = client.put(
            "/api/strategy/config",
            content=body,
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 422
        # active config must be unchanged
        assert client.get("/api/strategy/config").json()["config"]["take_profit_pct"] == 0.6

    def test_infinite_stop_loss_rejected(self, client: TestClient):
        r = client.put("/api/strategy/config", json=_cfg(stop_loss_mult=1e308))
        assert r.status_code == 422

    def test_raw_nan_body_rejected(self, client: TestClient):
        import json as _json

        body = _json.dumps(_cfg()).replace("0.6", "NaN")
        r = client.put(
            "/api/strategy/config",
            content=body,
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 422

    def test_zero_take_profit_still_rejected(self, client: TestClient):
        assert client.put("/api/strategy/config", json=_cfg(take_profit_pct=0.0)).status_code == 422


class TestTradeAbuse:
    def _post(self, client, **over):
        body = {"symbol": "AAPL", "qty": 1, "side": "buy"}
        body.update(over)
        return client.post("/api/trade", json=body)

    def test_nan_qty_is_422_not_500(self, client: TestClient):
        import json as _json

        r = client.post(
            "/api/trade",
            content='{"symbol":"AAPL","qty":NaN,"side":"buy"}',
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 422

    def test_infinite_limit_price_rejected(self, client: TestClient):
        import json as _json

        r = client.post(
            "/api/trade",
            content='{"symbol":"AAPL","qty":1,"side":"buy","type":"limit","limit_price":Infinity}',
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 422

    def test_oversized_qty_capped(self, client: TestClient):
        assert self._post(client, qty=10**15).status_code == 422

    def test_negative_qty_rejected(self, client: TestClient):
        assert self._post(client, qty=-5).status_code == 422

    def test_huge_client_order_id_rejected(self, client: TestClient):
        assert self._post(client, client_order_id="A" * 10_000).status_code == 422

    def test_option_sql_injection_symbol_rejected(self, client: TestClient):
        r = self._post(client, symbol="AAPL240621C00175000; DROP TABLE users", qty=1)
        assert r.status_code == 422

    def test_option_unicode_homoglyph_rejected(self, client: TestClient):
        r = self._post(client, symbol="ΑΑΡL240621C00175000", qty=1)
        assert r.status_code == 422  # must not pass OCC parse silently

    def test_tif_whitelist_holds_for_options(self, client: TestClient):
        r = self._post(client, symbol="AAPL240621C00175000", time_in_force="day OR 1=1")
        assert r.status_code == 422


class TestScreenAbuse:
    def test_get_top_n_negative_is_422_not_500(self, client: TestClient):
        assert client.get("/api/strategy/screen?top_n=-1").status_code == 422

    def test_get_top_n_huge_is_422_not_500(self, client: TestClient):
        assert client.get("/api/strategy/screen?top_n=1000000000").status_code == 422

    def test_get_negative_open_interest_is_422_not_500(self, client: TestClient):
        assert client.get("/api/strategy/screen?min_open_interest=-5").status_code == 422

    def test_symbols_list_length_capped(self, client: TestClient):
        r = client.post("/api/strategy/screen", json={"symbols": ["AAPL"] * 10_000})
        assert r.status_code == 422

    def test_null_byte_symbol_rejected(self, client: TestClient):
        r = client.post("/api/strategy/screen", json={"symbols": ["AA\x00PL"]})
        assert r.status_code == 422

    def test_full_false_still_works(self, client: TestClient):
        r = client.get("/api/strategy/screen?full=false")
        assert r.status_code == 200
