"""Trend provider protocol and shared data types (frozen v1 design §6)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class TrendPoint:
    """A single trending-hashtag observation from a provider."""

    hashtag: str
    score: float  # normalized 0..1 popularity
    volume: int = 0  # posts in window (nullable upstream)
    competition: str = "low"  # low | medium | high

    def __post_init__(self) -> None:
        self.score = max(0.0, min(1.0, float(self.score)))


@runtime_checkable
class TrendProvider(Protocol):
    """Pluggable trend source. MVP ships Mastodon + Reddit."""

    id: str
    platforms: set[str]

    def fetch(self, platform: str, seed_terms: list[str]) -> list[TrendPoint]:
        """Return trend points for `platform` relevant to `seed_terms`."""
        ...

    def health(self) -> bool:
        """True when the provider's upstream is reachable."""
        ...
