"""TrendAggregator — fans out to providers, normalizes, merges, caches.

Provider failure is non-fatal: a failing provider is skipped, and if all
fail the aggregator returns an empty list (the engine degrades to LLM-only).
"""
from __future__ import annotations

import logging
import time

from hashtagger.trends.base import TrendPoint, TrendProvider

log = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 4 * 60 * 60  # 4h, matching the best competitor


class TrendAggregator:
    """Merges trend points from multiple providers with TTL caching."""

    def __init__(
        self,
        providers: list[TrendProvider],
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
    ) -> None:
        self._providers = list(providers)
        self._ttl = ttl_seconds
        # cache key: (platform, tuple(sorted(seed_terms))) -> (timestamp, points)
        self._cache: dict[tuple[str, tuple[str, ...]], tuple[float, list[TrendPoint]]] = {}

    def _cache_get(
        self, key: tuple[str, tuple[str, ...]]
    ) -> list[TrendPoint] | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        ts, points = entry
        if self._ttl > 0 and (time.monotonic() - ts) > self._ttl:
            del self._cache[key]
            return None
        return points

    def _cache_put(
        self, key: tuple[str, tuple[str, ...]], points: list[TrendPoint]
    ) -> None:
        if self._ttl > 0:
            self._cache[key] = (time.monotonic(), points)

    def fetch(self, platform: str, seed_terms: list[str]) -> list[TrendPoint]:
        """Fetch trends from all supporting providers, merge, and cache."""
        cache_key = (platform, tuple(sorted(seed_terms)))
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        merged: dict[str, TrendPoint] = {}
        for provider in self._providers:
            if platform not in provider.platforms:
                continue
            try:
                points = provider.fetch(platform, seed_terms)
            except Exception as exc:
                log.warning("provider %s failed: %s", provider.id, exc)
                continue
            for pt in points:
                existing = merged.get(pt.hashtag)
                if existing is None or pt.score > existing.score:
                    merged[pt.hashtag] = pt

        result = sorted(merged.values(), key=lambda p: p.score, reverse=True)
        self._cache_put(cache_key, result)
        return result
