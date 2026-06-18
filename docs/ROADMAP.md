# WC2026 Predictor — Roadmap

**Created:** 2026-06-19
**Owner:** Jaso
**Status:** Phase 1 in pre-build research (no code yet)

---

## Context: where the project stands

Live at https://wc26.tinjak.com (commit `224689a`). Architecture:
- **Frontend:** Next 14.2 App Router (Docker, served via nginx-proxy-manager)
- **Backend:** FastAPI + SQLite, Dixon-Coles model, 20k Monte Carlo tournament sim
- **VPS:** 51.161.134.191 (4-core, ~7GB free RAM, plenty of disk)
- **Data feeds (already wired):**
  - The Odds API (free tier — 500 req/month, ~490 remaining today) → bookmaker odds
  - api-football.com (`API_FOOTBALL_KEY` env var) → lineups, injuries, suspensions, squad xG
  - football-data.org (`FOOTBALL_DATA_KEY` env var) → match events
  - openweathermap (`OPENWEATHER_API_KEY`) → match-day weather context

**Pages live:** /, /value, /acca, /bracket, /groups, /scenarios, /winner, /performance, /predictions, /match3, /how-it-works, /team/<code>, /match/<id>.

**Recent additions (16-19 Jun):**
- Live knockout bracket (locks in as groups complete)
- MD3 progression scenarios
- VAPID push notifications with pywebpush (live)
- PWA manifest + service worker + WC26 logo icons
- Plain-language Report Card TL;DR
- Mobile nav with bottom-sheet for secondary items
- Auto-pick matchday + sticky context-aware back navigation

---

## Phase 0 — Competitive landscape (researched 2026-06-19)

| Competitor | Strength | Gap they leave |
|---|---|---|
| **Opta Supercomputer** | 10,000 sims, per-team round %, polished articles, brand authority | Articles only — no interactivity, no public Brier score, no value picks, B2B price tag |
| **FotMob** | Real-time scores, bracket UI, lineup builder, "predict the score" game | No transparent prediction model, no value-pick discovery |
| **Superbru / Prodefy** | Prediction pool — friends + leagues + leaderboards | Pure game. No data analysis, no probabilities, no model |
| **Dimers / InPredictable / Sportradar widget** | Live in-game win probability — for US sports & EPL | Nobody is doing it well for WC2026 right now |
| **FiveThirtyEight SPI** (defunct 2023) | The "swing chart", public methodology, longitudinal accuracy tracking | RIP. Audience has no replacement |

**Verbatim user pain points** from r/sportsanalytics + r/PredictionsMarkets:
- "Track their win rate publicly so you can see the data yourself before trusting anything, which is rare"
- "Distinction between tools that predict outcomes vs tools that identify smart traders"
- Universal contempt for paywalled / fixed-match / "we hit 80%, subscribe!" sites

**Insider gap found in research** (KuCoin Aug 2026 article): "No rigorous, peer-reviewed academic study has directly compared the Brier scores of prediction markets with those of Opta/538 during the 2018 and 2022 World Cups." → A public Brier-score scoreboard vs Opta + Bet365 is genuinely novel; nobody owns this turf yet.

---

## Phase 1 — Live in-game swing chart + Public scoreboard

**Goal:** Make the site the place people open during every match (swing chart) and the public scoreboard for forecast accuracy. The combination — feature plus credibility framing — creates a moat no competitor currently fills.

**Effort budget:** 4-5 days of build, broken into research-validated milestones below.

---

### Part A — Live in-game swing chart

#### What it is
During a live match, a line chart that updates every minute or two showing:
- Home win probability (emerald line)
- Draw probability (slate line)
- Away win probability (orange line)

Goals push lines, red cards crash them, time decay flattens to 100% certainty at FT. Modelled on FiveThirtyEight's 2018 chart, the most-loved feature their audience never got replaced.

#### The maths — established methodology

