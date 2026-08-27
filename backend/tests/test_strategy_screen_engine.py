"""Tests for DecisionEngine enrichment of /strategy/screen responses."""

from backend.tests.conftest import HAS_APP  # noqa: F401
import pytest

pytestmark = pytest.mark.skipif(
    not HAS_APP, reason="backend.app.main does not expose a FastAPI app yet"
)


class TestScreenEnrichment:
    @pytest.fixture(autouse=True)
    def _no_real_credentials(self, monkeypatch):
        # Tests must never depend on (or hit) real Alpaca credentials.
        for var in ("ALPACA_KEY", "ALPACA_SECRET", "APCA_API_KEY_ID", "APCA_API_SECRET_KEY"):
            monkeypatch.delenv(var, raising=False)

    def test_mock_get_enriched_shape(self, client):
        resp = client.get("/api/strategy/screen")
        assert resp.status_code == 200
        body = resp.json()
        assert body["mode"] == "mock"
        assert body["count"] == len(body["candidates"])
        assert isinstance(body.get("portfolio_context"), dict)
        for cand in body["candidates"]:
            assert isinstance(cand["risk_score"], int)
            assert 0 <= cand["risk_score"] <= 100
            assert cand["action"] in (
                "INITIATE_POSITION", "HOLD_POSITION", "MONITOR_CLOSELY",
            )
            assert isinstance(cand["rationale"], str) and cand["rationale"]
            assert isinstance(cand["reasoning_trace"], list)
            assert all(isinstance(t, str) for t in cand["reasoning_trace"])
        # Backward-compat fields still present on candidates.
        sample = body["candidates"][0]
        for key in ("symbol", "strike_price", "expiration_date",
                    "annualized_return_rate", "recommendation"):
            assert key in sample

    def test_mock_post_enriched(self, client):
        resp = client.post("/api/strategy/screen", json={"top_n": 2})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["candidates"]) <= 2
        assert "risk_score" in body["candidates"][0]
        assert "reasoning_trace" in body["candidates"][0]

    def test_full_false_skips_engine(self, client):
        resp = client.get("/api/strategy/screen?full=false")
        assert resp.status_code == 200
        body = resp.json()
        assert "portfolio_context" not in body
        assert "risk_score" not in body["candidates"][0]

    def test_mock_mode_needs_no_credentials(self, client, monkeypatch):
        # Simulate zero-credential environment: route must stay on mock data.
        monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
        monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)
        resp = client.get("/api/strategy/screen")
        assert resp.status_code == 200
        assert resp.json()["mode"] == "mock"
