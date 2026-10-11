"""RED-phase tests: TrendPoint dataclass + TrendProvider protocol."""
import pytest
from hashtagger.trends.base import TrendPoint, TrendProvider


def test_trend_point_has_required_fields():
    """A TrendPoint must expose hashtag, score, volume, competition."""
    tp = TrendPoint(hashtag="#ai", score=0.85, volume=12000, competition="high")
    assert tp.hashtag == "#ai"
    assert tp.score == 0.85
    assert tp.volume == 12000
    assert tp.competition == "high"


def test_trend_point_score_clamped():
    """Score must be clamped to the 0..1 range."""
    tp_hi = TrendPoint(hashtag="#x", score=1.5, volume=0, competition="low")
    tp_lo = TrendPoint(hashtag="#y", score=-0.3, volume=0, competition="low")
    assert tp_hi.score == 1.0
    assert tp_lo.score == 0.0


def test_trend_provider_protocol_structural():
    """Any class satisfying the Protocol can act as a provider."""

    class DummyProvider:
        id = "dummy"
        platforms = {"mastodon"}

        def fetch(self, platform, seed_terms):
            return [TrendPoint(hashtag="#test", score=0.5, volume=10, competition="low")]

        def health(self):
            return True

    # If this runs without raising, the Protocol is satisfied.
    provider = DummyProvider()
    assert isinstance(provider, TrendProvider)
    assert provider.id == "dummy"
    assert provider.fetch("mastodon", []) == [
        TrendPoint(hashtag="#test", score=0.5, volume=10, competition="low")
    ]
    assert provider.health() is True
