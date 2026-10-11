"""Tests for billing (subscription upgrade -> pro tier) and the performance loop.

The payment provider is injected, so these tests run with no Stripe key.
"""
from __future__ import annotations

import pytest

from hashtagger.billing import BillingService, PaymentError, StubPaymentProvider
from hashtagger.usage import UsageStore
from hashtagger.performance import PerformanceStore


# ---- BillingService --------------------------------------------------------

def test_checkout_upgrades_account_to_pro(tmp_path):
    usage = UsageStore(db_path=str(tmp_path / "u.db"))
    billing = BillingService(usage=usage, provider=StubPaymentProvider())
    session = billing.create_checkout(account_id="a1", plan="pro")
    assert session["status"] == "paid"
    assert usage.tier("a1") == "pro"


def test_checkout_free_plan_downgrades(tmp_path):
    usage = UsageStore(db_path=str(tmp_path / "u.db"))
    usage.set_tier("a1", "pro")
    billing = BillingService(usage=usage, provider=StubPaymentProvider())
    billing.create_checkout(account_id="a1", plan="free")
    assert usage.tier("a1") == "free"


def test_unknown_plan_rejected(tmp_path):
    usage = UsageStore(db_path=str(tmp_path / "u.db"))
    billing = BillingService(usage=usage, provider=StubPaymentProvider())
    with pytest.raises(ValueError):
        billing.create_checkout(account_id="a1", plan="enterprise")


def test_failed_payment_does_not_upgrade(tmp_path):
    usage = UsageStore(db_path=str(tmp_path / "u.db"))

    class FailingProvider:
        def charge(self, *, account_id, plan, amount_cents):
            raise PaymentError("card declined")

    billing = BillingService(usage=usage, provider=FailingProvider())
    with pytest.raises(PaymentError):
        billing.create_checkout(account_id="a1", plan="pro")
    assert usage.tier("a1") == "free"  # unchanged


def test_webhook_upgrade_is_idempotent(tmp_path):
    """A repeated webhook for the same event must not error or double-apply."""
    usage = UsageStore(db_path=str(tmp_path / "u.db"))
    billing = BillingService(usage=usage, provider=StubPaymentProvider())
    billing.handle_webhook({"type": "subscription.created", "account_id": "a1", "plan": "pro"})
    billing.handle_webhook({"type": "subscription.created", "account_id": "a1", "plan": "pro"})
    assert usage.tier("a1") == "pro"


def test_webhook_cancellation_downgrades(tmp_path):
    usage = UsageStore(db_path=str(tmp_path / "u.db"))
    usage.set_tier("a1", "pro")
    billing = BillingService(usage=usage, provider=StubPaymentProvider())
    billing.handle_webhook({"type": "subscription.cancelled", "account_id": "a1"})
    assert usage.tier("a1") == "free"


# ---- PerformanceStore (v2 feedback loop) -----------------------------------

def test_record_performance(tmp_path):
    store = PerformanceStore(db_path=str(tmp_path / "p.db"))
    store.record(generation_id="g1", platform="instagram", tag="#ai",
                 impressions=1000, engagements=50)
    rows = store.for_generation("g1")
    assert len(rows) == 1
    assert rows[0]["tag"] == "#ai"


def test_tag_stats_aggregate(tmp_path):
    store = PerformanceStore(db_path=str(tmp_path / "p.db"))
    store.record(generation_id="g1", platform="instagram", tag="#ai", impressions=1000, engagements=50)
    store.record(generation_id="g2", platform="instagram", tag="#ai", impressions=500, engagements=25)
    stats = store.tag_stats("#ai")
    assert stats["impressions"] == 1500
    assert stats["engagements"] == 75
    assert stats["engagement_rate"] == pytest.approx(0.05)


def test_top_tags_ranks_by_engagement_rate(tmp_path):
    store = PerformanceStore(db_path=str(tmp_path / "p.db"))
    store.record(generation_id="g1", platform="x", tag="#good", impressions=100, engagements=20)
    store.record(generation_id="g1", platform="x", tag="#bad", impressions=100, engagements=1)
    top = store.top_tags(platform="x", limit=2)
    assert top[0]["tag"] == "#good"