The standard live-WP approach (used by Sportmonks/Opta for Amazon Prime Video; reference implementation by ASA / Tyler Richardett; also dashee87.github.io and inpredictable):

```
Given current state at minute t:
  home_score, away_score, t_remaining, red_card_diff
  pre-match lambdas: λ_home, λ_away  (already produced by our Dixon-Coles)

1. Compute per-minute scoring rate from full-match λ:
     λ_h_per_min = λ_home * (state_adjustment) / 90
     λ_a_per_min = λ_away * (state_adjustment) / 90
   state_adjustment accounts for:
     - red cards (~0.7x for short side, 1.2x for opposition)
     - score state (trailing teams slightly more aggressive — inpredictable
       confirmed this is mostly TEAM STRENGTH bias, so we can keep it small)

2. Monte Carlo: simulate t_remaining minutes, N=10,000 times.
   Each sim, per minute, per team: Bernoulli(λ_per_min) for a goal.

3. Tally final scores → P(home_win), P(draw), P(away_win).

4. Push the (t, p_home, p_draw, p_away) tuple to the frontend.
```

**Why this is buildable for us:**
- We already produce λ_home and λ_away for every match via Dixon-Coles
- Our tournament simulator already does Monte Carlo at 20k iters in ~13s — a single-match 10k-iter sim is sub-second
- Existing `prediction_inputs.py` does the model assembly we can reuse

**Two methodological choices worth flagging:**

