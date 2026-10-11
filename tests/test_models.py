"""RED-phase tests: API contract models (architecture §4)."""
import pytest
from pydantic import ValidationError

from hashtagger.models import (
    PLATFORM_DEFAULTS,
    GenerateRequest,
    GenerateResponse,
    HashtagResult,
)


def test_request_minimal_text_and_platform():
    req = GenerateRequest(text="hello world", platform="instagram")
    assert req.text == "hello world"
    assert req.platform == "instagram"
    assert req.max_tags is PLATFORM_DEFAULTS["instagram"]
    assert req.tone is None
    assert req.include_trends is True


def test_request_instagram_default_max_tags_is_five():
    """Instagram's Dec-2025 policy caps output at 5 tags."""
    assert GenerateRequest(text="x", platform="instagram").max_tags == 5


def test_request_text_length_bounds():
    with pytest.raises(ValidationError):
        GenerateRequest(text="", platform="x")
    with pytest.raises(ValidationError):
        GenerateRequest(text="x" * 2001, platform="x")
    # boundary: exactly 1 and 2000 are valid
    assert GenerateRequest(text="x", platform="x").text == "x"
    assert len(GenerateRequest(text="x" * 2000, platform="x").text) == 2000


def test_request_max_tags_bounds():
    with pytest.raises(ValidationError):
        GenerateRequest(text="x", platform="x", max_tags=0)
    with pytest.raises(ValidationError):
        GenerateRequest(text="x", platform="x", max_tags=31)
    assert GenerateRequest(text="x", platform="x", max_tags=30).max_tags == 30


def test_request_invalid_platform():
    with pytest.raises(ValidationError):
        GenerateRequest(text="x", platform="facebook")


def test_request_valid_platforms():
    for p in ("x", "instagram", "tiktok", "youtube", "linkedin", "mastodon"):
        assert GenerateRequest(text="x", platform=p).platform == p


def test_hashtag_result_fields():
    hr = HashtagResult(
        tag="#ai", score=0.93, volume=120000,
        competition="high", trending=True, source="mastodon",
    )
    assert hr.tag == "#ai"
    assert hr.trending is True
    assert hr.source == "mastodon"


def test_hashtag_result_competition_values():
    for c in ("low", "medium", "high"):
        assert HashtagResult(tag="#t", score=0.5, competition=c).competition == c
    with pytest.raises(ValidationError):
        HashtagResult(tag="#t", score=0.5, competition="extreme")


def test_generate_response_shape():
    hr = HashtagResult(tag="#ai", score=0.9, trending=True, source="mastodon")
    resp = GenerateResponse(
        hashtags=[hr], platform="instagram", max_tags=5,
        generation_id="abc-123", model="gpt-4o-mini",
    )
    assert resp.hashtags == [hr]
    assert resp.generation_id == "abc-123"
    assert resp.model == "gpt-4o-mini"
