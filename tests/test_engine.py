"""RED-phase tests: HashtagEngine (LLM + trend fusion, ranking, graceful degrade)."""
import json

import pytest

from hashtagger.engine import HashtagEngine
from hashtagger.models import GenerateResponse, HashtagResult
from hashtagger.trends.base import TrendPoint
from hashtagger.trends.aggregator import TrendAggregator


class FakeLLMClient:
    """Returns a canned response for testing."""

    def __init__(self, response: str):
        self._response = response
        self.calls: list[dict] = []

    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        self.calls.append({"system": system_prompt, "user": user_prompt, "temperature": temperature})
        return self._response


class FakeAggregator:
    """Returns canned trend points or fails."""

    def __init__(self, points: list[TrendPoint] | None = None, fail: bool = False):
        self._points = points or []
        self._fail = fail
        self.calls: list[tuple[str, list[str]]] = []

    def fetch(self, platform: str, seed_terms: list[str]) -> list[TrendPoint]:
        self.calls.append((platform, list(seed_terms)))
        if self._fail:
            raise RuntimeError("all providers down")
        return self._points


def _make_engine(llm_response: str, trend_points: list[TrendPoint] | None = None, fail_trends: bool = False):
    llm = FakeLLMClient(llm_response)
    agg = FakeAggregator(points=trend_points, fail=fail_trends)
    engine = HashtagEngine(aggregator=agg, llm_client=llm, model="test-model")
    return engine, llm, agg


def test_engine_returns_hashtags_for_valid_input():
    llm_resp = '{"hashtags": [{"tag": "#ai", "relevance": 0.9}, {"tag": "#ml", "relevance": 0.7}]}'
    engine, _, _ = _make_engine(llm_resp)
    resp = engine.generate("AI is transforming healthcare", "instagram")
    assert isinstance(resp, GenerateResponse)
    assert len(resp.hashtags) == 2
    assert resp.platform == "instagram"
    assert resp.max_tags == 5
    assert resp.model == "test-model"
    assert resp.generation_id  # non-empty UUID


def test_engine_calls_llm_with_post_text():
    llm_resp = '{"hashtags": [{"tag": "#ai", "relevance": 0.9}]}'
    engine, llm, _ = _make_engine(llm_resp)
    engine.generate("AI is transforming healthcare", "instagram")
    assert len(llm.calls) == 1
    assert "AI is transforming healthcare" in llm.calls[0]["user"]


def test_engine_shapes_output_to_platform_max_tags():
    """Instagram max_tags=5 — LLM returns 8 tags, engine clips to 5."""
    tags = [{"tag": f"#tag{i}", "relevance": 0.9 - i * 0.1} for i in range(8)]
    llm_resp = json.dumps({"hashtags": tags})
    engine, _, _ = _make_engine(llm_resp)
    resp = engine.generate("test", "instagram")
    assert len(resp.hashtags) == 5


def test_engine_degrades_gracefully_when_trends_fail():
    """All trend providers fail → LLM-only hashtags with trending=false, never raises."""
    llm_resp = '{"hashtags": [{"tag": "#ai", "relevance": 0.9}]}'
    engine, _, _ = _make_engine(llm_resp, fail_trends=True)
    resp = engine.generate("test post", "instagram")
    assert len(resp.hashtags) == 1
    assert resp.hashtags[0].trending is False


def test_engine_marks_trending_when_trend_data_available():
    """When trend data exists for a hashtag, trending=true."""
    llm_resp = '{"hashtags": [{"tag": "#ai", "relevance": 0.9}, {"tag": "#unknown", "relevance": 0.5}]}'
    trends = [TrendPoint("#ai", 0.95, 50000, "high")]
    engine, _, _ = _make_engine(llm_resp, trend_points=trends)
    resp = engine.generate("test", "instagram")
    ai_tag = next(h for h in resp.hashtags if h.tag == "#ai")
    unknown_tag = next(h for h in resp.hashtags if h.tag == "#unknown")
    assert ai_tag.trending is True
    assert ai_tag.volume == 50000
    assert ai_tag.competition == "high"
    assert unknown_tag.trending is False


def test_engine_ranking_formula():
    """score = 0.6*trend + 0.3*llm_relevance + 0.1*(1 - competition_penalty)."""
    llm_resp = '{"hashtags": [{"tag": "#ai", "relevance": 0.8}]}'
    trends = [TrendPoint("#ai", 0.9, 10000, "high")]
    engine, _, _ = _make_engine(llm_resp, trend_points=trends)
    resp = engine.generate("test", "instagram")
    # high competition penalty = 1.0
    expected = 0.6 * 0.9 + 0.3 * 0.8 + 0.1 * (1.0 - 1.0)
    assert resp.hashtags[0].score == pytest.approx(expected, abs=0.01)


def test_engine_ranking_low_competition_boost():
    """Low competition gives a small boost vs high."""
    llm_resp = '{"hashtags": [{"tag": "#a", "relevance": 0.5}, {"tag": "#b", "relevance": 0.5}]}'
    trends = [TrendPoint("#a", 0.5, 100, "low"), TrendPoint("#b", 0.5, 100, "high")]
    engine, _, _ = _make_engine(llm_resp, trend_points=trends)
    resp = engine.generate("test", "instagram")
    a = next(h for h in resp.hashtags if h.tag == "#a")
    b = next(h for h in resp.hashtags if h.tag == "#b")
    assert a.score > b.score


def test_engine_handles_invalid_llm_json():
    """LLM returns garbage → engine returns empty hashtags, never raises."""
    engine, _, _ = _make_engine("this is not json")
    resp = engine.generate("test", "instagram")
    assert resp.hashtags == []


def test_engine_handles_llm_missing_hashtags_key():
    """LLM returns valid JSON but no 'hashtags' key → empty list."""
    engine, _, _ = _make_engine('{"foo": "bar"}')
    resp = engine.generate("test", "instagram")
    assert resp.hashtags == []


def test_engine_generates_unique_generation_ids():
    llm_resp = '{"hashtags": [{"tag": "#ai", "relevance": 0.9}]}'
    engine, _, _ = _make_engine(llm_resp)
    r1 = engine.generate("test", "instagram")
    r2 = engine.generate("test", "instagram")
    assert r1.generation_id != r2.generation_id


def test_engine_passes_tone_to_llm():
    llm_resp = '{"hashtags": [{"tag": "#ai", "relevance": 0.9}]}'
    engine, llm, _ = _make_engine(llm_resp)
    engine.generate("test", "instagram", tone="professional")
    assert "professional" in llm.calls[0]["user"]


def test_engine_respects_custom_max_tags():
    llm_resp = '{"hashtags": [{"tag": "#a", "relevance": 0.9}, {"tag": "#b", "relevance": 0.8}]}'
    engine, _, _ = _make_engine(llm_resp)
    resp = engine.generate("test", "x", max_tags=1)
    assert len(resp.hashtags) == 1
    assert resp.max_tags == 1
