"""RED-phase tests: TrendAggregator (fan-out, normalize, merge, TTL cache)."""
import time

import pytest

from hashtagger.trends.aggregator import TrendAggregator
from hashtagger.trends.base import TrendPoint, TrendProvider


class FakeProvider:
    """In-memory provider for testing."""

    def __init__(self, pid: str, platforms: set[str], points: list[TrendPoint], fail: bool = False):
        self.id = pid
        self.platforms = platforms
        self._points = points
        self._fail = fail
        self.calls: list[tuple[str, list[str]]] = []

    def fetch(self, platform: str, seed_terms: list[str]) -> list[TrendPoint]:
        self.calls.append((platform, list(seed_terms)))
        if self._fail:
            raise RuntimeError(f"{self.id} is down")
        return self._points

    def health(self) -> bool:
        return not self._fail


def test_aggregator_fans_out_to_all_providers():
    p1 = FakeProvider("p1", {"mastodon"}, [TrendPoint("#a", 0.5)])
    p2 = FakeProvider("p2", {"mastodon"}, [TrendPoint("#b", 0.7)])
    agg = TrendAggregator(providers=[p1, p2])
    points = agg.fetch("mastodon", ["ai"])
    assert len(p1.calls) == 1
    assert len(p2.calls) == 1
    assert len(points) == 2


def test_aggregator_normalizes_scores():
    """Scores from different providers are merged and capped at 1.0."""
    p1 = FakeProvider("p1", {"mastodon"}, [TrendPoint("#x", 1.0)])
    p2 = FakeProvider("p2", {"mastodon"}, [TrendPoint("#x", 0.8)])
    agg = TrendAggregator(providers=[p1, p2])
    points = agg.fetch("mastodon", ["x"])
    # merge takes max per hashtag
    assert len(points) == 1
    assert points[0].score <= 1.0
    assert points[0].score == pytest.approx(1.0)


def test_aggregator_provider_failure_is_non_fatal():
    """One provider failing must not raise; others still contribute."""
    good = FakeProvider("good", {"mastodon"}, [TrendPoint("#ok", 0.5)])
    bad = FakeProvider("bad", {"mastodon"}, [], fail=True)
    agg = TrendAggregator(providers=[good, bad])
    points = agg.fetch("mastodon", ["test"])
    assert len(points) == 1
    assert points[0].hashtag == "#ok"


def test_aggregator_all_providers_fail_returns_empty():
    """All providers failing → empty list (engine degrades to LLM-only)."""
    p1 = FakeProvider("p1", {"mastodon"}, [], fail=True)
    p2 = FakeProvider("p2", {"mastodon"}, [], fail=True)
    agg = TrendAggregator(providers=[p1, p2])
    assert agg.fetch("mastodon", ["test"]) == []


def test_aggregator_caches_within_ttl():
    """Second call within TTL should hit cache (no new fetch)."""
    pts = [TrendPoint("#cached", 0.9)]
    p = FakeProvider("p1", {"mastodon"}, pts)
    agg = TrendAggregator(providers=[p], ttl_seconds=60)
    r1 = agg.fetch("mastodon", ["cache_test"])
    r2 = agg.fetch("mastodon", ["cache_test"])
    assert len(p.calls) == 1  # second call served from cache
    assert r1 == r2


def test_aggregator_cache_expires_after_ttl():
    """After TTL expires, providers are called again."""
    pts = [TrendPoint("#expired", 0.5)]
    p = FakeProvider("p1", {"mastodon"}, pts)
    agg = TrendAggregator(providers=[p], ttl_seconds=0.01)
    agg.fetch("mastodon", ["exp_test"])
    time.sleep(0.02)
    agg.fetch("mastodon", ["exp_test"])
    assert len(p.calls) == 2


def test_aggregator_cache_bypassed_when_disabled():
    """ttl_seconds=0 means no caching."""
    pts = [TrendPoint("#nocache", 0.3)]
    p = FakeProvider("p1", {"mastodon"}, pts)
    agg = TrendAggregator(providers=[p], ttl_seconds=0)
    agg.fetch("mastodon", ["no_cache"])
    agg.fetch("mastodon", ["no_cache"])
    assert len(p.calls) == 2


def test_aggregator_only_queries_providers_for_platform():
    """Providers not supporting the platform are skipped."""
    p1 = FakeProvider("masto", {"mastodon"}, [TrendPoint("#m", 0.5)])
    p2 = FakeProvider("reddit", {"reddit"}, [TrendPoint("#r", 0.7)])
    agg = TrendAggregator(providers=[p1, p2])
    points = agg.fetch("mastodon", ["x"])
    assert len(p1.calls) == 1
    assert len(p2.calls) == 0
    assert len(points) == 1


def test_aggregator_empty_providers():
    agg = TrendAggregator(providers=[])
    assert agg.fetch("mastodon", ["x"]) == []
