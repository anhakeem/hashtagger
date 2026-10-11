"""FastAPI application for Hashtagger (architecture §4 contract).

Endpoints:
  POST /api/v1/generate   -> ranked hashtags for a post
  GET  /api/v1/health     -> liveness + provider status

Errors follow the single shape in architecture §5:
  {"error": {"code": ..., "message": ..., "details": ...}}
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from hashtagger.models import GenerateRequest, GenerateResponse

log = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


def _error(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


def create_app(engine_factory=None) -> FastAPI:
    """Build the app. `engine_factory` is called lazily to construct the engine,
    which keeps tests free of LLM/network dependencies."""
    app = FastAPI(title="Hashtagger API", version="1.0.0")

    if engine_factory is None:
        engine_factory = _default_engine_factory

    _engine_cache: dict[str, object] = {}

    def get_engine():
        if "engine" not in _engine_cache:
            _engine_cache["engine"] = engine_factory()
        return _engine_cache["engine"]

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError):
        # exc.errors() can contain non-serializable objects (e.g. a ValueError
        # raised inside model_post_init). Sanitize to plain JSON-safe data.
        safe = []
        for e in exc.errors():
            item = {k: v for k, v in e.items() if k in ("type", "loc", "msg")}
            item["loc"] = [str(x) for x in item.get("loc", [])]
            item["msg"] = str(item.get("msg", ""))
            safe.append(item)
        return _error(422, "VALIDATION_ERROR", "invalid request", {"errors": safe})

    @app.post(f"{API_PREFIX}/generate", response_model=GenerateResponse)
    async def generate(req: GenerateRequest):
        try:
            result = get_engine().generate(
                text=req.text,
                platform=req.platform,
                max_tags=req.max_tags,
                tone=req.tone,
                include_trends=req.include_trends,
            )
        except Exception as exc:  # noqa: BLE001 — map any engine failure to 502
            log.error("generate failed: %s", type(exc).__name__)
            return _error(502, "UPSTREAM_ERROR", "hashtag generation failed")
        return result

    @app.get(f"{API_PREFIX}/health")
    async def health():
        return {"status": "ok"}

    return app


def _default_engine_factory():
    """Construct the real engine from environment configuration."""
    import os

    from hashtagger.engine import HashtagEngine
    from hashtagger.trends.aggregator import TrendAggregator
    from hashtagger.trends.mastodon import MastodonProvider
    from hashtagger.trends.reddit import RedditProvider

    class _HTTPLLMClient:
        """Minimal OpenAI-compatible chat client (no SDK dependency)."""

        def __init__(self) -> None:
            import httpx

            self._base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
            self._key = os.environ.get("OPENAI_API_KEY", "")
            self._model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
            self._client = httpx.Client(base_url=self._base, timeout=30.0)

        def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
            resp = self._client.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {self._key}"},
                json={
                    "model": self._model,
                    "temperature": temperature,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

    aggregator = TrendAggregator([MastodonProvider(), RedditProvider()])
    return HashtagEngine(
        aggregator=aggregator,
        llm_client=_HTTPLLMClient(),
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
    )


app = create_app()
