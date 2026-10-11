"""FastAPI application for Hashtagger (architecture §4 contract).

Endpoints:
  POST /api/v1/generate            -> ranked hashtags for a post
  GET  /api/v1/usage               -> tier + daily usage
  POST /api/v1/billing/checkout    -> upgrade/downgrade a plan
  POST /api/v1/billing/webhook     -> subscription events
  POST /api/v1/performance         -> record post performance (v2 loop)
  GET  /api/v1/performance/top     -> top tags by engagement rate
  GET  /api/v1/health              -> liveness + provider status

Errors follow the single shape in architecture §5:
  {"error": {"code": ..., "message": ..., "details": ...}}
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from hashtagger.billing import BillingService, PaymentError, StubPaymentProvider
from hashtagger.models import GenerateRequest, GenerateResponse

log = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


class BillingCheckoutRequest(BaseModel):
    account_id: str = Field(min_length=1, max_length=128)
    plan: str = Field(min_length=1, max_length=32)


class PerformanceRequest(BaseModel):
    generation_id: str = Field(min_length=1, max_length=128)
    platform: str = Field(min_length=1, max_length=32)
    tag: str = Field(min_length=1, max_length=100)
    impressions: int = Field(default=0, ge=0)
    engagements: int = Field(default=0, ge=0)


def _error(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


def create_app(engine_factory=None, usage_store_factory=None,
               billing_factory=None, performance_factory=None) -> FastAPI:
    """Build the app. `engine_factory` is called lazily to construct the engine,
    which keeps tests free of LLM/network dependencies."""
    app = FastAPI(title="Hashtagger API", version="1.0.0")

    if engine_factory is None:
        engine_factory = _default_engine_factory
    if usage_store_factory is None:
        usage_store_factory = _default_usage_store_factory
    if performance_factory is None:
        performance_factory = _default_performance_factory

    _engine_cache: dict[str, object] = {}

    def get_engine():
        if "engine" not in _engine_cache:
            _engine_cache["engine"] = engine_factory()
        return _engine_cache["engine"]

    def get_usage():
        if "usage" not in _engine_cache:
            _engine_cache["usage"] = usage_store_factory()
        return _engine_cache["usage"]

    def get_billing():
        if "billing" not in _engine_cache:
            if billing_factory is not None:
                _engine_cache["billing"] = billing_factory()
            else:
                _engine_cache["billing"] = BillingService(
                    usage=get_usage(), provider=StubPaymentProvider()
                )
        return _engine_cache["billing"]

    def get_performance():
        if "performance" not in _engine_cache:
            _engine_cache["performance"] = performance_factory()
        return _engine_cache["performance"]

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
        # Freemium enforcement: an identified account is rate-limited on free.
        usage = get_usage()
        if req.account_id is not None and not usage.can_generate(req.account_id):
            s = usage.summary(req.account_id)
            return _error(
                429, "RATE_LIMITED",
                f"free tier limit reached ({s['limit']}/day); upgrade for unlimited",
                {"tier": s["tier"], "limit": s["limit"], "used_today": s["used_today"],
                 "reset_at": s["reset_at"]},
            )
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
        if req.account_id is not None:
            usage.increment(req.account_id)
        return result

    @app.get(f"{API_PREFIX}/usage")
    async def usage_endpoint(account_id: str):
        return get_usage().summary(account_id)

    @app.post(f"{API_PREFIX}/billing/checkout")
    async def billing_checkout(req: BillingCheckoutRequest):
        try:
            return get_billing().create_checkout(account_id=req.account_id, plan=req.plan)
        except ValueError as exc:
            return _error(422, "VALIDATION_ERROR", str(exc))
        except PaymentError as exc:
            return _error(402, "PAYMENT_REQUIRED", str(exc))

    @app.post(f"{API_PREFIX}/billing/webhook")
    async def billing_webhook(event: dict):
        try:
            return get_billing().handle_webhook(event)
        except ValueError as exc:
            return _error(422, "VALIDATION_ERROR", str(exc))

    @app.post(f"{API_PREFIX}/performance")
    async def record_performance(req: PerformanceRequest):
        perf = get_performance()
        rid = perf.record(
            generation_id=req.generation_id, platform=req.platform, tag=req.tag,
            impressions=req.impressions, engagements=req.engagements,
        )
        return {"id": rid, "recorded": True}

    @app.get(f"{API_PREFIX}/performance/top")
    async def top_performance(platform: str | None = None, limit: int = 10):
        return {"tags": get_performance().top_tags(platform=platform, limit=limit)}

    @app.get(f"{API_PREFIX}/health")
    async def health():
        return {"status": "ok"}

    return app


def _default_usage_store_factory():
    """Usage store backed by the configured SQLite database."""
    import os

    from hashtagger.usage import UsageStore

    return UsageStore(db_path=os.environ.get("USAGE_DB", "./hashtagger.db"))


def _default_performance_factory():
    """Performance store backed by the configured SQLite database."""
    import os

    from hashtagger.performance import PerformanceStore

    return PerformanceStore(db_path=os.environ.get("PERF_DB", "./hashtagger.db"))


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

    # Trend providers: free MVP sources always; TwitterAPI.io only when a key
    # is configured (it is the paid production source for X data).
    providers = [MastodonProvider(), RedditProvider()]
    if os.environ.get("TWITTERAPI_IO_KEY"):
        from hashtagger.trends.twitterapi_io import TwitterApiIoProvider

        providers.append(TwitterApiIoProvider())

    aggregator = TrendAggregator(providers)
    return HashtagEngine(
        aggregator=aggregator,
        llm_client=_HTTPLLMClient(),
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
    )


app = create_app()
