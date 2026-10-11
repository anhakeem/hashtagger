# Hashtagger — System Architecture

**Phase:** design · **Status:** frozen v1.0 · **Date:** 2026-10-11
**Inputs:** [`results/market-research.md`](../results/market-research.md), [`results/hashtag-data-sources.md`](../results/hashtag-data-sources.md)

---

## 1. Design Goals (from research)

| Research finding | Architectural response |
|---|---|
| No dominant standalone player; competitors do keyword shuffling | LLM does **semantic** extraction; trend data is the moat, not the model |
| No real-time platform data (Buffer: "doesn't pull real-time") | Pluggable **trend provider** interface; cache with TTL |
| Only Inflact shows competition tiers | Return **competition/difficulty** per hashtag |
| No performance feedback loop | Schema reserves a `post_performance` table from day one |
| Instagram 5-tag limit (Dec 2025) → precision > volume | Per-platform output shaping (`max_tags` per platform) |
| LLM is commoditized | Moat = trend + competition data + performance loop |

**Non-goals (v1):** multi-user teams, social scheduling, mobile apps, billing integration (design-only stub).

---

## 2. Component Diagram

```
┌──────────────────────────────────────────────────────────────┐
│  Clients                                                      │
│  ┌───────────────┐   ┌────────────────────┐                  │
│  │  Web UI       │   │ Chrome Extension   │                  │
│  │  (public/)    │   │ (extension/, MV3)  │                  │
│  └──────┬────────┘   └─────────┬──────────┘                  │
└─────────┼──────────────────────┼─────────────────────────────┘
          │  HTTPS/JSON          │  HTTPS/JSON
          ▼                      ▼
┌──────────────────────────────────────────────────────────────┐
│  FastAPI application (src/api/)                               │
│  ┌────────────┬──────────────┬──────────────┬──────────────┐  │
│  │ /generate  │ /trends      │ /usage       │ /health      │  │
│  └─────┬──────┴──────┬───────┴──────┬───────┴──────────────┘  │
│        │             │              │                          │
│  ┌─────▼─────────────▼──────────────▼──────┐                  │
│  │  Service layer (src/services/)          │                  │
│  │  ┌──────────────┐  ┌──────────────────┐ │                  │
│  │  │ HashtagEngine│  │ TrendAggregator  │ │                  │
│  │  │ (LLM + rank) │  │ (providers+cache)│ │                  │
│  │  └──────┬───────┘  └────────┬─────────┘ │                  │
│  └─────────┼───────────────────┼───────────┘                  │
└────────────┼───────────────────┼──────────────────────────────┘
             │                   │
      ┌──────▼──────┐     ┌──────▼───────────────────────────┐
      │ LLM Provider│     │ Trend Providers (pluggable)      │
      │ (OpenAI-    │     │  • MastodonProvider  (free, MVP) │
      │  compatible)│     │  • RedditProvider    (free, MVP) │
      └─────────────┘     │  • TwitterApiIoProvider (prod)   │
                          │  • ApifyTrendsProvider  (prod)   │
                          └──────────────┬───────────────────┘
                                         │
                                   ┌─────▼──────┐
                                   │  SQLite    │
                                   │ (cache +   │
                                   │  usage +   │
                                   │  perf)     │
                                   └────────────┘
```

---

## 3. Data Model (SQLite → Postgres)

```sql
-- Users / accounts (billing stub in v1)
CREATE TABLE accounts (
  id            TEXT PRIMARY KEY,          -- uuid
  email         TEXT UNIQUE NOT NULL,
  tier          TEXT NOT NULL DEFAULT 'free',  -- free | pro
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Daily usage counters (freemium enforcement: 10/day free)
CREATE TABLE usage_counters (
  account_id    TEXT NOT NULL REFERENCES accounts(id),
  day           DATE NOT NULL,
  generate_count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (account_id, day)
);

-- Trend cache (TTL'd rows keyed by platform+hashtag)
CREATE TABLE trend_cache (
  platform      TEXT NOT NULL,             -- x | instagram | tiktok | mastodon | reddit
  hashtag       TEXT NOT NULL,
  score         REAL NOT NULL,             -- normalized 0..1 popularity
  volume        INTEGER,                   -- posts in window (nullable)
  competition   TEXT,                      -- low | medium | high
  fetched_at    TIMESTAMP NOT NULL,
  expires_at    TIMESTAMP NOT NULL,
  source        TEXT NOT NULL,             -- provider id
  PRIMARY KEY (platform, hashtag)
);
CREATE INDEX idx_trend_expiry ON trend_cache(expires_at);

-- Generation log (for analytics + performance loop)
CREATE TABLE generations (
  id            TEXT PRIMARY KEY,
  account_id    TEXT REFERENCES accounts(id),
  post_text     TEXT NOT NULL,
  platform      TEXT NOT NULL,
  hashtags      TEXT NOT NULL,             -- JSON array of results
  model         TEXT,
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Reserved for the feedback loop (v2): which tags actually performed
CREATE TABLE post_performance (
  id            TEXT PRIMARY KEY,
  generation_id TEXT REFERENCES generations(id),
  platform      TEXT NOT NULL,
  impressions   INTEGER,
  engagements   INTEGER,
  recorded_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

---

## 4. API Contract (frozen v1)

Base: `/api/v1` · All responses JSON · Errors follow the single shape in §5.

### `POST /api/v1/generate`

**Request**
```json
{
  "text": "string, 1..2000 chars, required",
  "platform": "x | instagram | tiktok | youtube | linkedin | mastodon",
  "max_tags": "integer 1..30, optional (default per platform)",
  "tone": "string, optional (e.g. 'professional', 'funny')",
  "include_trends": "boolean, optional (default true)"
}
```

**Response 200**
```json
{
  "hashtags": [
    { "tag": "#ai", "score": 0.93, "volume": 120000, "competition": "high",
      "trending": true, "source": "mastodon" }
  ],
  "platform": "instagram",
  "max_tags": 5,
  "generation_id": "uuid",
  "model": "gpt-4o-mini"
}
```

**Errors:** `422` validation · `429` free-tier limit reached (body includes `reset_at`) · `502` upstream provider failure (degrade gracefully: return LLM-only tags with `trending:false`).

### `GET /api/v1/trends?platform=instagram&q=ai&limit=20`
Returns ranked trending hashtags for a platform, from cache. `200` → `{ "hashtags": [...] }`.

### `GET /api/v1/usage`
`200` → `{ "tier": "free", "used_today": 3, "limit": 10, "reset_at": "..." }`

### `GET /api/v1/health`
`200` → `{ "status": "ok", "providers": {"llm":"ok","mastodon":"ok"} }`

### Contract rules
- **Additive-only** changes (new optional fields); never change/remove a field type.
- List endpoints paginate (`limit`, `offset`).
- Rate-limit headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`.
- Every state-changing endpoint documents retry safety; `/generate` is **safe to retry** (idempotent by content — no side effects beyond a usage increment, which is deduped per `(account, day)`).