| Choice | Option A (simpler) | Option B (sharper) |
|---|---|---|
| Per-minute rate | Constant λ/90 | Time-varying λ (research: goals are slightly more likely 60-75min, less so 0-15min) |
| State adjustment | Score-aware (trail boost) | Plus xT momentum (we don't have live xT) |

Recommend A for v1. Inpredictable showed B's marginal accuracy gain is mostly noise without live possession/xT data, which we don't have.

#### Data dependencies — the live feed

**Required:** minute-by-minute updates of {score, elapsed_minute, red_cards}.

**Option 1 — api-football.com `/fixtures?live=all`** (recommended)
- We ALREADY have `API_FOOTBALL_KEY` in production env (used by lineups/injuries/squad_xg)
- Endpoint returns elapsed minute + score + recent events
- Free tier: 100 req/day — TIGHT but workable with smart polling
  - Pre-match: 0 requests
  - Live: 1 request every 60 seconds (90 requests per match)
  - WC2026 has 1-2 concurrent matches max at peak → ~90-180 req/day during peak group-stage days
  - Knockout days: 1 match at a time = 90 req/match
- **Action required:** verify current tier in api-sports dashboard; might be free, might be paid already — needs human check
- Paid plans: $19/mo for 7,500 req/day (covers everything trivially)

**Option 2 — football-data.org** (backup)
- We have `FOOTBALL_DATA_KEY` already
- Slower update cadence (90-second polling typical)
- Free tier is more generous (10 req/min, no daily cap)
- Less granular than api-football for live events

**Option 3 — Reza Rahiminia's WC2026 free API** (https://worldcup26.ir)
- No API key required for reads
- Real-time updates during the tournament
- Unknown SLA / reliability — community project
- Could be a fallback if both above fail

**Recommendation:** Primary api-football, fallback football-data.org. Cache aggressively, skip the request when nothing has changed.

#### Real-time delivery architecture

Two options. Both fit the existing FastAPI + Next stack:

**Option 1 — Server-Sent Events (SSE)** ← recommended
- One-way server → browser. Perfect fit (the user doesn't send anything).
- `sse-starlette` package, ~50 LoC integration.
- Auto-reconnect built into the browser's `EventSource` API.
- Keep-alive pings every 15s to defeat proxy idle-timeouts.
- **Infrastructure tax (researched):**
  - `nginx-proxy-manager` (we use this) needs `X-Accel-Buffering: no` response header to stop buffering the stream
  - If we ever put Cloudflare in front, same header is mandatory; otherwise Cloudflare buffers and the client never sees the stream
  - `proxy_read_timeout 86400s` on the SSE location

**Option 2 — WebSocket**
- Two-way, overkill for read-only chart.
- FastAPI has native support. More complex on the proxy side.
- Reject for v1.

**Option 3 — Plain polling**
- Frontend polls `/match/<id>/live` every 30s.
- Simplest. Higher backend load. Slower UX.
- Reject — we should ship the good version, not the easy one.

**Decision:** SSE via sse-starlette. Single endpoint `/match/<id>/live-stream` emits `wp` events with `{ t, p_home, p_draw, p_away, h_score, a_score, last_event }`.

#### Frontend: chart library

**Current convention (verified by inspecting `frontend/components/viz/`):**
- Three hand-rolled SVG components: `GoalsDistribution.tsx`, `SurvivalFunnel.tsx`, `TeamRadar.tsx`
- **No chart library installed** (no recharts, visx, d3, victory, nivo)
- This is deliberate — keeps the bundle slim (FCP measured 1.28s)

**Decision matrix:**

| Approach | Bundle size | Effort | Animations | Pros / Cons |
|---|---|---|---|---|
| Hand-rolled SVG (existing pattern) | 0KB | 6-8 hrs | Manual via CSS transitions | Matches site convention; full control; nothing extra to learn |
| **Recharts** | ~15-25KB gz | 2-3 hrs | Built-in | Industry standard React+D3 wrapper, but introduces dependency |
| Visx | ~15KB | 5-6 hrs | Manual | Lower-level, steeper learning curve |

**Recommendation:** Stay hand-rolled SVG. The chart is just three smoothed lines with a moving x-axis — about 80 lines of SVG. We already have the in-house style for sports viz. Avoids a new dep and matches the existing aesthetic. Saves ~20KB bundle.

#### Visual design (researched against FiveThirtyEight + Dimers references)

```
┌─ Match: Mexico vs South Africa ───────  87' 1–0 ─────────┐
│                                                          │
│ 100%                                                     │
│  ─ ─ Mexico  ───────                ▲ GOAL Mex 12'        │
│      Draw       ╲───────────────╲                        │
│  50%                                                     │
│      South Africa   ───────────────────                  │
│   0%                                                     │
│  0'    15'    30'    45'    60'    75'    90'+           │
└──────────────────────────────────────────────────────────┘
```

- Three colored areas (or lines), 0→100% y-axis
- Major events as dots/markers (⚽ goal, 🟥 red card)
- Sticky top: current minute + score
- Mobile-first; 320px wide must work
- "Now" indicator (vertical line) on the current minute
- Tap any minute to see the WP at that point

#### Edge cases to handle (research-confirmed)

1. **Half-time / extra time** — feed reports `HT`, `ET1`, `ET2`, `BT`; need to map to elapsed minutes correctly.
2. **Stoppage time** — minute reads `45+3` etc. Our state needs to ingest this.
3. **Feed lag** — api-football typically 30-90s behind broadcast. Disclaim it: "Updates ~1 min behind".
4. **Feed gaps** — sometimes goes silent for 5+ min. Last-good-state pattern.
5. **Wrong-team event** — feed occasionally mis-attributes goals. Show source link.
6. **Pre-match state** — show pre-match probabilities flat until kickoff.

#### Sharing — viral mechanic

- "Save this moment" button generates a static snapshot at the current minute.
- Image generated server-side (we'd use Next 14's `ImageResponse` from `next/og`).
- Shareable URL: `/match/<id>/wp/<minute>` → renders the chart up to that minute + OG image.
- Twitter / WhatsApp share text auto-includes "Australia at 8% — see how it unfolded"

This is the unsung accelerator. The single screenshot of the moment Iceland beat England in 2016 was 538's biggest acquisition driver for soccer.

---

### Part B — Public scoreboard vs Opta + Bet365

#### What it is

Reframe `/performance` (currently model-only) as the comparison leaderboard:

```
┌─ WC2026 Forecast Accuracy — Group Stage ─────────────────┐
│                                                          │
│  RANK  FORECASTER             HIT RATE   BRIER   ROI     │
│   1    👑 wc26.tinjak.com     64% (16/25) .184    +12.3% │
│   2    Opta supercomputer     56% (14/25) .201       —   │
│   3    Bet365 implied         52% (13/25) .218    -1.4%  │
│   4    Coin flip               48% (12/25) .250       —  │
│                                                          │
│  Last updated: 19 Jun, 22:30 AEST.   How we score this →  │
└──────────────────────────────────────────────────────────┘
```

#### The data sources

**Our model's probabilities:**
- Already stored in `PredictionSnapshot` table (locked in pre-kickoff for every match)
- Scored after FT with proper RPS / Brier / log-loss in `/performance`
- ✅ Done

**Opta's probabilities:**
- Published in articles at theanalyst.com (per-group + overall)
- NOT in a structured API — need to scrape
- **Implementation cost (researched):**
  - One scrape per matchday × 12 groups + tournament page = ~5 scrapes per matchday
  - Parse with BeautifulSoup against table-of-numbers pattern (their format is consistent within a tournament)
  - Risk: Opta could update numbers mid-tournament; need versioning
- **Schema:** store as `competitor_predictions` table with `(forecaster, match_id, p_home, p_draw, p_away, snapshotted_at)`
- Score after FT same as our model

**Bet365 implied:**
- Already in `OddsCache` from the existing odds feed
- Convert decimal odds to probabilities (de-vig with Shin method — we already do this in `backend/betting/market.py`)
- Snapshot at closing line (we already capture this in `clv.py`)
- ✅ Effectively done

**Coin flip / chalk baselines** — trivial calculations to include for context.

#### The scoring methodology — pedagogically defensible

Three metrics, explained in plain language on the page:

1. **Hit rate** — % of times the FAVOURITE (highest-probability outcome) wins. Intuitive. Imperfect.
2. **Brier score** — mean squared error of probabilities. Industry standard. Lower = better.
3. **ROI at flat stakes** — if you'd backed every favourite at the best available odds, what would you net? Real money meaning.

**Why this is genuinely novel:** KuCoin's Aug 2026 article explicitly confirms no peer-reviewed study has done this Brier comparison between Opta, 538, and market prices for prior World Cups. We're not just publishing; we're filling an information gap.

#### Honesty caveats (must include — credibility lives or dies here)

- "Opta numbers are scraped at the time of their article publication. If they update, we re-snapshot."
- "Bet365 implied probability is the closing line, de-vigged with Shin."
- "We don't cherry-pick. Every match the model predicted is in this scoreboard."
- "Our pre-match probabilities are locked in /how-it-works' linked archive — anyone can audit."

#### Press / SEO angle

After group stage if our model is winning:
- Headline blog: "We beat the Opta Supercomputer at the WC2026 group stage — here's the receipts"
- This is the natural shareability that turns the site into a brand
- Don't write it pre-emptively — wait for the result

---

## Cross-cutting infrastructure work both parts need

### Backend dependencies (additions)

| Package | Why | Cost |
|---|---|---|
| `sse-starlette` | SSE endpoint for live chart streaming | Free; Python pkg, +30KB |
| `beautifulsoup4` | Already installed — Opta article scraping | None |

### Frontend dependencies

| Package | Why | Cost |
|---|---|---|
| None | Hand-rolled SVG chart stays | 0KB bundle |

### Database changes

| Table | Why |
|---|---|
| `live_match_state` | Snapshot of current score/minute/events per live match. Allows chart replay. |
| `live_wp_history` | Per-minute WP tuple `(match_id, t, p_h, p_d, p_a)` for the chart. Bulk insert. |
| `competitor_predictions` | Opta + Bet365 + future forecasters per match |

All additive — `init_db()` + migrate.py handles. No back-compat concerns.

### Nginx-proxy-manager config (for SSE)

Custom config block on the FastAPI proxy:
```
location /match/ {
    proxy_pass http://wc26-backend:8000;
    proxy_buffering off;
    proxy_cache off;
    chunked_transfer_encoding off;
    proxy_read_timeout 86400s;
    proxy_set_header X-Accel-Buffering no;
    proxy_http_version 1.1;
}
```

Worth flagging: nginx-proxy-manager surfaces this in "Advanced" tab of the proxy host. One-time edit.

### Push notification integration (composes with existing VAPID system)

The push system already in place can be wired to fire on big swings:
- "Australia dropped from 35% to 8% — match on now"
- Dedupe by `match_id:big_swing` so one big-event push per match max

This is the layered acquisition feature — Phase 1 already amplifies the push system we shipped yesterday.

### SEO + sharing

- New shareable URL pattern: `/match/<id>/wp/<minute>` renders an OG image of the chart at that minute
- Search engines can index `/performance` for "WC2026 prediction accuracy comparison"
- New `/about/accuracy` long-form page explains methodology — SEO + credibility

---

## Phase 1 build sequence (research-validated)

This is the order I'd build it; each step verifiable before moving on.

| # | Step | Effort | Verifies what |
|---|---|---|---|
| 1 | Verify api-football tier in dashboard | 5 min | Free tier OK or need to upgrade? |
| 2 | Add `sse-starlette` to requirements, smoke-test SSE through nginx-proxy-manager | 1 hr | The streaming pipeline works end-to-end |
| 3 | Build the in-play WP simulator in backend — pure function, unit tests | 3 hrs | Math correctness |
| 4 | Wire the live-feed poller (api-football → `live_match_state` table) | 3 hrs | Feed integration; cache strategy |
| 5 | Wire the WP simulator into the live state → `live_wp_history` table | 1 hr | The pipeline produces real numbers |
| 6 | SSE endpoint `/match/<id>/live-stream` reads from `live_wp_history`, pings every 15s | 2 hrs | Real-time delivery |
| 7 | Frontend: hand-rolled SVG swing chart, `EventSource` client | 6 hrs | Visual + UX |
| 8 | Match page integration: show pre-match preview → live chart on kickoff → final result | 2 hrs | Match page complete |
| 9 | Save-this-moment OG image route | 3 hrs | Sharing mechanic |
| 10 | Opta scraper for one group as PoC | 3 hrs | Scraping pattern works |
| 11 | Run Opta scraper for all 12 groups + tournament page; backfill `competitor_predictions` | 1 hr | Data populated |
| 12 | Bet365 closing-line snapshot already in `clv.py` — wire to `competitor_predictions` table | 1 hr | Consistent schema |
| 13 | Comparison scoreboard on `/performance` — top of page | 4 hrs | Public scoreboard UI |
| 14 | Big-swing push notification trigger | 1 hr | Push integration |
| 15 | About/Methodology page explaining the comparison | 2 hrs | Credibility surface |

**Total:** ~32 hours of focused dev. Add 50% buffer for genuinely unknown unknowns → ~5 working days.

### Sequencing during pre-upgrade window

While owner is subscribing to api-football pro, work on items that DON'T need the live feed:
- A. SSE smoke-test through Cloudflare + nginx-proxy-manager (verifies infra)
- B. In-play WP simulator as a pure function with unit tests
- C. DB schema + migrations for `live_match_state`, `live_wp_history`, `competitor_predictions`
- D. Opta scraper + competitor_predictions backfill + comparison scoreboard UI (Part B ships in full)
- E. xG race chart shell that works against static historical data

The moment the pro key lands, swap the static feed for the live poller and the entire Part A lights up. ~70% of Phase 1 ships without the upgrade — Part B is fully shippable on free tier.

---

## Decisions taken 2026-06-19

1. **api-football pro tier ($19/mo)** — confirmed needed. Free tier (100 req/day) cannot support live polling during a busy matchday. Pro (7,500/day, 300/min) unlocks `/fixtures/events`, `/statistics`, `/players` at 15-30s update freq. Owner to subscribe; new API key drops into VPS env.
2. **Cloudflare is already in front** of wc26.tinjak.com (subdomain on tinjak.com behind nginx-proxy-manager). The SSE config MUST include `X-Accel-Buffering: no` to defeat both nginx and Cloudflare buffering. Documented in the nginx config block above.
3. **Opta scrape** — credit them, link the source article, scrape ~5 articles per matchday. Acceptable.
4. **Chart palette** — homepage stays emerald/orange. Decision: keep the same palette (Home = emerald 500, Draw = slate 500, Away = orange 500) for visual consistency with MatchCard. The emerald-on-emerald isn't a real conflict because the chart is the only emerald element on the match page.
5. **Phase 1 scope expanded** — given pro tier unlocks rich live data, ship the swing chart bundled with: live event ticker, possession bar, xG race chart, big-moment push triggers. Same polling pipeline, ~30% extra UI work for 2x the perceived value.

---

## What I would NOT include in Phase 1 (despite seeming related)

- ❌ Live xT / pressure / shot maps — needs paid feed data we don't have
- ❌ Audio commentary — voice quality bar is too high to ship in a week
- ❌ Multi-match dashboard ("see all live matches at once") — defer until we know one match works
- ❌ ML upgrade to live WP model (e.g. ASA's LightGBM regressor) — vanilla Monte Carlo restart works. Save ML for v2.
- ❌ User-account-based prediction tracking ("how YOU compare") — adds auth complexity; defer

---

## Phase 2 — Deferred (only after Phase 1 lands)

- **B: "What if" interactive bracket** — Monte Carlo with forced-result overrides. Generates shareable URLs.
- **C: "My team" personalised dashboard** — favourite-team bookmark drives push relevance + AU SEO.

## Phase 3 — Future / aspirational

- Local LLM analyst takes per value pick (Ollama install on VPS deferred)
- Affiliate links (deferred until owner has active affiliate programs)
- Email digests
- API access for other developers

---

## References (in case future me needs to re-research)

- **In-play WP methodology:**
  - https://sharmaabhishekk.github.io/projects/win-probability-implementation (ASA / Tyler Richardett model)
  - https://www.inpredictable.com/2014/07/on-probability-of-scoring-goal.html (state-adjustment bias caveat)
  - https://www.sportmonks.com/glossary/win-probability/ (Opta/Amazon Prime methodology)
  - https://theanalyst.com/eu/2021/11/live-win-probability/ (StatsPerform write-up)
  - https://allendowney.github.io/ThinkBayes2/chap08.html (Bayesian update after observed goal)

- **Data feeds:**
  - https://www.api-football.com/pricing (live fixtures endpoint, pricing)
  - https://github.com/rezarahiminia/worldcup2026 (free WC2026 API, no key)

- **Real-time delivery:**
  - https://github.com/sysid/sse-starlette (FastAPI SSE library, keep-alive)
  - https://community.cloudflare.com/t/using-server-sent-events-sse-with-cloudflare-proxy/656279 (X-Accel-Buffering header)
  - https://oneuptime.com/blog/post/2025-12-16-server-sent-events-nginx/view (nginx SSE config)

- **Chart libraries:**
  - https://blog.logrocket.com/best-react-chart-libraries-2026/ (comparison)
  - Existing site convention: hand-rolled SVG in `components/viz/`

- **Comparison baseline:**
  - https://theanalyst.com/articles/who-will-win-2026-fifa-world-cup-predictions-opta-supercomputer (Opta source)
  - https://www.kucoin.com/news/flash/how-2026-world-cup-win-probabilities-are-calculated-market-prices-vs-supercomputing-models (confirms gap in academic Brier comparison)
