# Post-WC2026 Pivot Plan

Written 2026-06-22. WC2026 kickoff 2026-06-11; final 2026-07-19. After the
final we have a roughly 6-week window before Aus domestic + EPL preseason
kicks off, and that is the window for the pivot. This doc covers three things:

1. Multi-competition architecture (what code stays, what becomes generic).
2. What admin grows into (right now /admin is one-person-with-a-token).
3. Real-money path in Australia (legal constraints + which revenue models
   actually work for a small Aus-licensed operator vs which get the site
   ISP-blocked by ACMA).

No code changes here. This is the plan we work from.

---

## 1. Where the engine already is competition-agnostic

What the WC2026 build already gets right for a multi-comp future:

- Poisson + Dixon-Coles + ELO + form blend (`backend/models/`) takes lambdas
  in, gives match probabilities out. Doesn't care if the lambda came from a
  WC team or a Heidenheim-Augsburg Bundesliga line.
- Market pricing (`backend/betting/markets.py`, `sgm.py`, `ev.py`, `kelly.py`)
  is pure score-grid math — totally competition-blind.
- The `Match` table already has `id`, `kickoff`, `venue`, `home_code`,
  `away_code`, `home_score`, `away_score`, `status`. None of that is WC-only.
- Prediction logging + calibration + Brier scoring works off any list of
  Match rows. The Performance page is reusable as-is.
- Frontend match cards / value board / acca builder / SGM pricer are all
  ignorant of "which competition".

What's WC-specific and has to become generic:

- `Match.group` (column) + `Match.matchday` (column) encode WC group-stage
  structure. EPL doesn't have groups; a season has rounds + a league table.
- `backend/models/group_predictor.py` and `knockout_predictor.py` are
  competition-format code. Knockout brackets, third-place-qualify rules, the
  tournament-projection sim — all WC-specific format logic.
- Hardcoded team list (48 nations, the `Team` table seed, FIFA codes,
  set-piece data, manager map, `TEAM_IDS` for api-football).
- Routes: `/groups`, `/match3`, `/bracket`, `/winner`, `/scenarios` —
  WC-only concepts.
- The /how-it-works page reads as "this is a World Cup model".
- Daily seed (`backend/db/seed.py`) loads the WC fixtures from openfootball
  worldcup.json.

## 2. Multi-competition architecture

The model is the keeper. The schema needs two new entities + a column on
`Match`. The frontend needs a competition switcher and a small route reshuffle.
The bracket / group-stage routes become per-competition format plugins.

### Schema additions

```
competitions (
  code        primary key,        # e.g. "wc2026", "epl-25-26", "ucl-25-26"
  name,                           # "2026 FIFA World Cup", "Premier League 2025-26"
  country,                        # "INT", "ENG", "AUS"
  federation,                     # "FIFA", "FA", "FFA"
  format,                         # "tournament-groups-knockout" | "league" | "league-cups"
  season_start, season_end,
  active                          # bool — which comps the cron jobs touch
)

seasons (                         # league cycles within a competition
  id pk,
  competition_code fk,
  label,                          # "2025-26"
  start, end
)

# Match gets:
ALTER TABLE matches ADD COLUMN competition_code TEXT;
ALTER TABLE matches ADD COLUMN season_id INTEGER NULL;
ALTER TABLE matches ADD COLUMN round_label TEXT NULL;  # "Round 1", "Quarter Final"
# `group` and `matchday` stay but become NULLable + only filled for tournament formats.
```

### Format-plugin pattern

`backend/models/formats/` becomes a small registry:

```
formats/
  base.py              # FormatPlugin protocol (table view, simulate, bracket)
  groups_knockout.py   # WC + Euros + Asia Cup etc.
  round_robin.py       # EPL, La Liga, A-League — league table + remaining-fixture
                       # sim for finals/relegation projections
  swiss_then_knockout.py  # New UCL + ECL format
```

The plugin owns: how to render standings, how to simulate the remainder of
the competition, what knockout/playoff bracket (if any) is shown. The
prediction engine doesn't change.

### Importers per competition

`backend/data/importers/openfootball_competition.py` already exists in
spirit (we use openfootball CC0 for WC fixtures). Extend to a directory:

```
importers/
  openfootball/
    wc2026.py          # current, becomes one of many
    epl_25_26.py
    bundesliga_25_26.py
    laliga_25_26.py
    ucl_25_26.py
    aleague_25_26.py
    mls_2026.py
  api_football/
    epl_results_lineups.py     # the harvester pattern we already run
    aleague_results_lineups.py
```

