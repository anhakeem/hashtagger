"""TwitterAPI.io trend provider — production X/Twitter source.

Per the research (results/hashtag-data-sources.md), TwitterAPI.io is the best
cost/value source for X data: $0.15/1K tweets, no monthly fee, ~5-min setup.

Docs: https://docs.twitterapi.io — GET /twitter/tweet/advanced_search

Design notes (mirrors the Mastodon/Reddit providers):
  #2  hashtag activity is a cross-platform signal → serves all contract platforms
  #6  seed terms (user-derived) are never written to logs
  #12 a tag seen in several tweets/terms is counted once (max, not sum)
  #21 the injected httpx client is actually used
"""
from __future__ import annotations

import logging
import math
import os
import re

import httpx

from hashtagger.models import ALL_PLATFORMS
from hashtagger.trends.base import TrendPoint

log = logging.getLogger(__name__)

_API_BASE = "https://api.twitterapi.io"
_HASHTAG_RE = re.compile(r"#([A-Za-z][A-Za-z0-9_]{1,49})")
_MAX_TWEETS = 100


def _competition_level(volume: int) -> str:
    if volume >= 50_000:
        return "high"
    if volume >= 5_000:
        return "medium"
    return "low"


class TwitterApiIoProvider:
    """Fetches recent tweets and extracts hashtags weighted by engagement."""

    id = "twitterapi_io"
    platforms = set(ALL_PLATFORMS)

    def __init__(
        self,
        api_key: str | None = None,
        client: httpx.Client | None = None,
        base_url: str = _API_BASE,
        max_tweets: int = _MAX_TWEETS,
    ) -> None:
        self._key = api_key if api_key is not None else os.environ.get("TWITTERAPI_IO_KEY", "")
        if not self._key:
            raise ValueError("TwitterAPI.io requires an API key (TWITTERAPI_IO_KEY)")
        self._base_url = base_url.rstrip("/")
        self._max = max_tweets
        self._client = client or httpx.Client(
            base_url=self._base_url,
            headers={"X-API-Key": self._key},
            timeout=15.0,
        )

    def _search(self, term: str) -> list[dict]:
        resp = self._client.get(
            "/twitter/tweet/advanced_search",
            params={"query": f"#{term}", "queryType": "Latest", "count": self._max},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("tweets", []) if isinstance(data, dict) else []

    def fetch(self, platform: str, seed_terms: list[str]) -> list[TrendPoint]:
        if platform not in self.platforms:
            raise ValueError(f"{self.id} provider does not support platform {platform!r}")

        # tag -> best (max) engagement seen for that tag across tweets+terms (#12)
        engagement: dict[str, int] = {}
        for term in seed_terms:
            try:
                tweets = self._search(term)
            except Exception as exc:
                log.warning("twitterapi.io search failed (%s)", type(exc).__name__)
                continue
            for tw in tweets:
                if not isinstance(tw, dict):
                    continue
                text = tw.get("text", "") or ""
                likes = tw.get("likeCount", 0) or 0
                rts = tw.get("retweetCount", 0) or 0
                score = int(likes) + int(rts)
                for m in _HASHTAG_RE.finditer(text):
                    name = m.group(1).lower()
                    engagement[name] = max(engagement.get(name, 0), score)

        if not engagement:
            return []

        max_eng = max(engagement.values()) or 1
        points: list[TrendPoint] = []
        for name, total in engagement.items():
            norm = math.log1p(total) / math.log1p(max_eng)
            points.append(
                TrendPoint(
                    hashtag=f"#{name}",
                    score=round(norm, 6),
                    volume=total,
                    competition=_competition_level(total),
                )
            )
        return points

    def health(self) -> bool:
        try:
            resp = self._client.get(
                "/twitter/tweet/advanced_search",
                params={"query": "test", "queryType": "Latest", "count": 1},
            )
            return resp.status_code < 400
        except Exception as exc:
            log.debug("twitterapi.io health check failed: %s", type(exc).__name__)
            return False
