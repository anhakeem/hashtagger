"""Reddit trend provider — free tier (non-commercial), 100 QPM.

Strategy: scan hot posts in relevant subreddits for hashtag-like tokens
in titles. Subreddit names and post titles mirror trending hashtags.

Reddit activity is a platform-agnostic trend signal, so this provider serves
every platform in the API contract (#2).

Review fixes (deleg_6490a216 follow-up):
  #2  serves all contract platforms
  #6  seed terms (user-derived) are never written to logs
  #12 a subreddit fetched for several terms is fetched once (no double-count)
  #21 the injected httpx client is actually used
"""
from __future__ import annotations

import logging
import math
import re

import httpx

from hashtagger.models import ALL_PLATFORMS
from hashtagger.trends.base import TrendPoint

log = logging.getLogger(__name__)

# Require a leading non-word char or start, so "We're #1" doesn't match "1".
_HASHTAG_RE = re.compile(r"(?:^|\W)#([A-Za-z][A-Za-z0-9_]{1,49})")

# Map common seed terms → subreddit names (lowercase keys).
_SUBREDDIT_MAP = {
    "ai": "MachineLearning",
    "machinelearning": "MachineLearning",
    "ml": "MachineLearning",
    "programming": "programming",
    "python": "Python",
    "javascript": "javascript",
    "tech": "technology",
    "technology": "technology",
    "news": "news",
    "science": "science",
    "gaming": "gaming",
    "sports": "sports",
}

DEFAULT_SUBREDDIT = "all"


def _competition_level(volume: int) -> str:
    if volume >= 10_000:
        return "high"
    if volume >= 1_000:
        return "medium"
    return "low"


class RedditProvider:
    """Extracts trending hashtags from Reddit hot post titles."""

    id = "reddit"
    platforms = set(ALL_PLATFORMS)  # platform-agnostic signal (#2)

    def __init__(
        self,
        client: httpx.Client | None = None,
        base_url: str = "https://www.reddit.com",
        max_posts: int = 100,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._max_posts = max_posts
        self._client = client or httpx.Client(
            base_url=self._base_url,
            headers={
                "User-Agent": "hashtagger-dev/0.1 by /u/test",
                "Accept": "application/json",
            },
            timeout=10.0,
        )

    def _subreddit_for(self, term: str) -> str:
        return _SUBREDDIT_MAP.get(term.lower(), DEFAULT_SUBREDDIT)

    def _fetch_hot(self, subreddit: str) -> list[dict]:
        """GET /r/{sub}/hot.json — returns list of post data dicts."""
        resp = self._client.get(
            f"/r/{subreddit}/hot.json",
            params={"limit": self._max_posts, "raw_json": 1},
        )
        resp.raise_for_status()
        return resp.json().get("data", {}).get("children", [])

    def fetch(self, platform: str, seed_terms: list[str]) -> list[TrendPoint]:
        """Extract hashtags from hot posts across relevant subreddits."""
        if platform not in self.platforms:
            raise ValueError(
                f"{self.id} provider does not support platform {platform!r}"
            )

        # #12: resolve each seed term to a subreddit, then fetch each unique
        # subreddit exactly once — otherwise repeated fetches double-count.
        subreddits = {self._subreddit_for(term) for term in seed_terms}

        engagement: dict[str, int] = {}  # name -> ups + comments
        for subreddit in subreddits:
            try:
                posts = self._fetch_hot(subreddit)
            except Exception as exc:
                # #6: log subreddit + error type only — never the seed term.
                log.warning("reddit fetch failed for r/%s (%s)", subreddit, type(exc).__name__)
                continue
            for post_wrapper in posts:
                post = post_wrapper.get("data", {})
                title = post.get("title", "")
                ups = post.get("ups", 0) or 0
                comments = post.get("num_comments", 0) or 0
                score = ups + comments
                for match in _HASHTAG_RE.finditer(title):
                    name = match.group(1).lower()
                    engagement[name] = engagement.get(name, 0) + score

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
        """Check /r/all/hot.json — True on 2xx."""
        try:
            resp = self._client.get("/r/all/hot.json", params={"limit": 1})
            return resp.status_code < 400
        except Exception as exc:
            log.debug("reddit health check failed: %s", type(exc).__name__)
            return False
