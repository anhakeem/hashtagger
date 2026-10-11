"""HashtagEngine — fuses LLM semantic extraction with trend data.

Ranking: score = 0.6 * trend + 0.3 * llm_relevance + 0.1 * (1 - competition_penalty)
Degrade: if all trend providers fail, return LLM-only hashtags (trending=false).

Review fixes (deleg_6490a216 follow-up):
  #1  the post text is NEVER sent to trend providers (privacy)
  #3  seed terms are derived only from validated LLM tags (bounded upstream)
  #5  `trending` requires a meaningful trend score, not mere presence
  #9  LLM-only tags get no competition bonus and are not labelled "low"
  #14 sort tie-breaks toward lower competition
  #15 one malformed LLM entry is dropped, not fatal to the whole result
  #16 an invalid competition value from a provider degrades safely
  #17 `include_trends` is honoured
  #20/#23 tag validation and NaN guards
  #26 the engine depends on a Protocol, not the concrete TrendAggregator
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Protocol

from hashtagger.models import (
    COMPETITION_LEVELS,
    PLATFORM_DEFAULTS,
    GenerateResponse,
    HashtagResult,
)
from hashtagger.trends.base import TrendPoint

log = logging.getLogger(__name__)

_COMPETITION_PENALTY = {"low": 0.0, "medium": 0.5, "high": 1.0}
_TRENDING_THRESHOLD = 0.05  # a point must clear this to count as trending (#5)
_MAX_SEED_TERMS = 15  # architecture §7: the prompt asks for 8-15 tags


class LLMClient(Protocol):
    """Minimal LLM interface the engine depends on."""

    def complete(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.3
    ) -> str: ...


class TrendSource(Protocol):
    """Anything that can return trend points for (platform, seed_terms) (#26)."""

    def fetch(self, platform: str, seed_terms: list[str]) -> list[TrendPoint]: ...


_SYSTEM_PROMPT = (
    "You are a hashtag extraction engine. Extract 8-15 semantic topic signals "
    "from the post. Never invent brand names. Return strict JSON only: "
    '{"hashtags": [{"tag": "#example", "relevance": 0.9}]}. Relevance is 0..1.'
)


def _rank_score(trend: float, relevance: float, competition: str) -> float:
    """0.6*trend + 0.3*llm_relevance + 0.1*(1 - competition_penalty)."""
    comp_penalty = _COMPETITION_PENALTY.get(competition, 1.0)
    return 0.6 * trend + 0.3 * relevance + 0.1 * (1.0 - comp_penalty)


def _safe_competition(value: str) -> str:
    """Coerce an untrusted competition value to a known level (#16)."""
    return value if value in COMPETITION_LEVELS else "high"


class HashtagEngine:
    """Generates ranked hashtags by fusing LLM output with trend data."""

    def __init__(
        self,
        aggregator: TrendSource,
        llm_client: LLMClient,
        model: str = "gpt-4o-mini",
    ) -> None:
        self._aggregator = aggregator
        self._llm = llm_client
        self._model = model

    def generate(
        self,
        text: str,
        platform: str,
        max_tags: int | None = None,
        tone: str | None = None,
        include_trends: bool = True,
    ) -> GenerateResponse:
        """Generate hashtags for a post. Never raises on trend failure."""
        if max_tags is None or max_tags < 1:
            max_tags = PLATFORM_DEFAULTS.get(platform, 5)
        max_tags = min(max_tags, 30)

        # 1. Extract semantic signals from the LLM.
        user_prompt = f"Post:\n<<<\n{text}\n>>>"
        if tone:
            user_prompt += f"\nTone: {tone[:100]}"
        try:
            raw = self._llm.complete(_SYSTEM_PROMPT, user_prompt, temperature=0.3)
            llm_tags = self._parse_llm_response(raw)
        except Exception as exc:
            log.warning("LLM call failed: %s", exc)
            llm_tags = []

        # 2. Fetch trend data. Seed terms come ONLY from validated LLM tags —
        #    never from the raw post text (#1). With no tags there is nothing
        #    to seed with, so skip the trend lookup entirely.
        seed_terms = [t["tag"].lstrip("#") for t in llm_tags][:_MAX_SEED_TERMS]
        trend_points: list[TrendPoint] = []
        if include_trends and seed_terms:
            try:
                trend_points = self._aggregator.fetch(platform, seed_terms)
            except Exception as exc:
                log.warning("trend aggregation failed: %s", exc)
                trend_points = []
        trend_map = {pt.hashtag.lower(): pt for pt in trend_points}

        # 3. Fuse and rank.
        results: list[HashtagResult] = []
        for tag_info in llm_tags:
            tag = tag_info["tag"]
            relevance = tag_info["relevance"]
            tp = trend_map.get(tag.lower())
            if tp is not None and tp.score > 0:
                competition = _safe_competition(tp.competition)
                score = _rank_score(tp.score, relevance, competition)
                results.append(
                    HashtagResult(
                        tag=tag,
                        score=round(min(1.0, max(0.0, score)), 6),
                        volume=tp.volume,
                        competition=competition,
                        trending=tp.score >= _TRENDING_THRESHOLD,
                        source="trend",
                    )
                )
            else:
                # LLM-only: no trend evidence, so no competition bonus (#9).
                score = _rank_score(0.0, relevance, "high")
                results.append(
                    HashtagResult(
                        tag=tag,
                        score=round(min(1.0, max(0.0, score)), 6),
                        competition="high",
                        trending=False,
                        source="llm",
                    )
                )

        # 4. Sort by score desc; tie-break toward lower competition (#14).
        results.sort(
            key=lambda h: (-h.score, _COMPETITION_PENALTY.get(h.competition, 1.0))
        )
        results = results[:max_tags]

        return GenerateResponse(
            hashtags=results,
            platform=platform,
            max_tags=max_tags,
            generation_id=str(uuid.uuid4()),
            model=self._model,
        )

    @staticmethod
    def _parse_llm_response(raw: str) -> list[dict]:
        """Parse and validate LLM JSON. Bad entries are dropped, not fatal (#15)."""
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
        if not isinstance(data, dict):
            return []
        tags = data.get("hashtags")
        if not isinstance(tags, list):
            return []
        valid: list[dict] = []
        for t in tags:
            if not isinstance(t, dict):
                continue
            tag = t.get("tag")
            if not isinstance(tag, str):
                continue
            tag = tag.strip()
            # Reject bare "#", whitespace, multi-token, or over-long tags (#20).
            if not tag.startswith("#") or len(tag) < 2 or len(tag) > 100:
                continue
            if any(ch.isspace() for ch in tag):
                continue
            try:
                relevance = float(t.get("relevance", 0.5))
            except (TypeError, ValueError):
                continue  # drop just this entry (#15)
            if relevance != relevance:  # NaN guard (#23)
                continue
            relevance = max(0.0, min(1.0, relevance))
            valid.append({"tag": tag, "relevance": relevance})
        return valid