---

## 5. Error Shape (single format, all endpoints)

```json
{ "error": { "code": "VALIDATION_ERROR", "message": "text is required", "details": {} } }
```
Codes: `VALIDATION_ERROR` (422) · `UNAUTHENTICATED` (401) · `FORBIDDEN` (403) · `NOT_FOUND` (404) · `RATE_LIMITED` (429) · `UPSTREAM_ERROR` (502) · `INTERNAL` (500).

---

## 6. Trend Provider Interface (the moat)

```python
class TrendProvider(Protocol):
    id: str
    platforms: set[str]
    def fetch(self, platform: str, seed_terms: list[str]) -> list[TrendPoint]: ...
    def health(self) -> bool: ...
```

| Provider | Phase | Cost | Notes (from research) |
|---|---|---|---|
| `MastodonProvider` | MVP | $0 | 300 req/5min, real hashtag timelines |
| `RedditProvider` | MVP | $0 (non-comm) | 100 QPM; commercial needs approval |
| `TwitterApiIoProvider` | Production | $0.15/1K tweets | Best cost/value for X |
| `ApifyTrendsProvider` | Production | $5/1K results | TikTok + Google Trends |

`TrendAggregator` fans out to enabled providers, normalizes scores to 0..1, merges, and caches with TTL (default 4h, matching the best competitor). Provider failure is non-fatal — degrade to LLM-only.

---

## 7. AI Prompt Strategy

- **System prompt:** extract 8–15 *semantic* topic signals from the post; never invent brand names; return strict JSON.
- **Determinism:** `temperature=0.3`; seed where supported.
- **Output validation:** parse JSON, reject/repair on schema mismatch (never trust LLM output — validate at the boundary).
- **Ranking:** final score = `0.6 * trend_score + 0.3 * llm_relevance + 0.1 * (1 - competition_penalty)`.
- **Platform shaping:** clip to `max_tags` (Instagram=5 per Dec-2025 policy), prefer lower-competition tags when scores tie.

---

## 8. Security & Privacy

- API keys only via env (`OPENAI_API_KEY`, provider keys) — never logged, never committed.
- Post text is user content: not persisted beyond `generations` (retention policy: 30 days, configurable).
- No secrets in the extension: it calls our API, never the LLM/trend providers directly.
- CORS locked to known origins; `host_permissions` in the extension is only our API domain.
- Rate limiting per account + per IP to protect upstream quotas and cost.

---

## 9. Cost Model (per 1,000 generations, estimates)

| Item | Estimate | Basis |
|---|---|---|
| LLM tokens | ~$0.30 | gpt-4o-mini, ~1.5K tokens/gen |
| Trend fetch | ~$0.15–0.50 | cached 4h → amortized |
| Infra | ~$0.05 | small VPS |
| **Total** | **~$0.50–0.85** | vs $9/mo Pro → viable at ~15 gen/mo/user |

---

## 10. Frozen Decisions

1. Python 3.11 + FastAPI, no build step for the MVP UI.
2. SQLite for MVP; repository layer keeps Postgres migration a config change.
3. Trend providers are pluggable behind `TrendProvider`; MVP ships Mastodon + Reddit.
4. LLM is provider-agnostic (OpenAI-compatible base URL).
5. Free tier = 10 generations/day enforced in `usage_counters`.
6. `/generate` degrades to LLM-only on provider failure — never 500s on a trend outage.

**Next:** implementation phase → `core-engine` (TDD), then `api`, then `web-ui`.
