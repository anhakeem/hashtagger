# Hashtagger

AI-powered hashtag generator for social media. Paste a post → get ranked,
trending hashtags that maximize reach and engagement.

**Source:** [Loot Drop Startup Graveyard](https://www.loot-drop.io/ideas.html) — 1,388 upvotes
**Owner:** Ahmed Elhakeem (@AhmedTitan01)
**License:** MIT

---

## The Problem

Creators and marketers guess at hashtags. Picking the wrong ones kills reach;
picking generic ones buries the post. There is no fast, data-driven way to get
*targeted, currently-trending* hashtags for a specific piece of content.

## The Product

1. **Web app** — paste a post, get 20–30 ranked hashtags with reach estimates.
2. **REST API** — for automation and third-party integrations.
3. **Chrome extension** — analyze the composer on X/Twitter in real time.

## Monetization

| Tier | Price | Limits |
|------|-------|--------|
| Free | $0 | 10 generations/day, basic suggestions |
| Pro | $9/mo | Unlimited, analytics, trend forecasting, API access |

## Tech Stack

| Layer | Choice |
|-------|--------|
| Backend | Python 3.11 + FastAPI |
| Frontend | HTML/CSS/JS (no build step for MVP) |
| AI | OpenAI-compatible API (provider-agnostic) |
| Database | SQLite (MVP) → PostgreSQL (scale) |
| Extension | Chrome Manifest V3 |

## Build Plan

See [`project.yaml`](project.yaml) for the full phase/task breakdown.

```
research → design → implementation → testing → extension → improvement
```

| Phase | Deliverable | Success criteria |
|-------|-------------|------------------|
| research | market + data-source reports | ≥5 competitors, ≥2 data sources |
| design | `docs/architecture.md` | API contract frozen |
| implementation | `src/`, `public/` | E2E: paste → ranked hashtags |
| testing | test suite | all pass, >80% core coverage |
| extension | `extension/` | loads unpacked, works on x.com |
| improvement | review report | no critical issues |

## Quick Start (once MVP lands)

```bash
cd src && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn api.main:app --reload      # API on :8000
cd ../public && python -m http.server 3000   # UI on :3000
```

## Repository Layout

```
hashtagger/
├── project.yaml      # phases, tasks, success criteria
├── agents.yaml       # agent roles for orchestration
├── tasks.yaml        # task queue with dependencies
├── src/              # backend (engine + API)
├── public/           # web UI
├── extension/        # Chrome MV3 extension
├── tests/            # test suite
├── docs/             # architecture, market analysis
├── results/          # agent outputs (reports)
├── audit/            # decisions + change log
└── workspace/        # shared scratch for agents
```
