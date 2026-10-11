# Hashtag Trend Data Sources — Research Findings

> **Project:** Hashtagger — AI-powered hashtag generator  
> **Date:** October 2026  
> **Purpose:** Identify viable sources of *currently trending* hashtags for ranking AI-generated suggestions.  
> **Scope:** Official APIs, unofficial APIs, third-party data providers, and scrapers across major platforms.

---

## Table of Contents

1. [X (Twitter)](#x-twitter)
2. [Instagram](#instagram)
3. [TikTok](#tiktok)
4. [Google Trends](#google-trends)
5. [Reddit](#reddit)
6. [YouTube](#youtube)
7. [Mastodon](#mastodon)
8. [Third-Party Hashtag APIs & Scrapers](#third-party-hashtag-apis--scrapers)
9. [Comparison Matrix](#comparison-matrix)
10. [Recommendation](#recommendation)
11. [Sources](#sources)

---

## X (Twitter)

### Official API v2

X provides the most direct access to real-time hashtag trends via its v2 API.

| Tier | Monthly Cost | Rate Limits | Notes |
|------|-------------|-------------|-------|
| **Free** | $0 | 17 posts/24h; read limits apply (25 requests/24h for `GET /2/users/me`) | Very limited read access; primarily for posting |
| **Basic** | $200/mo ($175/mo annual) | 450 requests/15 min (app-level); 300 requests/15 min (user-level) for recent search; 10,000 tweet reads/month; 50,000 posts/month | Entry tier for read access; 7-day historical search |
| **Pro** | $5,000/mo ($4,500/mo annual) | 1,000,000 reads/month; 300,000 posts/month | 30-day historical search |
| **Enterprise** | Custom (~$42K+/mo reported) | Custom | Full archive access |

**Pay-Per-Use Pilot** (announced 2025–2026): New developers default to pay-per-use pricing (~$0.01/post, ~$0.005/read). Legacy Basic/Pro tiers are grandfathered only. ([X Developer Announcement](https://devcommunity.x.com/t/announcing-the-x-api-pay-per-use-pricing-pilot/250253), [Postproxy](https://postproxy.dev/blog/social-media-platform-api-rules-rate-limits-media-specs))

### Trends Endpoint

- `GET /2/tweets/counts/recent` — tweet counts by keyword/hashtag
- `GET /1.1/trends/place.json` — trending topics by WOEID (v1.1, still available)
- Trending hashtags can be extracted from recent search results

**Key constraint:** The 10,000 tweet read cap on Basic is extremely low for trend aggregation. At ~100 tweets per hashtag query, you can only query ~100 hashtags/month.

**Sources:** [X Developer Portal](https://developer.x.com), [TwitterAPI.io comparison](https://twitterapi.io/articles/twitter-api-rate-limits-vs-alternative-solutions), [Xpoz Blog](https://www.xpoz.ai/blog/guides/understanding-twitter-api-pricing-tiers-and-alternatives)

---

## Instagram

### Graph API (Meta)

Instagram's official API is **posting-focused**; hashtag read access is extremely limited.

| Feature | Limit |
|---------|-------|
| Platform rate limit | 200 calls/hour × N users (app-level, scales with user base) |
| Hashtag search | **30 unique hashtags per rolling 7 days** per Instagram user |
| Content publishing | 25 posts per 24 hours per account |
| Media uploads | 500 posts/month free tier (X), Instagram separate |

**Hashtag Search Process:**
1. Resolve hashtag → ID: `GET /v21.0/ig_hashtag_search?q={hashtag}`
2. Fetch media: `GET /v21.0/{hashtag-id}/recent_media`

**Key constraints:**
- Requires Instagram Professional (Business/Creator) account
- Basic Display API deprecated December 4, 2024
- No trending hashtag endpoint — you can only query specific hashtags
- 30 hashtag lookups per 7 days is nearly useless for trend discovery

**Sources:** [Meta Graph API Docs](https://developers.facebook.com/docs/instagram-api), [Zernio](https://zernio.com/blog/instagram-graph-api), [Phyllo](https://www.getphyllo.com/post/instagram-api-rate-limits-explained-and-how-to-scale-beyond-them-2026), [Blotato](https://www.blotato.com/blog/instagram-api-pricing)

---

## TikTok

### Official Research API

| Requirement | Detail |
|-------------|--------|
| **Access** | Academic/institutional only — non-commercial |
| **Application** | Formal proposal + institutional affiliation required |
| **Approval** | Weeks to months; discretionary |
| **Cost** | Free for approved researchers |
| **Commercial use** | Not permitted |

**Key constraint:** Completely unsuitable for a commercial product. Access requires institutional affiliation, ethical review, and non-commercial commitment. As of 2025–2026, TikTok has hardened access — there is **no free commercial API**.

**Sources:** [TikTok Research API](https://developers.tiktok.com/products/research-api), [SociaVault](https://sociavault.com/blog/tiktok-api-free-2026), [KInIT](https://kinit.sk/when-research-apis-close-the-door-when-you-finally-get-it-it-is-not-what-you-have-asked-for)

### TikTok Creative Center (Scraping)

- Web UI: [TikTok Creative Center - Trends](https://ads.tiktok.com/business/creativecenter/trending/hashtag/pc/en)
- No official API — data is accessible via browser scraping only
- Apify offers ready-made scrapers:
  - **TikTok Trends** — trending hashtags from 27 countries, top videos with engagement metrics ([Apify](https://apify.com/data_xplorer/tiktok-trends))
  - **TikTok Trending Hashtags Scraper** — by lexis-solutions ([Apify](https://apify.com/lexis-solutions/tiktok-trending-hashtags-scraper))
- **Apify pricing:** Pay-per-result (from $5/1,000 results) or platform subscription ($5 free credit)

### Third-Party TikTok APIs

| Provider | Pricing | Notes |
|----------|---------|-------|
| **Data365** | Custom pricing | TikTok trends API with video views, hashtags, engagement ([Data365](https://data365.co/blog/tiktok-trends-api)) |
| **TickerTrends** | Substack-based | Historical hashtag view counts, monthly growth tracking ([TickerTrends](https://blog.tickertrends.io/p/tiktok-trends-api-timeseries-hashtag-analytics)) |
| **Phyllo** | Custom | Unified API with hashtag analytics endpoint (popularity score, reach, demographics) ([Phyllo](https://www.getphyllo.com/post/tiktok-content-discovery-how-developers-use-the-tiktok-search-api-iv)) |

---

## Google Trends

### Official API

**No official public API exists.** Google shut down the Google Trends API in 2007 and never replaced it.

- **Unofficial libraries:** `pytrends` (Python) — repository archived April 17, 2025, now read-only and broken due to Google consent flow changes ([Anakin.io](https://anakin.io/blog/pytrends-dead-google-trends-api-alternative-2026), [ScrapeGraphAI](https://scrapegraphai.com/blog/google-trends-api))
- **Google Trends API alpha** announced July 24, 2025 — limited, application-based access for researchers/journalists/developers. Not publicly available from standard Google Cloud console. ([ScrapeGraphAI](https://scrapegraphai.com/blog/google-trends-api))

### Unofficial Workarounds

| Approach | Status | Notes |
|----------|--------|-------|
| pytrends (Python) | ❌ Broken (archived Apr 2025) | Fails on datacenter IPs; NID cookie flow broken |
| Direct scraping | ⚠️ Fragile | Aggressive rate limiting; IP blocks after a few hundred requests |
| Apify Google Trends scraper | ✅ Working | Pay-per-result; avoids IP blocks via rotating proxies ([Apify](https://apify.com)) |
| SerpAPI | ✅ Working | SERP API approach; paid tiers |

**Key constraint:** No reliable, free, programmatic access to Google Trends data. Scraping is fragile and rate-limited.

**Sources:** [The Mine Works](https://themineworks.com/blog/google-trends-scraper-api-python), [Requestly](https://requestly.com/api-explorer/google-trends)

---

## Reddit

### Data API

| Tier | Cost | Rate Limit | Notes |
|------|------|------------|-------|
| **Free (non-commercial)** | $0 | 100 QPM (queries per minute) per OAuth client | Averaged over 10-min window |
| **Commercial** | $0.24 per 1,000 API calls | Custom | Requires manual approval (2–4 weeks) |
| **Data licensing** | Custom (~$60M/yr reported Google deal) | Custom | For AI training at scale |

**Key constraint:** Commercial use requires Reddit approval + paid agreement. For a hashtag generator, Reddit could provide trending topics via subreddit analysis, but the commercial approval barrier is significant.

**Reddit as hashtag proxy:** Subreddit names and post titles often mirror trending hashtags. Free tier (100 QPM) may be sufficient for a low-volume product during development.

**Sources:** [Reddit Data API Wiki](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki), [SocialCrawl](https://www.socialcrawl.dev/blog/reddit-data-api-2026), [Apidog](https://apidog.com/blog/reddit-api-guide)

---

## YouTube

### Data API v3

| Metric | Value |
|--------|-------|
| Default quota | 10,000 units/day |
| `search.list` cost | 100 units per call |
| Quota reset | Midnight Pacific Time |
| Paid tier | None published — quota increase requires audit |

**Key constraint:** 100 searches/day with default quota. YouTube doesn't have a native hashtag trend system, but video tags and titles contain hashtags. The quota is too low for systematic trend aggregation.

**Unofficial:** `youtube-transcript-api` and similar libraries exist but are also fragile.

**Sources:** [Google Developers](https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits), [ChannelCrawler](https://channelcrawler.com/insights/youtube-api-daily-limit-quotas-costs-and-how-to-scale-beyond-10000-units-channelcrawler), [Blotato](https://www.blotato.com/blog/youtube-api-pricing)

---

## Mastodon

### Official API

| Metric | Value |
|--------|-------|
| Rate limit | 300 requests per 5 minutes (per account AND per IP) |
| Cost | Free |
| Auth | Optional for public read access |
| Hashtag endpoint | `GET /api/v1/tags/{name}` and `GET /api/v1/timelines/tag/{hashtag}` |

**Key constraint:** Decentralized — trending hashtags vary by instance. You'd need to query multiple instances. Rate limit is generous but per-IP, so multi-instance querying is straightforward.

**Apify Mastodon Scraper:** [mastodon-social-scraper](https://apify.com/navy_currant/mastodon-social-scraper) — from $5/1,000 results.

**Sources:** [Mastodon API docs](https://docs.joinmastodon.org/api/rate-limits), [Communalytic](https://communalytic.org/docs/mastodon-hashtag-posts-data-collector)

---

## Third-Party Hashtag APIs & Scrapers

### Unified Social Data Providers

| Provider | Pricing | Platforms | Notes |
|----------|---------|-----------|-------|
| **TwitterAPI.io** | $0.15 per 1,000 tweets | X/Twitter | 1,000+ req/sec; full 14+ year archive; no monthly fee; <5 min setup ([TwitterAPI.io](https://twitterapi.io)) |
| **SocialData.tools** | $0.20 per 1,000 tweets | X/Twitter | Alternative to official API |
| **GetXAPI** | $0.05 per 1,000 tweets | X/Twitter | Lowest cost X data |
| **EnsembleData** | $200–$1,400/mo | Instagram, TikTok, etc. | 5,000–50,000 units/day; scraping-based ([EnsembleData](https://www.ensemble-data.com)) |
| **Phyllo** | Custom | Instagram, TikTok, X, etc. | Unified API; abstracts rate limits ([Phyllo](https://www.getphyllo.com)) |

### Hashtag-Specific Tools with APIs

| Tool | Pricing | API | Notes |
|------|---------|-----|-------|
| **RiteTag** | $49–$249/mo | Yes (RiteKit) | 5,000–100,000 suggestions/mo; real-time suggestions; historical data ([RiteTag](https://ritetag.com), [RiteKit](https://ritekit.com/api-demo)) |
| **RiteKit API** | $99–$600/mo | Yes | 100 calls/second; hashtag suggestions for Instagram + 9 platforms ([RiteKit](https://ritekit.com/api-demo)) |
| **Hashtagify** | $19/mo (Personal) | Yes (Enterprise) | Trending hashtag search; popularity metrics ([Hashtagify](https://hashtagify.me), [Saasworthy](https://www.saasworthy.com/product/hashtagify/pricing)) |

### Apify Scrapers (Pay-per-Result)

| Scraper | Pricing | What it provides |
|---------|---------|-------------------|
| Social Media Hashtag Research | Pay-per-run | Facebook, Instagram, TikTok, YouTube hashtag posts ([Apify](https://apify.com/apify/social-media-hashtag-research/api)) |
| TikTok Trends | From $5/1,000 results | Trending hashtags from 27 countries ([Apify](https://apify.com/data_xplorer/tiktok-trends)) |
| Mastodon Scraper | From $5/1,000 results | Hashtag timelines, trending tags ([Apify](https://apify.com/navy_currant/mastodon-social-scraper)) |
| Instagram Hashtag Scraper | Various | Post extraction by hashtag |

### RapidAPI

- Marketplace with dozens of hashtag/social APIs
- Free tiers: typically 50–500 requests/day
- Paid: $10–$100+/month
- Quality varies wildly; no SLAs; can break overnight
- **Sources:** [RapidAPI Hashtag Collection](https://rapidapi.com/collection/hashtag-api), [RapidAPI blog](https://medium.com/@rapid_api/top-50-most-popular-apis-on-rapidapi-2019-5eb77658892a)

---

## Comparison Matrix

| Source | Trending Data? | Commercial Use? | Free Tier? | Rate Limit | Setup Effort | Cost for Scale |
|--------|---------------|-----------------|------------|------------|--------------|----------------|
| **X API Basic** | ✅ Yes | ✅ Yes | ❌ No | 450 req/15 min | Medium | $200/mo (10K reads) |
| **X API PPU** | ✅ Yes | ✅ Yes | ❌ No | N/A | Low | ~$0.005/read |
| **TwitterAPI.io** | ✅ Yes | ✅ Yes | ❌ No | 1,000+ req/sec | Low | $0.15/1K tweets |
| **Instagram Graph** | ⚠️ Limited | ✅ Yes | ✅ Yes | 200 calls/hr × users | High | $0 (30 hashtags/7d) |
| **TikTok Research** | ✅ Yes | ❌ No | ✅ Academic | Varies | High | N/A |
| **TikTok Scraping** | ✅ Yes | ⚠️ Gray area | ❌ No | N/A | Medium | $5+/1K results |
| **Google Trends** | ✅ Yes | ⚠️ Unofficial | ✅ Yes | Aggressive IP limits | Low | Fragile/unreliable |
| **Reddit API** | ⚠️ Indirect | ⚠️ Commercial approval | ✅ Non-commercial | 100 QPM | Low | $0.24/1K calls |
| **YouTube API** | ⚠️ Indirect | ✅ Yes | ✅ Yes | 100 searches/day | Medium | Quota audit needed |
| **Mastodon API** | ⚠️ Instance-specific | ✅ Yes | ✅ Yes | 300 req/5 min | Low | Free |
| **RiteTag/RiteKit** | ✅ Yes | ✅ Yes | ❌ No | 100 calls/sec | Low | $99–$600/mo |
| **Hashtagify** | ✅ Yes | ✅ Yes | ❌ No | N/A | Low | $19+/mo |
| **Apify scrapers** | ✅ Yes | ✅ Yes | ✅ Limited | N/A | Low | $5+/1K results |

---

## Recommendation

### Phase 1: MVP / Development (Free)
1. **Mastodon API** — free, generous rate limits, real hashtag timelines. Use as a baseline trend source.
2. **Reddit API (free tier)** — monitor subreddit trending topics and titles for emerging hashtags. 100 QPM is sufficient for development.
3. **TikTok Creative Center scraping** (via Apify or manual) — trending hashtags with view counts. Start with pay-per-result to validate.
4. **X API Free tier** — 17 posts/24h won't help with read trends, but useful for testing posting integration later.

### Phase 2: Production Launch (Low Cost)
1. **TwitterAPI.io** ($0.15/1K tweets) — primary source for X/Twitter trending hashtags. No monthly fee, instant setup, 14+ years of history. This is the best cost-to-value ratio for X data.
2. **Google Trends scraping via Apify** — for search-interest trends that correlate with hashtag popularity.
3. **Apify TikTok Trends scraper** — for cross-platform trending hashtag discovery.

### Phase 3: Scale
1. **X API Basic** ($200/mo) — if you need guaranteed rate limits and official access for X data.
2. **Phyllo or EnsembleData** — if you need unified multi-platform data at scale and want to abstract rate limit management.
3. **RiteKit API** ($99/mo) — if you want a dedicated hashtag suggestion API with historical performance data.

### Key Insights
- **No single source covers all platforms.** A multi-source approach is necessary.
- **X/Twitter is the most hashtag-centric platform** and should be the primary source.
- **Instagram's API is nearly useless for trend discovery** (30 hashtags/7 days). Scraping or third-party data is required.
- **TikTok has no commercial API.** Scraping Creative Center is the only viable path.
- **Google Trends correlates with hashtag popularity** but has no reliable free API.
- **Mastodon is an underrated free source** — open API, generous limits, real-time hashtag timelines.
- **TwitterAPI.io is the best cost-efficient X data source** at $0.15/1K tweets with no monthly minimum.

---

## Sources

1. [X Developer Portal](https://developer.x.com)
2. [X Developer Community — Pay-Per-Use Announcement](https://devcommunity.x.com/t/announcing-the-x-api-pay-per-use-pricing-pilot/250253)
3. [X Developer Community — Free Tier Rate Limits](https://devcommunity.x.com/t/specifics-about-the-new-free-tier-rate-limits/229761)
4. [TwitterAPI.io — Rate Limits vs Alternatives](https://twitterapi.io/articles/twitter-api-rate-limits-vs-alternative-solutions)
5. [Xpoz Blog — Twitter API Pricing](https://www.xpoz.ai/blog/guides/understanding-twitter-api-pricing-tiers-and-alternatives)
6. [Postproxy — Social Media API Rules 2026](https://postproxy.dev/blog/social-media-platform-api-rules-rate-limits-media-specs)
7. [Meta Graph API Documentation](https://developers.facebook.com/docs/instagram-api)
8. [Zernio — Instagram Graph API Rate Limits](https://zernio.com/blog/instagram-graph-api)
9. [Phyllo — Instagram API Rate Limits](https://www.getphyllo.com/post/instagram-api-rate-limits-explained-and-how-to-scale-beyond-them-2026)
10. [Blotato — Instagram API Pricing](https://www.blotato.com/blog/instagram-api-pricing)
11. [TikTok Research API](https://developers.tiktok.com/products/research-api)
12. [SociaVault — Is TikTok API Free?](https://sociavault.com/blog/tiktok-api-free-2026)
13. [Apify — TikTok Trends](https://apify.com/data_xplorer/tiktok-trends)
14. [Data365 — TikTok Trends API](https://data365.co/blog/tiktok-trends-api)
15. [TickerTrends — TikTok Trends API](https://blog.tickertrends.io/p/tiktok-trends-api-timeseries-hashtag-analytics)
16. [The Mine Works — Google Trends API](https://themineworks.com/blog/google-trends-scraper-api-python)
17. [Anakin.io — pytrends Dead](https://anakin.io/blog/pytrends-dead-google-trends-api-alternative-2026)
18. [ScrapeGraphAI — Google Trends API](https://scrapegraphai.com/blog/google-trends-api)
19. [Requestly — Google Trends API Explorer](https://requestly.com/api-explorer/google-trends)
20. [Reddit Data API Wiki](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki)
21. [SocialCrawl — Reddit API 2026](https://www.socialcrawl.dev/blog/reddit-data-api-2026)
22. [Apidog — Reddit API Guide](https://apidog.com/blog/reddit-api-guide)
23. [Google Developers — YouTube API Quota](https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits)
24. [ChannelCrawler — YouTube API Limits](https://channelcrawler.com/insights/youtube-api-daily-limit-quotas-costs-and-how-to-scale-beyond-10000-units-channelcrawler)
25. [Blotato — YouTube API Pricing](https://www.blotato.com/blog/youtube-api-pricing)
26. [Mastodon API Rate Limits](https://docs.joinmastodon.org/api/rate-limits)
27. [Communalytic — Mastodon Hashtag Collector](https://communalytic.org/docs/mastodon-hashtag-posts-data-collector)
28. [Apify — Mastodon Social Scraper](https://apify.com/navy_currant/mastodon-social-scraper/api/openapi)
29. [RiteKit API Demo](https://ritekit.com/api-demo)
30. [RiteTag Review — Research.com](https://research.com/software/reviews/ritetag)
31. [Hashtagify Pricing — Saasworthy](https://www.saasworthy.com/product/hashtagify/pricing)
32. [Apify — Social Media Hashtag Research](https://apify.com/apify/social-media-hashtag-research/api)
33. [RapidAPI — Hashtag API Collection](https://rapidapi.com/collection/hashtag-api)
34. [BrandMentions — How to Find Trending Hashtags](https://brandmentions.com/blog/how-to-find-trending-hashtags)
35. [Phyllo — TikTok Content Discovery](https://www.getphyllo.com/post/tiktok-content-discovery-how-developers-use-the-tiktok-search-api-iv)
36. [KInIT — TikTok Research API Access](https://kinit.sk/when-research-apis-close-the-door-when-you-finally-get-it-it-is-not-what-you-have-asked-for)
37. [Meta Content Library / DSA Research](https://arxiv.org/html/2601.12390v1)