Cron stays the same — `backend/data/refresh.py` iterates `competitions.active`
and calls each importer. Quota budget already exists; just add a per-comp
priority so the cheap WC importers don't starve the EPL ones.

### Frontend routes

`/c/[code]/` becomes the new shape. Existing routes stay as a default that
redirects to `/c/wc2026/...` (so old links don't break).

```
/                          → competition switcher (or default to most-active)
/c/wc2026/                 → matches list for WC
/c/wc2026/value
/c/wc2026/bracket          # tournament-format only — format plugin renders
/c/epl-25-26/              → matches list for EPL
/c/epl-25-26/table         # league-format only — format plugin renders
/c/epl-25-26/value
/match/[id]                # unchanged — match id is globally unique
```

The sidebar nav becomes two-tier: pick a competition, then pick a section.
The codebase doesn't need a routing rewrite — Next.js dynamic routes handle
this with one new `[code]` segment. ~80% of components keep working without
modification once they read `competition_code` from a context.

### Migration sequencing (the 6-week window after the WC final)

| Week | Work |
|---|---|
| 1 | Schema migration: `competitions`, `seasons` tables; backfill `competition_code='wc2026'` on every existing Match row. WC2026 still serves identically. |
| 2 | Format-plugin refactor: extract `group_predictor` + `knockout_predictor` behind the `FormatPlugin` interface. Add `round_robin.py`. Tests stay green. |
| 3 | First non-WC importer (EPL 25-26 via openfootball). Backfill 2024-25 results so DC + ELO have a base. Confirm calibration page reads sanely. |
| 4 | Frontend `/c/[code]/...` routing + competition switcher. Old routes redirect to `/c/wc2026/...`. |
| 5 | Add Bundesliga + La Liga + UCL importers. Cron runs all four nightly. |
| 6 | Buffer / on-call. Aus domestic (A-League) added if time. |

This sequencing is non-destructive — at no point does WC2026 stop working.

---

## 3. Admin: what it grows into

Current admin (per memory `wc2026-admin-dashboard`): token-gated /admin with
quota gauge + feed health + queue + pause toggle. Single env-token auth.
Built for one operator running one competition.

For a multi-comp + paid-product future it needs:

### Auth
- Multi-user with roles: `owner`, `editor`, `read-only`.
- Email + magic-link login (no passwords). `lucia-auth` or `auth.js` v5
  with Stripe's customer id as the secondary identity.
- Audit log of every admin action (pause harvester, push manual override,
  publish a pick, edit copy).

### Per-competition surfaces
- Comp on/off toggle (cron picks up new comps + retires finished ones).
- Per-comp data feed health (right now `feed_health` is global).
- Per-comp calibration page so a sharper EPL model doesn't get its grade
  dragged down by a noisy A-League one.
- Per-comp value threshold tuning (the calibration-shrunk staking memory
  already proved EPL needs different thresholds than WC group stage).

### Subscriber + billing surfaces
- Subscriber list + state (active, past_due, cancelled, free-trial).
- Stripe webhook receiver (`/billing/stripe/webhook`) — already a known
  pattern from EarGuard / Code Most builds.
- Refund / comp / extend-trial actions.
- Churn dashboard (the LTV math in the OddsPapi research is the gate: if
  monthly churn >25% the sub model doesn't work — admin needs the read).

### Affiliate manager (Aus-licensed operators only — see section 4)
- Per-operator referral codes + per-comp landing URL templates.
- Click + conversion log (UTM + first-party fingerprint).
- Manual reconciliation against operator dashboards (Sportsbet, Pointsbet,
  TAB — they each have their own affiliate UI; we need a "what they say
  we got" vs "what we logged" view).

### Content + picks editor
- For paid subs, the picks need editorial polish — a one-line "why this
  pick" written in plain English. WYSIWYG that publishes a pick blurb
  attached to a `Prediction` row.
- Scheduled publish so picks appear at the same cadence (e.g. 12:00 AEDT
  every match day) instead of when the model happens to finish a run.

### Ops (already mostly in place)
- Harvester pause + quota.
- Force-refit DC.
- Backup-now button (wrap `scripts/backup-db.sh`).
- Deploy-from-here button is dangerous and we're not building it; deploys
  stay manual via the VPS.

### Auth migration sequencing
- Keep current env-token /admin alive through the pivot.
- Add `/admin/v2` behind magic-link auth.
- New admin features land on v2 only; v1 freezes to whatever ships first.
- Cut over once v2 has parity.

---

## 4. Real-money path in Australia

This is where I had to do real research because the wrong choice gets the
site ISP-blocked by ACMA, not just fined. The law that matters is the
Interactive Gambling Act 2001 (IGA) + 2017 amendments, administered by
ACMA. The 2026 "Stop the Gambling Ads" Bill is in parliament and may
further restrict promotion placement — design assuming the strictest
likely outcome.

### What's legal vs not, for an Aus-resident operator

LEGAL:
- Building a tipping / odds / model site for an Australian audience.
- Referring users to wagering services LICENSED in Australia (Sportsbet,
  TAB, Pointsbet, Ladbrokes AU, Neds, Bet365 AU, Unibet AU — full list on
  the ACMA register of licensed interactive wagering service providers).
- Running an affiliate programme with any of the above. Sportsbet, TAB,
  Pointsbet all run public affiliate programmes (sportsbetaffiliates.com.au,
  pointsbet.com.au/affiliates-legal).
- Charging a subscription for premium picks / tools / data. This is not a
  wagering service under the IGA; it's a content / SaaS product.

ILLEGAL (will get the site ISP-blocked):
- Referring users to OFFSHORE / unlicensed bookmakers. ACMA actively blocks
  affiliate marketing sites that funnel traffic to unlicensed operators.
- Offering in-play sports betting via a website (only via phone/in-person).
- Offering an online casino product. Period.
- Advertising banned services.
- Offering credit for online betting.

REQUIRED ON ANY WAGERING-ADJACENT SITE TARGETING AUSTRALIANS:
- 18+ markings and gambling-harm messaging.
- BetStop link (betstop.gov.au) on every page with wagering content.
- Gambling Helpline 1800 858 858 + gamblinghelponline.org.au reference.
- A privacy policy that complies with the Australian Privacy Act 1988 if
  collecting any personal data (email for subs counts).

### Revenue model rank (Aus-licensed only)

| Model | Aus legality | Realistic monthly rev at 1k DAU | Effort to start | Verdict |
|---|---|---|---|---|
| Subscription (premium picks / tools / alerts) | Clean — not a wagering service | $5k–$30k at 5–10% paid conversion at $15–30/mo | Stripe + magic-link auth + paywall route. Weeks. | Best fit. Builds on the publicly-graded track record. |
| Affiliate to Aus-licensed bookmakers | Clean — only via ACMA register | Highly volatile. CPA $50–$200 per qualifying signup; tiny without SEO scale | Apply to each operator, get approved, plumb codes. Weeks of admin per operator. | Layer-on revenue, not a foundation. |
| Sponsored content / featured operator | Clean if disclosed + only licensed ops | Small until you have audience | Sales work, not engineering | Defer until 50k+ MAU. |
| Data API / B2B feed | Clean | Niche. Either zero or one $5k/mo enterprise deal. | Build + sell. | Defer. Not the audience we have. |
| Run a sportsbook | NO — six-figure licence floor, regulated by State Govts | n/a | n/a | Not an option for us. |
| Affiliate to offshore books | NO — gets the site blocked | Tempting RevShare but illegal | n/a | Hard no. Not worth the risk to everything else. |

### Recommended path (everything free until Jan ~20 2027, then paid)

Strategic call (made 2026-06-22): the model stays 100% free through the
entire first half of EPL 2026-27. Three reasons:

1. By Jan 1 we have ~150 graded EPL predictions = a much sharper Brier /
   calibration sample than launching paid in Oct on ~80 games. Calibration
   IS the moat; thin numbers undermine the pitch.
2. Boxing Day + NYE is the densest bet-week of the Aus calendar (10+ EPL
   matches between Dec 26 and Jan 1, peak attention, everyone on holiday).
   Free product + viral specials during that window = max email-list
   acquisition.
3. Launching paid Jan 1 lands in the lowest-attention week of the Aus
   calendar (summer holidays + Big Bash + cricket + beach, EPL ignored).
   Better launch date is Jan ~20 — back-to-work week, school holidays end,
   EPL fixtures resume hard.

| Phase | Window | Action |
|---|---|---|
| Setup | Now (Jun) | Register Pty Ltd company + ABN. Sole-trader free; ~$500 for Pty Ltd. No GST registration needed until >$75k AUD annual rev. Pro-indemnity insurance ($800–$1500/yr — required if charging for tipping). Write + publish ToS, privacy policy, responsible-gambling page, refund policy. |
| Free + build | Aug 2026 – Jan 2027 | EPL 2026-27 fully free + ad-free. Model goes live with every pick locked + publicly graded. SEO compounds; trust compounds. No paywall, no friction. Site banner from day 1: "Free until Jan 20 2027 — early adopters get $9/mo for life". |
| Email capture | Aug 2026 onwards | One-field email signup on the value board + post-match-view: "weekly model report card + Boxing Day specials + early-adopter discount lock-in". This list is the only bridge from free-traffic-now to paid-conversion-Jan. Without it, Jan 20 is a launch into the void. |
| Xmas specials | Dec 2026 | Pick 2–3 of: (a) Boxing Day model accumulator — pre-built multi across the full Boxing Day EPL card, branded shareable card; (b) Year-in-review email — each user gets "model went X% on the EPL season-to-date, beat closing line on Y bets"; (c) Lock-in pricing — email-list signups before Jan 1 lock in $9/mo for life vs $15 standard; (d) Boxing Day "best value" notification blast. |
| Pre-launch infra | Nov–Dec 2026 | Stripe Checkout + paywall middleware + email-driven launch sequence built + tested. Magic-link auth so users can self-create accounts. Apple Pay + Google Pay (Stripe handles). |
| Paid launch | Jan 20 2027 | Single tier $15/mo or $99/yr. Early-adopter list gets $9/mo locked in. Pitch: full value board + push alerts + bet builder + history with CLV + multi-tournament. Free tier persists with limits (e.g. 3 picks/day visible, no alerts) so SEO + trust keep compounding. |
| First affiliate | Feb 2027 | Sportsbet (largest Aus operator, easiest onboarding). Add referral code per value pick that has a Sportsbet line. Disclose clearly. |
| Multi-operator | Mar–Apr 2027 | Add Pointsbet + TAB affiliate. Build admin reconciliation view (operator dashboards drift from your logs; need your own truth). |
| Annual upsell | Jun 2027 onwards | If sub conversion >3% of free traffic, push annual plan at $99 — 10x churn reduction is the whole LTV game (per OddsPapi research). |
| GST registration | When projected annual rev >$75k AUD | Stripe flips the invoicing flag once you tell it. Free + fast. |

### What kills the business

- Lying about track record. The publicly-graded calibration is the moat;
  the day someone catches a fudge, you're done. Keep the locked-prediction
  ledger and the Brier scoring even if subscribers never look at it.
- Going wider than Australia before the Aus business throws cash. Each
  jurisdiction has its own affiliate / gambling regime; cross-border is
  weeks of compliance per market for marginal upside.
- Building white-label sportsbook or offering credit. Not for us at any
  scale we will reach.

### What hands us an early advantage

- The model is genuine, the calibration is honest, the site already shows
  Brier vs Opta vs market. That is the EXACT trust signal the OddsPapi
  research says wins tipster subscribers.
- The codebase is fast, owned outright, no per-call data costs that bite
  at scale (Rising Transfers + openfootball + football-data.org are CC/
  free; the only paid line is the Odds API at ~$500/quota/month, which
  scales with users not with calls).
- Punters.com.au-class incumbents are racing-first; soccer + multi-comp
  punters are underserved on the Aus side.

---

## 5. The naming question (open)

`wc26.tinjak.com` is a tournament-specific subdomain. The multi-comp pivot
wants a proper second-level domain. Options to think about, not decide today:

- `tinjak.com` could host this as `/predictor/...` or `/punt/...` but it
  bundles unrelated projects together.
- A dedicated `<word>.com.au` with the Aus angle baked in — affiliates
  weight `.com.au` more, and it signals "this site is in your jurisdiction".
- Punters.com.au, Champion Data, Squiggle — the Aus convention is short +
  punchy + sport-coloured.

Not buying anything today. Surfacing the question because the pivot is the
right moment to pick the long-term identity before SEO compounds onto the
WC subdomain.

---

## 6. The thing we are NOT building

- A sportsbook.
- A casino.
- An in-play betting product (illegal in Aus over the internet).
- An offshore-affiliate funnel.
- A "VIP DM me for tips" model (regulatory grey + the IGA 2026 amendment
  may explicitly target these).
- Cross-jurisdiction launches before Aus pays the rent.

---

## References

- Interactive Gambling Act 2001 + 2017 amendments — https://www.acma.gov.au/about-interactive-gambling-act
- ACMA register of licensed interactive wagering services — https://www.acma.gov.au/interactive-wagering-providers
- BetStop self-exclusion register — https://www.betstop.gov.au
- Sportsbet affiliates programme — https://www.sportsbetaffiliates.com.au/
- Pointsbet affiliates T&Cs — https://pointsbet.com.au/affiliates-legal
- OddsPapi: 5 business models for monetizing sports data — https://oddspapi.io/blog/monetize-sports-odds-data/
- Stripe Australia fees + GST — https://stripe.com/au/pricing , https://stripe.com/resources/more/sole-trader-gst-in-australia
- Australia GST threshold — https://stripe.com/au/resources/more/the-australia-gst-threshold-explained-for-growing-businesses
