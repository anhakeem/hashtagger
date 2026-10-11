# Audit Log — Hashtagger

Chronological record of decisions, changes, and rationale.

## 2026-10-11 — Project initialized

- **Decision:** Split "Hashtagger" out of the Loot Drop research as a standalone project.
  - **Why:** Idea had 1,388 community upvotes (highest of the doable set) and is a
    weekend-scale MVP — fastest path to a shippable artifact.
  - **Source:** https://www.loot-drop.io/ideas.html
- **Decision:** Tech stack = Python + FastAPI + HTML/CSS/JS + OpenAI-compatible API + SQLite.
  - **Why:** No build step for MVP keeps the weekend timeline realistic; SQLite defers
    infra until there is demand.
- **Decision:** Project lives at `/home/hermes/projects/hashtagger/` and is registered as a
  separate Hermes desktop Project (id `p_524aa363`) so it runs in its own session/workspace.
- **Decision:** Monetization = freemium, 10/day free → $9/mo Pro (analytics + trend forecasting).

### Open items / blockers
- GitHub push pending: `gh` CLI not installed (needs sudo) and the fine-grained
  PAT in `~/.hermes/.env` cannot create repos via REST. Local git repo is ready to push.

## 2026-10-11 — Research phase complete (2 subagents)

- **market-research.md:** 20 competitors mapped. Key finding: market is fragmented;
  no dominant standalone AI hashtag tool; competitors do keyword shuffling, not
  contextual AI; none have real-time trend data. Instagram's Dec-2025 5-tag limit
  increases demand for precision. $9/mo sits below RiteTag ($49) and Flick ($14).
- **hashtag-data-sources.md:** 37 sources evaluated. No single source covers all
  platforms. MVP path = Mastodon (free) + Reddit (free tier). Production = TwitterAPI.io
  ($0.15/1K tweets). Instagram API near-useless for trends (30 hashtags/7d).

## 2026-10-11 — Design phase complete

- **Decision:** Architecture frozen v1 — see `docs/architecture.md`.
  - **Moat:** trend + competition data + performance loop, not the LLM (commoditized).
  - **Trend providers are pluggable** behind a `TrendProvider` interface; MVP ships
    Mastodon + Reddit, production adds TwitterAPI.io + Apify.
  - **Degrade gracefully:** provider outage → LLM-only hashtags, never a 500.
  - **Ranking formula:** `0.6*trend + 0.3*llm_relevance + 0.1*(1-competition)`.
  - **Free tier enforced** in `usage_counters` (10/day).
  - **API contract frozen** (additive-only, single error shape, rate-limit headers).
  - `post_performance` table reserved from day one for the v2 feedback loop.

### Next
- Implementation phase: `core-engine` (TDD) → `api` → `web-ui`.
