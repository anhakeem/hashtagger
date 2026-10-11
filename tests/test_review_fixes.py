"""Regression tests for the Claude-review fixes (deleg_6490a216 follow-up).

Covers:
  #3  no cap on outbound requests per post (cap + dedupe seed terms)
  #4  provider FAILURE must not be cached for the full TTL
  #7  cache must be bounded (no unbounded growth)
  #8  cache key must be normalized so near-identical requests hit
"""
from __future__ import annotations

from hashtagger.trends.aggregator import TrendAggregator
from hashtagger.trends.base import TrendPoint


class FakeProvider:
    def __init__(self, pid: str, platforms: set[str], points, fail: bool = False):
        self.id = pid
        self.platforms = platforms
        self._points = points
        self._fail = fail
        self.calls: list[tuple[str, list[str]]] = []

    def fetch(self, platform: str, seed_terms: list[str]) -> list[TrendPoint]:
        self.calls.append((platform, list(seed_terms)))
        if self._fail:
            raise RuntimeError("upstream down")
        return list(self._points)

    def health(self) -> bool:
        return not self._fail


# ---- #3: seed terms are capped and deduped --------------------------------

def test_fetch_caps_seed_terms():
    """A post that produces 300 tags must not cause 300 provider queries."""
    p = FakeProvider("p1", {"mastodon"}, [TrendPoint("#ai", 0.9)])
    agg = TrendAggregator([p], ttl_seconds=0)
    agg.fetch("mastodon", [f"term{i}" for i in range(300)])
    assert len(p.calls) == 1
    _, seeds = p.calls[0]
    assert len(seeds) <= 15, f"expected <=15 seeds, got {len(seeds)}"


def test_fetch_dedupes_seed_terms_case_insensitively():
    p = FakeProvider("p1", {"mastodon"}, [TrendPoint("#ai", 0.9)])
    agg = TrendAggregator([p], ttl_seconds=0)
    agg.fetch("mastodon", ["ai", "AI", "Ai", "ai"])
    _, seeds = p.calls[0]
    assert seeds == ["ai"], f"expected deduped ['ai'], got {seeds}"


def test_fetch_ignores_blank_seed_terms():
    p = FakeProvider("p1", {"mastodon"}, [TrendPoint("#ai", 0.9)])
    agg = TrendAggregator([p], ttl_seconds=0)
    agg.fetch("mastodon", ["ai", "  ", "", "  #ai  "])
    _, seeds = p.calls[0]
    assert seeds == ["ai"], f"expected ['ai'], got {seeds}"


# ---- #4: failures are NOT cached ------------------------------------------

def test_provider_failure_is_not_cached():
    """After an outage the next call must retry, not serve a cached empty result."""
    failing = FakeProvider("p1", {"mastodon"}, [], fail=True)
    agg = TrendAggregator([failing], ttl_seconds=3600)
    first = agg.fetch("mastodon", ["ai"])
    assert first == []
    failing._fail = False
    failing._points = [TrendPoint("#ai", 0.9)]
    second = agg.fetch("mastodon", ["ai"])
    assert len(failing.calls) == 2, "failure must not be cached"
    assert second and second[0].hashtag == "#ai"


# ---- #7: cache is bounded --------------------------------------------------

def test_cache_is_bounded():
    p = FakeProvider("p1", {"mastodon"}, [TrendPoint("#ai", 0.9)])
    agg = TrendAggregator([p], ttl_seconds=3600, max_cache_size=10)
    for i in range(100):
        agg.fetch("mastodon", [f"term{i}"])
    assert agg.cache_size <= 10, f"cache grew to {agg.cache_size}"


# ---- #8: normalized cache key gives real hits -----------------------------

def test_cache_hits_on_normalized_key():
    """Same logical request (case/order/dup differences) must hit the cache."""
    p = FakeProvider("p1", {"mastodon"}, [TrendPoint("#ai", 0.9)])
    agg = TrendAggregator([p], ttl_seconds=3600)
    agg.fetch("mastodon", ["ai", "ml"])
    agg.fetch("mastodon", ["ML", "ai", "ai"])  # same set, normalized
    assert len(p.calls) == 1, f"expected 1 provider call, got {len(p.calls)}"
