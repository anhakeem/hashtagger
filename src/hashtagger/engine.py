"""HashtagEngine — fuses LLM semantic extraction with trend data.

Ranking: score = 0.6 * trend + 0.3 * llm_relevance + 0.1 * (1 - competition_penalty)
Degrade: if all trend providers fail, return LLM-only hashtags (trending=false).
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Protocol

from hashtagger.models import PLATFORM_DEFAULTS, GenerateResponse, HashtagResult
from hashtagger.trends.aggregator import TrendAggregator
from hashtagger.trends.base import TrendPoint

log = logging.getLogger(__name__)

_COMPETITION_PENALTY = {"low": 0.0, "medium": 0.5, "high": 1.0}


class LLMClient(Protocol):
    """Minimal LLM interface the engine depends on."""

    def complete(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.3
    ) -> str:
        ...


_SYSTEM_PROMPT = """You are a hashtag extraction engine. Extract 8-15 semantic topic signals from the post. Never invent brand names. Return strict JSON only: {"hashtags": [{"tag": "#example", "relevance": 0.9}]}. Relevance is 0..1."""


def _rank_score(trend: float, relevance: float, competition: str) -> float:
    """0.6*trend + 0.3*llm_relevance + 0.1*(1 - competition_penalty)."""
    comp_penalty = _COMPETITION_PENALTY.get(competition, 1.0)
    return 0.6 * trend + 0.3 * relevance + 0.1 * (1.0 - comp_penalty)


class HashtagEngine:
    """Generates ranked hashtags by fusing LLM output with trend data."""

    def __init__(
        self,
        aggregator: TrendAggregator,
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
    ) -> GenerateResponse:
        """Generate hashtags for a post. Never raises on trend failure."""
        if max_tags is None:
            max_tags = PLATFORM_DEFAULTS.get(platform, 5)

        # 1. Extract semantic signals from LLM
        user_prompt = f"Post: {text}"
        if tone:
            user_prompt += f"\nTone: {tone}"
        try:
            raw = self._llm.complete(_SYSTEM_PROMPT, user_prompt, temperature=0.3)
            llm_tags = self._parse_llm_response(raw)
        except Exception as exc:
            log.warning("LLM call failed: %s", exc)
            llm_tags = []

        # 2. Fetch trend data (graceful: empty list on total failure)
        seed_terms = [t["tag"].lstrip("#") for t in llm_tags] or [text]
        try:
            trend_points = self._aggregator.fetch(platform, seed_terms)
        except Exception as exc:
            log.warning("trend aggregation failed: %s", exc)
            trend_points = []
        trend_map = {pt.hashtag.lower(): pt for pt in trend_points}

        # 3. Fuse and rank
        results: list[HashtagResult] = []
        for tag_info in llm_tags:
            tag = tag_info["tag"]
            relevance = float(tag_info.get("relevance", 0.5))
            tp = trend_map.get(tag.lower())
            if tp is not None:
                score = _rank_score(tp.score, relevance, tp.competition)
                results.append(
                    HashtagResult(
                        tag=tag,
                        score=round(score, 6),
                        volume=tp.volume,
                        competition=tp.competition,
                        trending=True,
                        source="trend",
                    )
                )
            else:
                # LLM-only: no trend data, neutral competition
                score = _rank_score(0.0, relevance, "low")
                results.append(
                    HashtagResult(
                        tag=tag,
                        score=round(score, 6),
                        trending=False,
                        source="llm",
                    )
                )

        # 4. Sort by score desc, clip to max_tags
        results.sort(key=lambda h: h.score, reverse=True)
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
        """Parse and validate LLM JSON output. Returns list of {tag, relevance}."""
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
        if not isinstance(data, dict):
            return []
        tags = data.get("hashtags")
        if not isinstance(tags, list):
            return []
        valid = []
        for t in tags:
            if not isinstance(t, dict):
                continue
            tag = t.get("tag")
            if not isinstance(tag, str) or not tag.startswith("#"):
                continue
            relevance = float(t.get("relevance", 0.5))
            relevance = max(0.0, min(1.0, relevance))
            valid.append({"tag": tag, "relevance": relevance})
        return valid
