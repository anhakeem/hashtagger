"""TrendAggregator — fans out to providers, normalizes, merges, caches.

Provider failure is non-fatal: a failing provider is skipped, and if all
fail the aggregator returns an empty list (the engine degrades to LLM-only).

Review fixes (deleg_6490a216 follow-up):
  #3  seed terms are capped and deduped so a post can't fan out unbounded calls
  #4  a total-failure result is NOT cached, so recovery isn't hidden for the TTL
  #7  the cache is bounded (LRU eviction) — no unbounded growth / memory leak
  #8  the cache key is normalized (lowercased, deduped, sorted) so it actually hits
"""
from __future__ import annotations

import logging
import time
from collections import OrderedDict

from hashtagger.trends.base import TrendPoint, TrendProvider

log = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 4 * 60 * 60  # 4h, matching the best competitor
DEFAULT_MAX_SEED_TERMS = 15  # architecture §7: prompt asks for 8-15 tags
DEFAULT_MAX_CACHE_SIZE = 2048  # bounded; per-(platform, seed-set) keys


def _normalize_seed_terms(seed_terms: list[str], cap: int) -> list[str]:
    """Lowercase, strip, drop blanks/#, dedupe (order-preserving), then cap.

    This bounds the number of outbound provider calls one post can trigger (#3)
    and makes the cache key stable (#8).
    """
    seen: set[str] = set()
    out: list[str] = []
    for raw in seed_terms:
        term = (raw or "").strip().lstrip("#").strip().lower()
        if not term or term in seen:
            continue
        seen.add(term)
        out.append(term)
        if len(out) >= cap:
            break
    return out


class TrendAggregator:
    """Merges trend points from multiple providers with TTL caching."""

    def __init__(
        self,
        providers: list[TrendProvider],
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        max_seed_terms: int = DEFAULT_MAX_SEED_TERMS,
        max_cache_size: int = DEFAULT_MAX_CACHE_SIZE,
    ) -> None:
        self._providers = list(providers)
        self._ttl = ttl_seconds
        self._max_seed_terms = max_seed_terms
        self._max_cache_size = max_cache_size
        # LRU cache: key -> (timestamp, points). OrderedDict for eviction order.
        self._cache: OrderedDict[tuple[str, tuple[str, ...]], tuple[float, list[TrendPoint]]] = (
            OrderedDict()
        )

    @property
    def cache_size(self) -> int:
        return len(self._cache)

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
        self._cache.move_to_end(key)  # LRU touch
        return points

    def _cache_put(
        self, key: tuple[str, tuple[str, ...]], points: list[TrendPoint]
    ) -> None:
        if self._ttl <= 0:
            return
        self._cache[key] = (time.monotonic(), points)
        self._cache.move_to_end(key)
        # Evict oldest until within bound (#7).
        while len(self._cache) > self._max_cache_size:
            self._cache.popitem(last=False)

    def fetch(self, platform: str, seed_terms: list[str]) -> list[TrendPoint]:
        """Fetch trends from all supporting providers, merge, and cache.

        Returns a fresh list each call so callers can't mutate the cache.
        """
        normalized = _normalize_seed_terms(seed_terms, self._max_seed_terms)
        cache_key = (platform, tuple(sorted(normalized)))
        cached = self._cache_get(cache_key)
        if cached is not None:
            return list(cached)

        merged: dict[str, TrendPoint] = {}
        any_success = False
        for provider in self._providers:
            if platform not in provider.platforms:
                continue
            try:
                points = provider.fetch(platform, normalized)
            except Exception as exc:
                log.warning("provider %s failed: %s", provider.id, exc)
                continue
            any_success = True
            for pt in points:
                existing = merged.get(pt.hashtag)
                if existing is None or pt.score > existing.score:
                    merged[pt.hashtag] = pt

        result = sorted(merged.values(), key=lambda p: p.score, reverse=True)
        # #4: never cache a total failure — otherwise a transient outage is
        # served as "no trends" for the whole TTL after upstream recovers.
        if any_success:
            self._cache_put(cache_key, result)
        return result
