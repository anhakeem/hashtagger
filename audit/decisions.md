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
