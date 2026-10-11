"""Regression tests for provider review fixes (deleg_6490a216 follow-up).

Covers:
  #2  providers must declare the platforms they actually serve
  #6  user-derived seed terms must not be written to logs
  #12 the same hashtag returned for multiple seed terms must not double-count
  #21 the injected httpx client must actually be used
"""
from __future__ import annotations

import logging

import httpx

from hashtagger.models import PLATFORMS
from hashtagger.trends.mastodon import MastodonProvider
from hashtagger.trends.reddit import RedditProvider


def _masto_client(handler) -> httpx.Client:
    return httpx.Client(
        base_url="https://mastodon.social",
        transport=httpx.MockTransport(handler),
        headers={"User-Agent": "test/0.1"},
    )


# ---- #2: platform coverage -------------------------------------------------

def test_providers_serve_valid_contract_platforms():
    """Every platform a provider claims must be in the API contract PLATFORMS."""
    for prov in (MastodonProvider(client=_masto_client(lambda r: httpx.Response(200, json={}))),
                 RedditProvider(client=httpx.Client(base_url="https://www.reddit.com",
                                                    transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))))):
        assert prov.platforms, f"{prov.id} declares no platforms"
        unknown = prov.platforms - set(PLATFORMS)
        assert not unknown, f"{prov.id} claims non-contract platforms: {unknown}"


# ---- #12: no double counting across seed terms ----------------------------

def test_mastodon_no_double_count_across_terms():
    """The same hashtag returned for two seed terms must be counted once."""
    def handler(request: httpx.Request) -> httpx.Response:
        # Both terms return the same tag #ai with 100 uses.
        return httpx.Response(
            200,
            json={"tags": [{"name": "ai", "history": [{"uses": "100", "accounts": "10"}]}]},
        )

    p = MastodonProvider(client=_masto_client(handler))
    points = p.fetch("mastodon", ["ai", "artificialintelligence"])
    ai = [pt for pt in points if pt.hashtag == "#ai"]
    assert len(ai) == 1, "duplicate hashtag rows"
    assert ai[0].volume == 100, f"expected 100 (counted once), got {ai[0].volume}"


# ---- #6: no user-derived text in logs -------------------------------------

def test_mastodon_does_not_log_seed_terms(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    p = MastodonProvider(client=_masto_client(handler))
    with caplog.at_level(logging.WARNING):
        p.fetch("mastodon", ["supersecretterm"])
    assert "supersecretterm" not in caplog.text, "seed term leaked into logs"


def test_reddit_does_not_log_seed_terms(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    p = RedditProvider(client=httpx.Client(
        base_url="https://www.reddit.com",
        transport=httpx.MockTransport(handler),
        headers={"User-Agent": "test/0.1"},
    ))
    with caplog.at_level(logging.WARNING):
        p.fetch("instagram", ["supersecretterm"])
    assert "supersecretterm" not in caplog.text, "seed term leaked into logs"


# ---- #21: injected client is used -----------------------------------------

def test_mastodon_uses_injected_client():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"tags": []})

    p = MastodonProvider(client=_masto_client(handler))
    p.fetch("mastodon", ["ai"])
    assert seen, "injected client was not used for the request"
