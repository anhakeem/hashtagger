"""Tests for the freemium usage layer (architecture §3 usage_counters, §4 /usage)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from hashtagger.api.main import create_app
from hashtagger.models import GenerateResponse, HashtagResult
from hashtagger.usage import FREE_DAILY_LIMIT, UsageStore


# ---- UsageStore ------------------------------------------------------------

def test_new_account_defaults_to_free(tmp_path):
    store = UsageStore(db_path=str(tmp_path / "u.db"))
    assert store.tier("a1") == "free"


def test_increment_counts_today(tmp_path):
    store = UsageStore(db_path=str(tmp_path / "u.db"))
    store.increment("a1")
    store.increment("a1")
    assert store.used_today("a1") == 2


def test_free_tier_allows_up_to_limit(tmp_path):
    store = UsageStore(db_path=str(tmp_path / "u.db"))
    for _ in range(FREE_DAILY_LIMIT):
        assert store.can_generate("a1") is True
        store.increment("a1")
    assert store.can_generate("a1") is False


def test_pro_tier_is_unlimited(tmp_path):
    store = UsageStore(db_path=str(tmp_path / "u.db"))
    store.set_tier("a1", "pro")
    for _ in range(FREE_DAILY_LIMIT + 50):
        store.increment("a1")
    assert store.can_generate("a1") is True


def test_accounts_are_isolated(tmp_path):
    store = UsageStore(db_path=str(tmp_path / "u.db"))
    for _ in range(FREE_DAILY_LIMIT):
        store.increment("a1")
    assert store.can_generate("a1") is False
    assert store.can_generate("a2") is True


def test_usage_summary_shape(tmp_path):
    store = UsageStore(db_path=str(tmp_path / "u.db"))
    store.increment("a1")
    s = store.summary("a1")
    assert s["tier"] == "free"
    assert s["used_today"] == 1
    assert s["limit"] == FREE_DAILY_LIMIT


# ---- API enforcement -------------------------------------------------------

class FakeEngine:
    def generate(self, text, platform, max_tags=None, tone=None, include_trends=True):
        return GenerateResponse(
            hashtags=[HashtagResult(tag="#ai", score=0.9, trending=True, source="trend")],
            platform=platform, max_tags=max_tags or 5,
            generation_id="g1", model="fake",
        )


def make_client(store):
    app = create_app(engine_factory=lambda: FakeEngine(),
                     usage_store_factory=lambda: store)
    return TestClient(app)


def test_generate_increments_usage(tmp_path):
    store = UsageStore(db_path=str(tmp_path / "u.db"))
    client = make_client(store)
    r = client.post("/api/v1/generate", json={"text": "hi", "platform": "x", "account_id": "a1"})
    assert r.status_code == 200
    assert store.used_today("a1") == 1


def test_generate_blocks_at_free_limit(tmp_path):
    store = UsageStore(db_path=str(tmp_path / "u.db"))
    for _ in range(FREE_DAILY_LIMIT):
        store.increment("a1")
    client = make_client(store)
    r = client.post("/api/v1/generate", json={"text": "hi", "platform": "x", "account_id": "a1"})
    assert r.status_code == 429
    body = r.json()
    assert body["error"]["code"] == "RATE_LIMITED"
    assert "reset_at" in body["error"]["details"]


def test_generate_pro_tier_not_blocked(tmp_path):
    store = UsageStore(db_path=str(tmp_path / "u.db"))
    store.set_tier("a1", "pro")
    for _ in range(FREE_DAILY_LIMIT + 5):
        store.increment("a1")
    client = make_client(store)
    r = client.post("/api/v1/generate", json={"text": "hi", "platform": "x", "account_id": "a1"})
    assert r.status_code == 200


def test_usage_endpoint(tmp_path):
    store = UsageStore(db_path=str(tmp_path / "u.db"))
    store.increment("a1")
    client = make_client(store)
    r = client.get("/api/v1/usage?account_id=a1")
    assert r.status_code == 200
    body = r.json()
    assert body["tier"] == "free"
    assert body["used_today"] == 1
    assert body["limit"] == FREE_DAILY_LIMIT
