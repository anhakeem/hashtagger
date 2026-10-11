"""RED-phase tests: MastodonProvider."""
import httpx
import pytest

from hashtagger.trends.base import TrendPoint
from hashtagger.trends.mastodon import MastodonProvider


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(
        base_url="https://mastodon.social",
        transport=httpx.MockTransport(handler),
        headers={"User-Agent": "hashtagger-dev/0.1"},
    )


def test_id_and_platforms():
    p = MastodonProvider()
    assert p.id == "mastodon"
    assert isinstance(p.platforms, set)
    # Mastodon trends are platform-agnostic: they serve every contract platform.
    assert "instagram" in p.platforms
    assert "x" in p.platforms


def test_fetch_returns_trend_points():
    payload = {
        "tags": [
            {
                "name": "ai",
                "url": "https://mastodon.social/tags/ai",
                "history": [
                    {"day": "1728432000", "uses": "5000", "accounts": "3000"},
                    {"day": "1728518400", "uses": "3000", "accounts": "2000"},
                ],
            },
            {
                "name": "machinelearning",
                "url": "https://mastodon.social/tags/machinelearning",
                "history": [{"day": "1728432000", "uses": "100", "accounts": "80"}],
            },
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/search"
        return httpx.Response(200, json=payload)

    p = MastodonProvider(client=_mock_client(handler))
    points = p.fetch("mastodon", ["ai"])

    assert len(points) == 2
    assert all(isinstance(pt, TrendPoint) for pt in points)
    ai = next(pt for pt in points if pt.hashtag == "#ai")
    assert ai.volume == 8000  # 5000 + 3000
    assert 0.0 <= ai.score <= 1.0
    ml = next(pt for pt in points if pt.hashtag == "#machinelearning")
    assert ml.volume == 100


def test_fetch_normalizes_scores_to_zero_one():
    payload = {
        "tags": [
            {
                "name": "viral",
                "url": "https://mastodon.social/tags/viral",
                "history": [{"day": "1728432000", "uses": "999999", "accounts": "5"}],
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    p = MastodonProvider(client=_mock_client(handler))
    points = p.fetch("mastodon", ["viral"])
    assert points[0].score == pytest.approx(1.0, abs=0.05)


def test_fetch_skips_terms_with_no_tags():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"tags": []})

    p = MastodonProvider(client=_mock_client(handler))
    assert p.fetch("mastodon", ["nothing"]) == []


def test_unsupported_platform_raises():
    p = MastodonProvider()
    with pytest.raises(ValueError):
        p.fetch("myspace", ["ai"])


def test_health_ok():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/instance"
        return httpx.Response(200, json={"uri": "mastodon.social"})

    p = MastodonProvider(client=_mock_client(handler))
    assert p.health() is True


def test_health_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    p = MastodonProvider(client=_mock_client(handler))
    assert p.health() is False


def test_health_network_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    p = MastodonProvider(client=_mock_client(handler))
    assert p.health() is False
