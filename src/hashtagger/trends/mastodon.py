"""Mastodon trend provider — free, MVP, 300 req/5min per IP.

API: GET /api/v1/search?q=<term>&type=hashtags returns
     {"tags": [{"name", "history": [{"day": epoch, "uses": "N", "accounts": "N"}]}]}

Mastodon hashtag activity is a platform-agnostic trend signal, so this provider
serves every platform in the API contract (#2) — a tag trending on Mastodon is
useful input when generating hashtags for X, Instagram, etc.

Review fixes (deleg_6490a216 follow-up):
  #2  serves all contract platforms
  #6  seed terms (user-derived) are never written to logs
  #12 a tag returned for multiple seed terms is counted once (max, not sum)
  #21 the injected httpx client is actually used
"""
from __future__ import annotations

import logging
import math

import httpx

from hashtagger.models import ALL_PLATFORMS
from hashtagger.trends.base import TrendPoint

log = logging.getLogger(__name__)

_INSTANCE_URL = "https://mastodon.social"
_HASHTAG_LIMIT = 20


def _competition_level(uses: int, accounts: int) -> str:
    """Classify competition: high = many accounts AND high volume."""
    if accounts >= 5000 or uses >= 1_000_000:
        return "high"
    if accounts >= 500 or uses >= 50_000:
        return "medium"
    return "low"


class MastodonProvider:
    """Fetches trending hashtags from a Mastodon instance."""

    id = "mastodon"
    platforms = set(ALL_PLATFORMS)  # platform-agnostic signal (#2)

    def __init__(
        self,
        client: httpx.Client | None = None,
        instance_url: str = _INSTANCE_URL,
        hashtag_limit: int = _HASHTAG_LIMIT,
    ) -> None:
        self._instance_url = instance_url.rstrip("/")
        self._limit = hashtag_limit
        self._client = client or httpx.Client(
            base_url=self._instance_url,
            headers={"User-Agent": "hashtagger-dev/0.1"},
            timeout=10.0,
        )

    def _search(self, term: str) -> list[dict]:
        """Raw /api/v1/search call, returns list of tag dicts."""
        resp = self._client.get(
            "/api/v1/search",
            params={"q": term, "type": "hashtags", "limit": self._limit},
        )
        resp.raise_for_status()
        return resp.json().get("tags", [])

    def fetch(self, platform: str, seed_terms: list[str]) -> list[TrendPoint]:
        """Query each seed term, merge results, normalize scores to 0..1."""
        if platform not in self.platforms:
            raise ValueError(
                f"{self.id} provider does not support platform {platform!r}"
            )

        # Collect raw tag data: name -> {"uses": int, "accounts": int}
        tag_data: dict[str, dict[str, int]] = {}
        for term in seed_terms:
            try:
                tags = self._search(term)
            except Exception as exc:
                # #6: log the provider + error type only — never the seed term.
                log.warning("mastodon search failed (%s)", type(exc).__name__)
                continue
            for tag in tags:
                name = tag.get("name", "").lower().lstrip("#")
                if not name:
                    continue
                uses = sum(int(h.get("uses", 0)) for h in tag.get("history", []))
                accounts = sum(
                    int(h.get("accounts", 0)) for h in tag.get("history", [])
                )
                existing = tag_data.get(name)
                if existing is None:
                    tag_data[name] = {"uses": uses, "accounts": accounts}
                else:
                    # #12: same tag via different terms — take the max, don't sum.
                    existing["uses"] = max(existing["uses"], uses)
                    existing["accounts"] = max(existing["accounts"], accounts)

        if not tag_data:
            return []

        # Normalize scores: log-scale so mid-volume tags aren't crushed.
        max_uses = max(d["uses"] for d in tag_data.values()) or 1
        points: list[TrendPoint] = []
        for name, data in tag_data.items():
            score = math.log1p(data["uses"]) / math.log1p(max_uses)
            points.append(
                TrendPoint(
                    hashtag=f"#{name}",
                    score=round(score, 6),
                    volume=data["uses"],
                    competition=_competition_level(data["uses"], data["accounts"]),
                )
            )
        return points

    def health(self) -> bool:
        """GET /api/v1/instance — True on 2xx, False on any failure."""
        try:
            resp = self._client.get("/api/v1/instance")
            return resp.status_code < 400
        except Exception as exc:
            log.debug("mastodon health check failed: %s", type(exc).__name__)
            return False
