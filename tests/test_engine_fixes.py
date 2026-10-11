"""Regression tests for engine-level review fixes (deleg_6490a216 follow-up).

Covers:
  #1  the post text must NEVER be sent to trend providers (privacy leak)
  #5  `trending` must reflect real trend data, not just "a point exists"
  #16 an invalid competition value from a provider must not 500 the request
  #15 one malformed LLM entry must not discard the whole LLM result
"""
from __future__ import annotations

from hashtagger.engine import HashtagEngine
from hashtagger.trends.base import TrendPoint


class FakeLLM:
    def __init__(self, payload: str):
        self._payload = payload
        self.calls: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self._payload


class RaisingLLM:
    def complete(self, *a, **k):
        raise RuntimeError("llm down")


class SpyAggregator:
    """Records the seed terms it is asked to fetch."""

    def __init__(self, points: list[TrendPoint]):
        self._points = points
        self.calls: list[tuple[str, list[str]]] = []

    def fetch(self, platform: str, seed_terms: list[str]) -> list[TrendPoint]:
        self.calls.append((platform, list(seed_terms)))
        return list(self._points)


LLM_JSON = '{"hashtags": [{"tag": "#ai", "relevance": 0.9}, {"tag": "#ml", "relevance": 0.8}]}'


# ---- #1: post text never leaks to providers -------------------------------

def test_post_text_never_sent_to_providers_when_llm_returns_nothing():
    """If the LLM yields no tags, providers must never receive the post text.

    Skipping the trend lookup entirely is the safe behaviour: there are no
    validated seed terms, so there is nothing legitimate to query with.
    """
    llm = FakeLLM("{}")  # no hashtags
    agg = SpyAggregator([])
    engine = HashtagEngine(aggregator=agg, llm_client=llm)
    engine.generate("my secret private post about X", "mastodon")
    for _platform, seeds in agg.calls:
        assert "my secret private post about X" not in seeds
        assert all("secret" not in s for s in seeds)


def test_post_text_never_sent_when_llm_raises():
    llm = RaisingLLM()
    agg = SpyAggregator([])
    engine = HashtagEngine(aggregator=agg, llm_client=llm)
    engine.generate("confidential roadmap text", "mastodon")
    for _platform, seeds in agg.calls:
        assert "confidential" not in " ".join(seeds)


# ---- #5: trending reflects real data --------------------------------------

def test_trending_false_for_zero_score_point():
    """A matched point with score 0 must not be labelled trending."""
    llm = FakeLLM(LLM_JSON)
    agg = SpyAggregator([TrendPoint("#ai", 0.0), TrendPoint("#ml", 0.9)])
    engine = HashtagEngine(aggregator=agg, llm_client=llm)
    resp = engine.generate("post", "mastodon", max_tags=5)
    by_tag = {h.tag: h for h in resp.hashtags}
    assert by_tag["#ai"].trending is False
    assert by_tag["#ml"].trending is True


# ---- #16: bad competition must not 500 ------------------------------------

def test_invalid_competition_does_not_raise():
    llm = FakeLLM(LLM_JSON)
    agg = SpyAggregator([TrendPoint("#ai", 0.9, competition="extreme")])
    engine = HashtagEngine(aggregator=agg, llm_client=llm)
    resp = engine.generate("post", "mastodon", max_tags=5)
    assert resp.hashtags  # returned normally, no exception


# ---- #15: one bad LLM entry doesn't kill the rest -------------------------

def test_one_bad_llm_entry_is_dropped_not_fatal():
    payload = (
        '{"hashtags": ['
        '{"tag": "#good", "relevance": 0.9},'
        '{"tag": "#bad", "relevance": "high"},'
        '{"tag": "#alsoGood", "relevance": 0.7}'
        "]}"
    )
    llm = FakeLLM(payload)
    agg = SpyAggregator([])
    engine = HashtagEngine(aggregator=agg, llm_client=llm)
    resp = engine.generate("post", "mastodon", max_tags=5)
    tags = {h.tag for h in resp.hashtags}
    assert "#good" in tags and "#alsoGood" in tags
