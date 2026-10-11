"""Tests for the billing + performance API endpoints."""
from __future__ import annotations

from fastapi.testclient import TestClient

from hashtagger.api.main import create_app
from hashtagger.billing import BillingService, StubPaymentProvider
from hashtagger.models import GenerateResponse, HashtagResult
from hashtagger.performance import PerformanceStore
from hashtagger.usage import UsageStore


class FakeEngine:
    def generate(self, text, platform, max_tags=None, tone=None, include_trends=True):
        return GenerateResponse(
            hashtags=[HashtagResult(tag="#ai", score=0.9, trending=True)],
            platform=platform, max_tags=max_tags or 5, generation_id="g1", model="fake",
        )


def _client(tmp_path):
    usage = UsageStore(db_path=str(tmp_path / "u.db"))
    perf = PerformanceStore(db_path=str(tmp_path / "p.db"))
    app = create_app(
        engine_factory=lambda: FakeEngine(),
        usage_store_factory=lambda: usage,
        billing_factory=lambda: BillingService(usage=usage, provider=StubPaymentProvider()),
        performance_factory=lambda: perf,
    )
    return TestClient(app), usage


def test_checkout_upgrades_and_usage_reflects_pro(tmp_path):
    client, usage = _client(tmp_path)
    r = client.post("/api/v1/billing/checkout", json={"account_id": "a1", "plan": "pro"})
    assert r.status_code == 200
    assert usage.tier("a1") == "pro"
    u = client.get("/api/v1/usage?account_id=a1")
    assert u.json()["tier"] == "pro"
    assert u.json()["limit"] is None  # unlimited


def test_checkout_unknown_plan_422(tmp_path):
    client, usage = _client(tmp_path)
    r = client.post("/api/v1/billing/checkout", json={"account_id": "a1", "plan": "gold"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_webhook_cancellation_downgrades(tmp_path):
    client, usage = _client(tmp_path)
    usage.set_tier("a1", "pro")
    r = client.post("/api/v1/billing/webhook",
                    json={"type": "subscription.cancelled", "account_id": "a1"})
    assert r.status_code == 200
    assert usage.tier("a1") == "free"


def test_performance_record_and_top(tmp_path):
    client, usage = _client(tmp_path)
    r = client.post("/api/v1/performance", json={
        "generation_id": "g1", "platform": "x", "tag": "#ai",
        "impressions": 1000, "engagements": 80,
    })
    assert r.status_code == 200
    top = client.get("/api/v1/performance/top?platform=x")
    assert top.status_code == 200
    tags = top.json()["tags"]
    assert tags[0]["tag"] == "#ai"
    assert tags[0]["engagement_rate"] == 0.08
