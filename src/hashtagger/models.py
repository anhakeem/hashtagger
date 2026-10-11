"""Pydantic models for the frozen v1 API contract (architecture §4)."""
from __future__ import annotations

from pydantic import BaseModel, Field

PLATFORMS = ("x", "instagram", "tiktok", "youtube", "linkedin", "mastodon")

# Every contract platform as a set — used by providers whose signal is
# platform-agnostic (Mastodon/Reddit trends inform hashtags for any platform).
ALL_PLATFORMS: set[str] = set(PLATFORMS)

# Per-platform default output shaping (Instagram=5 per Dec-2025 policy).
PLATFORM_DEFAULTS: dict[str, int] = {
    "x": 3,
    "instagram": 5,
    "tiktok": 5,
    "youtube": 5,
    "linkedin": 5,
    "mastodon": 5,
}

COMPETITION_LEVELS = ("low", "medium", "high")


class GenerateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    platform: str
    max_tags: int | None = Field(default=None, ge=1, le=30)
    tone: str | None = None
    include_trends: bool = True
    account_id: str | None = Field(default=None, max_length=128)

    def model_post_init(self, __context) -> None:
        if self.platform not in PLATFORMS:
            raise ValueError(f"unsupported platform: {self.platform}")
        if self.max_tags is None:
            self.max_tags = PLATFORM_DEFAULTS[self.platform]


class HashtagResult(BaseModel):
    tag: str
    score: float = Field(ge=0.0, le=1.0)
    volume: int | None = None
    competition: str = "low"
    trending: bool = False
    source: str | None = None

    def model_post_init(self, __context) -> None:
        if self.competition not in COMPETITION_LEVELS:
            raise ValueError(f"invalid competition: {self.competition}")


class GenerateResponse(BaseModel):
    hashtags: list[HashtagResult]
    platform: str
    max_tags: int
    generation_id: str
    model: str | None = None
