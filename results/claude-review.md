I've reviewed all 6 source files, the 6 test files and `docs/architecture.md`. I couldn't run the tests: running pytest needed permission and wasn't approved. So this review comes from reading the code, and where a finding depends on runtime behavior I say what I reasoned from. No files were changed.

The four most serious problems:
- When the LLM returns no tags, the full post text is sent to mastodon.social and written to logs (#1).
- Every non-Mastodon platform, including Instagram, always comes back LLM-only, and the Reddit provider is never used (#2).
- The number of outbound requests per post has no limit, and a user's post text can push it up (#3).
- A trend outage gets cached for 4 hours (#4).

## Findings

### Critical

1. **`engine.py:76` — the post text is sent to third-party APIs when the LLM returns no tags.** The code is `seed_terms = [...] or [text]`. If the LLM call fails or its output can't be parsed, the whole post (up to 2000 chars) goes to `MastodonProvider` as the search query `q=<post>` to mastodon.social, and to Reddit as a lookup term. This breaks §8 (post text stays inside `generations`).
   - It also has no benefit: the fusion loop at line 86 only walks `llm_tags`, which is empty here, so the trend data is thrown away. The fallback only adds privacy exposure, upstream quota use and latency.
   - The text is then copied into two more places: logs (#6) and the in-memory cache (#7).

2. **`mastodon.py:34`, `reddit.py:51` vs `models.py:6` — no provider covers 5 of the 6 contract platforms.** `MastodonProvider.platforms = {"mastodon"}` and `RedditProvider.platforms = {"reddit"}`, but `"reddit"` isn't a valid platform in `PLATFORMS`.
   - For x, instagram, tiktok, youtube and linkedin, `aggregator.py:58` skips every provider, so results are always LLM-only with `trending:false`.
   - Instagram, the main use case in §1, never gets trend data, and the Reddit provider can't be reached through the engine.
   - The tests hide this: `test_engine` fakes the aggregator, and `test_aggregator` only uses `"mastodon"`.

### High

3. **`engine.py:139-147`, `mastodon.py:68`, `reddit.py:91` — nothing limits how many outbound calls one post can trigger.**
   - `_parse_llm_response` accepts any number of tags. The prompt asks for 8–15, but nothing enforces it.
   - Each seed term becomes one sequential HTTP request with a 10s timeout and no overall deadline. With 15 tags that's up to about 150s of latency per provider; with 500 tags it's 500 requests.
   - Seed terms aren't deduplicated.
   - The post text goes straight into the prompt (`engine.py:65`), so a user can write "return 300 hashtags" and multiply our upstream calls. That alone exceeds Mastodon's 300 req/5min (§6) and works against the cost goals in §8 and §9.

4. **`aggregator.py:70-71` — failures are cached for the full TTL.** When every provider throws, `result == []` is still stored for 4 hours. After a short outage, that platform+seed key stays LLM-only for 4h even once upstream recovers. Errors swallowed inside providers (#10) have the same effect.

5. **`engine.py:98` — "trending" is effectively always true when any trend point exists.** Any tag that matches a trend point gets `trending=True`, even if its score is 0 or it had a single use this week.
   - Mastodon is queried with the LLM's own tags as search terms, so `/api/v1/search` almost always returns the tag itself.
   - Result: on Mastodon nearly every LLM tag is marked trending. That's search data being labelled as trend data.

6. **`mastodon.py:72` — post content gets logged.** `log.warning("mastodon search failed for %r", term)` writes the seed term to logs. Through #1, that term is the whole post. Even normally, it's text derived from the user's post, which §8 says isn't kept outside `generations`.

7. **`aggregator.py:29,51` — the cache never evicts and holds user content.**
   - Keys are user-derived seed tuples, and through #1 sometimes the full post text.
   - Expired entries are only removed when the same key is looked up again, so the dict grows without limit (a memory leak) and keeps post-derived text in memory outside the 30-day retention rules.

8. **`aggregator.py:51` — the cache is keyed by the whole seed set, so it almost never hits.**
   - The key is `(platform, sorted(seed_terms))`, i.e. the full set of LLM tags for one post. Two posts rarely produce the same set, so hit rate is close to 0.
   - §3 (`trend_cache PRIMARY KEY (platform, hashtag)`) and §9 ("cached 4h → amortized") assume a per-hashtag cache. The cost model doesn't hold as built.
   - Terms also aren't lowercased or deduplicated before building the key.

### Medium

9. **`engine.py:104` — LLM-only tags get a competition bonus they haven't earned.**
   - `_rank_score(0.0, relevance, "low")` gives them the full +0.1 "low competition" bonus, and `HashtagResult` reports `competition="low"` (the default at `models.py:39`). The API is claiming low competition for tags it knows nothing about.
   - Meanwhile an unrecognised competition string on a *trend* tag gets the maximum penalty (`_COMPETITION_PENALTY.get(..., 1.0)`, line 36). Unknown competition is handled in opposite ways in the two branches.
   - Example: an LLM-only tag with relevance 1.0 scores 0.40. A trend tag with trend score 0.1, relevance 0.5 and high competition scores 0.21. The bonus is half the gap between them.

10. **`mastodon.py:69-73`, `reddit.py:93-97` — per-term errors are swallowed, so failures look like "no data".**
    - If every term fails (e.g. the instance is down, or a 429), `fetch` returns `[]` instead of raising. The aggregator can't tell an outage from an empty result, and caches it (#4).
    - After a 429, the loop keeps sending requests for the remaining terms with no backoff or early stop.

11. **`reddit.py:91-106` — subreddit fetches are duplicated and engagement is double-counted.**
    - Unmapped terms all fall back to `r/all`, and `"ai"`, `"ml"` and `"machinelearning"` all map to `r/MachineLearning`. 15 unmapped terms means fetching r/all 15 times.
    - Each repeat adds the same posts' engagement again, so `volume` and `competition` are inflated by the number of repeats. `test_reddit.py:40` makes exactly this call (two terms → the same sub) but doesn't check volume.

12. **`mastodon.py:82-84` — Mastodon volume is double-counted too.** A tag returned by more than one search term (e.g. `#ai` for "ai" and "artificialintelligence") has its uses/accounts summed once per term. That inflates `volume` and can raise `competition` to medium/high.

13. **`mastodon.py:92-95`, `reddit.py:111-114` — trend scores are relative to each batch, not absolute popularity.**
    - Scores are divided by the largest value in the current result set. A lone tag with 3 uses scores 1.0, the same as `#ai` with 1M uses.
    - Different providers each set their own top result to 1.0, and `aggregator.py:67` merges with `max`, so scores from different providers aren't comparable.
    - So `trend_score` (60% of the final score) doesn't measure what §3 describes ("normalized 0..1 popularity").
    - Also, the aggregator docstring and §6 say the aggregator normalizes scores; it doesn't.

14. **`engine.py:115` — the tie-break from §7 isn't implemented.** §7 says "prefer lower-competition tags when scores tie", but the sort key is `score` only. Equal scores keep the LLM's order. Untested.

15. **`engine.py:145` (inside `_parse_llm_response`) — one bad entry throws away the whole LLM result.**
    - `float(t.get("relevance"))` raises on `"high"`, `null` or `[]`. The exception isn't caught per entry; it escapes to `engine.py:71`, which discards *every* tag.
    - That empty list then triggers the post-text leak in #1.
    - §7 says "reject/repair": bad entries should be dropped or fixed individually.

16. **`engine.py:89-112` vs `models.py:43-45` — a bad competition value from a provider crashes `generate`.**
    - `TrendPoint.competition` (`base.py:15`) isn't validated. If a provider returns `"Medium"` or `"extreme"`, the `HashtagResult` constructor raises inside the fusion loop, which has no try/except.
    - `generate` then throws and the request becomes a 500, breaking frozen decision #6 ("never 500s on a trend outage") and the docstring "Never raises on trend failure" (line 60).

17. **`engine.py:53-59` — `include_trends` can't be honored.** The field is in the request contract (§4, `models.py:26`), but `generate()` has no parameter for it. Trends are always fetched, which costs money and, through #1, risks privacy, even when the client asked for no trends.

18. **`engine.py:99,110` — `source` isn't the provider id the contract shows.** The engine emits `"trend"` or `"llm"`, but §4's example shows `"source": "mastodon"`. `TrendPoint` has no field for the provider id, and the aggregator drops which provider a point came from, so the contract value can't be produced.

19. **`engine.py:68-73` — an LLM failure is hidden behind a normal empty response.** The engine returns 200 with `hashtags: []`, so the API layer can't return `502 UPSTREAM_ERROR` (§4/§5), and the user's daily usage still goes up. The doc's "degrade" only covers trend failure; a dead LLM shouldn't look like a successful empty result.

20. **`engine.py:143` — tags are barely validated.** The only check is `startswith("#")`. These all pass: `"#"`, `"# ai"`, `"#ai ml"`, a 5,000-char tag, `"#<script>"`. Duplicates differing only in case (`#AI` and `#ai`) aren't merged and both use up `max_tags` slots. Nothing enforces "never invent brand names" either.

21. **`engine.py:65-67`, `models.py:25` — prompt injection and unbounded `tone`.**
    - Post text and `tone` are pasted into the prompt with no delimiters, so either can steer the output (offensive tags, huge lists, see #3).
    - `tone` has no `max_length`, so an arbitrarily long tone is sent to the LLM (token cost).

22. **`reddit.py:61-66` — Reddit calls are unauthenticated and the User-Agent is a placeholder.** The UA is `"by /u/test"` and there's no OAuth. Reddit's 100 QPM limit (§6) only applies to OAuth clients; unauthenticated traffic gets much lower limits or 403s. Nothing gates the "commercial needs approval" condition either.

### Low

23. **`engine.py:145-146` — NaN relevance becomes 1.0.** `json.loads` accepts `NaN`, and `max(0.0, min(1.0, nan))` evaluates to `1.0`. `base.py:18` clamps `TrendPoint.score` the same way.
24. **`engine.py:82` — duplicate tags keep the lowest score.** Points arrive sorted by score descending, and the dict comprehension keeps the last one per key. This happens because `aggregator.py:66` merges case-sensitively (`#AI` and `#ai` stay separate) while the engine lowercases.
25. **`engine.py:61-62,116` — `max_tags` and `platform` aren't validated in the engine.** `max_tags=-1` makes `results[:-1]` drop only the last tag; `0` returns nothing. Unknown platforms silently default to 5.
26. **`engine.py:45` — the engine is typed against the concrete `TrendAggregator`.** Tests pass a duck-typed fake. A Protocol type would match how it's actually used.
27. **`engine.py:22-28,47` — no seed, and the reported model may be wrong.** `LLMClient` has no `seed` parameter (§7 says "seed where supported"). The `model` in the response is a constructor string, not what the client actually called.
28. **`aggregator.py:38-39` — not thread-safe.** Under FastAPI's threadpool, two requests can both try to `del` the same expired key; the second gets a `KeyError` and that request loses its trend data. The cache also returns shared, mutable `TrendPoint` lists to callers.
29. **`mastodon.py:75-80`, `reddit.py:99-102` — bad fields in one upstream item fail the whole provider.** A non-numeric `uses`, a `None` name, or a string `ups` raises outside the per-term try, so the entire provider result is lost.
30. **`base.py:14` — volume `0` vs `None`.** `TrendPoint.volume` defaults to `0`, but §3 says volume is nullable. The engine passes `0` through, so the API can't tell "no data" from "zero posts".
31. **`reddit.py:18` — the hashtag regex is too loose.** `#(\w+)` matches `"#1"` in "We're #1" and accepts any Unicode word. Hashtags in Reddit titles are rare, so the signal is weak.
32. **`mastodon.py:34`, `reddit.py:51` — `platforms` is a mutable set shared by every instance.** It's a class attribute.
33. **`models.py:23,28-32` — validation uses `model_post_init`.** `platform` would be simpler as a `Literal`. `GenerateResponse.platform` and `max_tags` (lines 50-51) aren't constrained.

### Test quality

34. **`tests/test_engine.py` — no privacy test.** `FakeAggregator.calls` is recorded but never checked. No test makes sure the post text isn't sent as a seed term, and no test covers the `or [text]` fallback (#1).
35. **`tests/test_engine.py:12-21` — LLM failure is untested.** `FakeLLMClient` can't raise, so the `engine.py:71` branch never runs, and there's no case with one bad `relevance` value (#15).
36. **`tests/test_engine.py:98-106` — the ranking test is weak.**
    - Using `"high"` competition makes the competition term zero, so that term is never checked numerically.
    - `abs=0.01` is loose for an exact formula.
    - "medium" (0.5 penalty), the LLM-only score (#9) and the tie-break (#14) are never tested.
37. **`tests/test_engine.py:66-72` — the clipping test only checks the count.** It asserts `len == 5`, not that the five highest scores were kept, or in order.
38. **`tests/test_engine.py:75-81` — the degrade test is thin.** It checks `trending is False` but not the score, the `source`, or that a provider throwing *inside the real aggregator* still degrades. There are no tests combining the engine with the real aggregator, and none for the non-Mastodon platform gap (#2).
39. **`tests/test_aggregator.py:40-49` — the "normalizes" test doesn't test normalization.** Its inputs are already in 0..1, so it only tests max-merge.
40. **`tests/test_aggregator.py` — important aggregator cases are missing:** failures aren't cached (#4), the cache key ignores term order, case-insensitive merge, and cache size limits.
41. **`tests/test_aggregator.py:81-89` — timing depends on real sleep.** `time.sleep(0.02)` against a 0.01s TTL; injecting a clock would make this deterministic.
42. **`tests/test_mastodon.py:59-75` — the normalization test can't fail.** With a single tag, `log1p(n)/log1p(n)` is always 1.0.
43. **`tests/test_mastodon.py` — missing Mastodon cases:** multi-term double-counting (#12), per-term failures, bad payloads, `_competition_level` thresholds, and the request params (`q`, `type`, `limit`).
44. **`tests/test_reddit.py:24-45` — double-counting goes unasserted.** The test triggers it (two terms → the same subreddit) but never checks `volume` or `competition`. There's also no test for the fallback to `r/all`, a failed fetch, or competition levels.
45. **`tests/test_mastodon.py:17-21,86-89`, `tests/test_reddit.py:17-21,77-80` — real `httpx.Client`s are created and never closed.** No requests are sent, but the clients leak.
46. **`tests/test_models.py:17` — `is` is used to compare ints.** `req.max_tags is PLATFORM_DEFAULTS[...]` only passes because Python caches small ints; it should be `==`. There's no test that `HashtagResult` rejects `score > 1` or `< 0`.
47. **Every test file — stale names and imports.** The "RED-phase" docstrings are out of date now that the code is implemented, and `test_engine.py:7,9` imports `HashtagResult` and `TrendAggregator` without using them.

Suggested fix order: #1 → #3/#7 → #2 → #4/#10 → #16 → #9/#14, then the tests in #34–#38. Run pytest locally to confirm the suite's current baseline before changing anything.
