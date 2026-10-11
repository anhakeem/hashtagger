"""RED-phase tests: RedditProvider."""
import httpx
import pytest

from hashtagger.trends.base import TrendPoint
from hashtagger.trends.reddit import RedditProvider


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(
        base_url="https://www.reddit.com",
        transport=httpx.MockTransport(handler),
        headers={"User-Agent": "hashtagger-dev/0.1 by /u/test"},
    )


def test_id_and_platforms():
    p = RedditProvider()
    assert p.id == "reddit"
    assert isinstance(p.platforms, set)
    assert "reddit" in p.platforms


def test_fetch_extracts_hashtags_from_titles():
    payload = {
        "data": {
            "children": [
                {"data": {"title": "AI is transforming #machinelearning #ai", "ups": 5000, "num_comments": 800}},
                {"data": {"title": "New breakthrough in #ai research", "ups": 3000, "num_comments": 400}},
                {"data": {"title": "No hashtags here", "ups": 1000, "num_comments": 50}},
            ]
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/r/MachineLearning/hot.json"
        return httpx.Response(200, json=payload)

    p = RedditProvider(client=_mock_client(handler))
    points = p.fetch("reddit", ["ai", "machinelearning"])

    assert len(points) == 2
    assert all(isinstance(pt, TrendPoint) for pt in points)
    hashtags = {pt.hashtag for pt in points}
    assert hashtags == {"#ai", "#machinelearning"}


def test_fetch_scores_proportional_to_engagement():
    payload = {
        "data": {
            "children": [
                {"data": {"title": "#ai is huge", "ups": 10000, "num_comments": 2000}},
                {"data": {"title": "#ml is small", "ups": 10, "num_comments": 2}},
            ]
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    p = RedditProvider(client=_mock_client(handler))
    points = p.fetch("reddit", ["ai"])
    ai = next(pt for pt in points if pt.hashtag == "#ai")
    ml = next(pt for pt in points if pt.hashtag == "#ml")
    assert ai.score > ml.score
    assert ai.score == pytest.approx(1.0, abs=0.05)


def test_fetch_empty_results():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"children": []}})

    p = RedditProvider(client=_mock_client(handler))
    assert p.fetch("reddit", ["nothing"]) == []


def test_unsupported_platform_raises():
    p = RedditProvider()
    with pytest.raises(ValueError):
        p.fetch("instagram", ["ai"])


def test_health_ok():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {}})

    p = RedditProvider(client=_mock_client(handler))
    assert p.health() is True


def test_health_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    p = RedditProvider(client=_mock_client(handler))
    assert p.health() is False


def test_health_network_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    p = RedditProvider(client=_mock_client(handler))
    assert p.health() is False
