"""Tests for the TwitterAPI.io trend provider (production X/Twitter source)."""
from __future__ import annotations

import httpx
import pytest

from hashtagger.trends.twitterapi_io import TwitterApiIoProvider


def _client(handler) -> httpx.Client:
    return httpx.Client(
        base_url="https://api.twitterapi.io",
        transport=httpx.MockTransport(handler),
        headers={"X-API-Key": "test-key"},
    )


def test_id_and_platforms():
    p = TwitterApiIoProvider(api_key="test-key")
    assert p.id == "twitterapi_io"
    assert isinstance(p.platforms, set)
    # X data is the primary signal for the 'x' platform, but hashtag activity
    # is useful cross-platform, so it serves all contract platforms.
    assert "x" in p.platforms


def test_fetch_parses_tweets_into_hashtags():
    payload = {
        "tweets": [
            {"text": "AI is huge #ai #machinelearning", "likeCount": 1000, "retweetCount": 200},
            {"text": "More #ai talk", "likeCount": 500, "retweetCount": 100},
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert "advanced_search" in str(request.url)
        return httpx.Response(200, json=payload)

    p = TwitterApiIoProvider(api_key="test-key", client=_client(handler))
    points = p.fetch("x", ["ai"])
    tags = {pt.hashtag for pt in points}
    assert "#ai" in tags and "#machinelearning" in tags


def test_fetch_scores_by_engagement():
    payload = {
        "tweets": [
            {"text": "#big", "likeCount": 10000, "retweetCount": 5000},
            {"text": "#small", "likeCount": 5, "retweetCount": 1},
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    p = TwitterApiIoProvider(api_key="test-key", client=_client(handler))
    points = p.fetch("x", ["test"])
    by = {pt.hashtag: pt for pt in points}
    assert by["#big"].score > by["#small"].score
    assert 0.0 <= by["#big"].score <= 1.0


def test_fetch_no_double_count_across_terms():
    """The same tweet returned for two terms must not double-count."""
    payload = {"tweets": [{"text": "#ai rocks", "likeCount": 100, "retweetCount": 0}]}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    p = TwitterApiIoProvider(api_key="test-key", client=_client(handler))
    points = p.fetch("x", ["ai", "artificialintelligence"])
    ai = [pt for pt in points if pt.hashtag == "#ai"]
    assert len(ai) == 1
    assert ai[0].volume == 100, f"expected 100 (counted once), got {ai[0].volume}"


def test_fetch_empty_returns_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"tweets": []})

    p = TwitterApiIoProvider(api_key="test-key", client=_client(handler))
    assert p.fetch("x", ["nothing"]) == []


def test_fetch_does_not_log_seed_terms(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    p = TwitterApiIoProvider(api_key="test-key", client=_client(handler))
    with caplog.at_level("WARNING"):
        p.fetch("x", ["supersecretterm"])
    assert "supersecretterm" not in caplog.text


def test_missing_api_key_raises():
    with pytest.raises(ValueError):
        TwitterApiIoProvider(api_key="")


def test_unsupported_platform_raises():
    p = TwitterApiIoProvider(api_key="test-key")
    with pytest.raises(ValueError):
        p.fetch("myspace", ["ai"])


def test_health_ok_and_failure():
    def ok(request): return httpx.Response(200, json={"tweets": []})
    def bad(request): raise httpx.ConnectError("x")

    assert TwitterApiIoProvider(api_key="k", client=_client(ok)).health() is True
    assert TwitterApiIoProvider(api_key="k", client=_client(bad)).health() is False
