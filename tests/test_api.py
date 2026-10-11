"""Tests for the FastAPI layer (architecture §4 contract)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from hashtagger.api.main import create_app
from hashtagger.models import GenerateResponse, HashtagResult
from hashtagger.trends.base import TrendPoint


class FakeEngine:
    """Stand-in for HashtagEngine so API tests don't touch LLM/network."""

    def __init__(self):
        self.calls: list[dict] = []

    def generate(self, text, platform, max_tags=None, tone=None, include_trends=True):
        self.calls.append(
            dict(text=text, platform=platform, max_tags=max_tags, tone=tone)
        )
        return GenerateResponse(
            hashtags=[HashtagResult(tag="#ai", score=0.9, trending=True, source="trend")],
            platform=platform,
            max_tags=max_tags or 5,
            generation_id="test-gen-id",
            model="fake-model",
        )


class FailingEngine:
    def generate(self, *a, **k):
        raise RuntimeError("upstream exploded")


def make_client(engine) -> TestClient:
    app = create_app(engine_factory=lambda: engine)
    return TestClient(app)


# ---- POST /api/v1/generate ------------------------------------------------

def test_generate_returns_contract_shape():
    engine = FakeEngine()
    client = make_client(engine)
    resp = client.post(
        "/api/v1/generate",
        json={"text": "hello world", "platform": "instagram"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["platform"] == "instagram"
    assert body["hashtags"][0]["tag"] == "#ai"
    assert engine.calls[0]["platform"] == "instagram"


def test_generate_rejects_empty_text():
    client = make_client(FakeEngine())
    resp = client.post("/api/v1/generate", json={"text": "", "platform": "x"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_generate_rejects_unknown_platform():
    client = make_client(FakeEngine())
    resp = client.post("/api/v1/generate", json={"text": "hi", "platform": "myspace"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_generate_engine_failure_returns_502():
    client = make_client(FailingEngine())
    resp = client.post("/api/v1/generate", json={"text": "hi", "platform": "x"})
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "UPSTREAM_ERROR"


# ---- GET /api/v1/health ----------------------------------------------------

def test_health_ok():
    client = make_client(FakeEngine())
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---- error shape consistency ----------------------------------------------

def test_error_shape_is_consistent():
    client = make_client(FakeEngine())
    resp = client.post("/api/v1/generate", json={"text": "", "platform": "x"})
    err = resp.json()["error"]
    assert set(err) >= {"code", "message"}
