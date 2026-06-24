# "I'm betting on them anyway" — research + product proposal

Written 2026-06-24, after the verdict block landed and the user asked
how we serve someone determined to back their country regardless of
edge ("they're going to bet on Brazil no matter what").

## The core insight

The default `/match` flow assumes the user is hunting for value. Most
World Cup viewers are not. They have a side, often by birth, and they
will bet on that side or stay home. The honest sharp-friend response
isn't "no edge, don't bet". It's "alright, since you're betting on
them, here's the smartest way to do it."

The product gap: we currently say "no clear edge, save the stake"
to a Brazilian opening the Brazil v Scotland page. That reads as "go
away", which is wrong both ethically (they're going to bet somewhere)
and commercially (they leave our page and bet blind on Bet365).

## What the academic literature actually says

### Home bias is real, measurable, and bookies already price it

Staněk 2017 (Judgment and Decision Making, 9,404 Czech ice hockey
matches, 1997-2014) found:

- At the SAME bookmaker odds, a bet on the home team has a winning
  probability **7 percentage points lower** than a bet on a neutral
  team. e.g. at odds of 2.00, a regular bet wins 48% of the time, a
  home team bet wins 41%.
- Coefficient was negative in 100% of 1,000 random samples, p < 0.05
  in over 99% of them. This is not noise.
- Replicated across the prior literature (Babad 1987, Babad & Katz
  1991, Massey et al. 2011, Forrest & Simmons 2008 on Spanish football,
  Feddersen et al. 2016 on the NBA).

**Why this matters for our product:** when a user wants to bet on
their country, the bookie has already moved the 1X2 line against them.
Telling them "1X2 has no edge" is true, but it's incomplete. The
right next sentence is "but there's value over here", not silence.

### Fans bet anyway, dissuasion doesn't work

- Wishful thinking (predicting outcomes favoured by emotional
  preference) persists with real money on the line (Simmons & Massey
  2012).
- Persists even when team allegiance is randomly assigned in lab
  conditions (Price 2000, Krizan & Windschitl 2007).
- Bias is not eliminated by knowledge of the bias.

**Product implication:** the user is going to bet. Our job isn't to
re-educate them out of fandom. It's to give them the highest-EV bet
**within the constraint of "I'm backing my team"**, so they walk away
better off than they would have on a generic sportsbook.

## The market landscape — where the edge actually lives

From football-bookie.com/football-betting-markets-guide (cross-checked
against FanDuel + Standard guides):

| Market | Typical margin | Honest read |
|---|---|---|
| 1X2 | 4-7% | Baseline. Heaviest action, sharpest priced |
| **Asian Handicap** | **3-5%** | **Lowest margin of any market** |
| Double Chance | ~5% | Covers 2 of 3 outcomes. Lower odds, safer |
| Draw No Bet | ~5% | Equivalent to AH 0. Refund on draw |
| BTTS | 5-7% | Hits ~50% of matches, predictable |
| Over/Under 2.5 | 4-6% | Decouples from match winner |
| Goalscorer (anytime) | 7-10% | Decent if you know the side |
| First Goalscorer | 20%+ | Lottery ticket. Avoid |
| Half-Time/Full-Time | 10%+ | Wide margins. Avoid |
| Correct Score | 12-18% | Lottery ticket. Avoid for stakes |
| Own Goal | random | Genuinely random. Avoid |

**Key takeaway:** when 1X2 has no edge, Asian Handicap and BTTS are
where to look. Both decouple from "did my team win" to "did my team
perform the way I think they will".

### Markets ranked by "fan knowledge advantage"

The markets where a passionate fan of team X plausibly has edge over
a generic bookie:

1. **Asian Handicap** — fans know whether their team usually wins by
   1, 2, or 3 goals against this calibre of opponent.
2. **BTTS** — fans know if their defence ships goals.
3. **Over/Under 2.5** — fans know if their team is high-tempo or
   defensive.
4. **Anytime Goalscorer** — fans know the team's main threat and
   penalty-taker.

The markets where a fan has NO edge but feels like they do:

1. Correct Score — variance dominates.
2. First Goalscorer — variance dominates.
3. Half-Time/Full-Time — defensive matchups distort routinely.

## Product proposal: the "Backing X" tab

A new tab on `/match` that activates when the user has signalled
they're backing one side. Activation paths:

1. Tap a "Backing Brazil" / "Backing Scotland" button under the team
   header (one click, no commitment).
2. Auto-suggest based on the team they followed via the follow-bell.
3. URL param `?backing=BRA` so a share link opens directly into the
   right mode.

### What "Backing X" shows

Three cards, ordered by expected value of the bet:

#### Card 1: The straight back

Either the 1X2 verdict block we already have (if there's edge), or:

> **No clear edge on the straight win.** Bookies have Brazil priced
> tight. If you're set on a straight winner bet, take it light. Stake
> around $5 on a $1,000 bankroll.

The honest acknowledgement. We don't pretend there's edge, we just
tell them the responsible size.

#### Card 2: The smarter bet (alternative market with edge)

The model already scores BTTS, O/U 2.5, and we can extend it cheaply
to Asian Handicap from the Dixon-Coles score grid we already build.
Pick the market on the team's side with the highest edge:

> **Brazil to win AND over 2.5 goals — better value here.**
>
> Model thinks Brazil scoring 2+ AND winning happens 55% of the
> time. Bookies are pricing it at 46% (paying $2.17). That's a
> 9-point gap.
>
> Stake $15 on a $1,000 bankroll. Take any price $2.17 or longer.

Or:

> **Brazil -1.5 Asian Handicap — better value here.**
>
> Model has Brazil winning by 2+ goals 38% of the time. Bookies are
> pricing it at 32% (paying $3.10). 6-point gap.

#### Card 3: The cover bet (if backing the underdog)

When the user backs the underdog, we show Double Chance:

> **Scotland not to lose — the safer way to back them.**
>
> Bookies are paying $1.80 for Scotland win OR draw. Combined that
> happens 56% of the time. Better than chasing the straight win at
> $5.50.

Or for a favourite the user thinks could be upset:

> **Want a hedge? Lay the draw at $4.20.**
>
> If Brazil win, you collect on your straight bet. If they draw, the
> lay covers. Only the small chance of Scotland winning loses you
> both.

### What we DON'T show

The lottery-ticket markets that look exciting but eat the bankroll:

- First Goalscorer (margins above 20%)
- Half-Time/Full-Time (10%+)
- Correct Score (12-18%)

If the user explicitly wants these, route them to the generic
"Markets" tab. The "Backing X" tab is curated; it omits markets
where they're guaranteed to lose to the margin over time.

### The "your team's story" line

Above the three cards, a single sentence on the model's read of how
Brazil are likely to play this match. Examples:

> Brazil are favoured to score 2+ and concede 0-1. Scotland's recent
> form away suggests a goal is on the cards.

> Scotland are heavy underdogs but defensive form is strong. The
> draw is live (25%).

This anchors WHY card 2 and card 3 are framed the way they are, so
the picks don't read as random alternatives.

## What we already have vs what we'd build

### Already in the codebase

- Dixon-Coles score grid (`backend/models/poisson.py`) — gives us
  joint probabilities for any score-derived market for free.
- BTTS + O/U 2.5 + 1X2 model probs (already in MatchPrediction).
- Multi-analyzer endpoint (`/betting/analyze-multi`) — gives us
  correlation-correct joint pricing for SGM legs like "Brazil
  win + over 2.5".
- Markets sheet (`MarketsSheet.tsx`) — shows every market with our
  fair odds; the data layer is there.
- Follow-bell wiring — knows which team the user has followed.

### What we'd add

1. **Asian Handicap pricing** from the existing score grid
   (~1h backend, pure math, no new data source).
2. **`/match/[id]/backing` route or `?backing=CODE` param** that
   switches the verdict block into the three-card mode.
3. **The three-card component** itself, reading from the same
   prediction payload (~3h frontend).
4. **Decision rules** for which of the three "smarter bet" patterns
   to show (table-driven from edge ranking).
5. **Per-team `?backing=` deeplink** from the team page so a
   follower clicks "I'm betting on Brazil" once and lands in the
   right view.

Total: about a day's work for the MVP, no new data dependencies.

## Voice rules for the "Backing X" tab

The same plain-English voice as the verdict block, extended for the
"you're going to bet, here's how" framing:

| Situation | Voice |
|---|---|
| Edge exists on straight win | "Lock in the straight win, model agrees you've got a real edge here." |
| No edge, alt market has edge | "Bookies have the win priced right, but they're slipping on the over. Here's the better bet." |
| No edge anywhere, backing underdog | "Long shot tonight. If you're set on it, the double chance gives you a draw cover." |
| No edge anywhere, backing favourite | "Bookies have your side priced fairly. Stake small, this one's heart not edge." |

The last band is the most important. We DO NOT lie. If there is no
edge, we say so directly. We DO give them the smartest way to act on
their heart bet, including a small responsible stake size.

## Responsible gambling overlay

Every "Backing X" card includes the stake suggestion (quarter-Kelly,
or a fixed 0.5% of bankroll when the model is -EV but the user is
betting anyway). The "heart bet" copy explicitly nudges the stake
down rather than up:

> If you're betting on your country regardless, treat it as
> entertainment. Stake around $5 on a $1,000 bankroll — the price of
> a beer, not next month's rent.

This serves two purposes:
1. Responsible gambling. We don't lure them into bigger heart bets
   because we know they're emotional.
2. Trust. The next time they have a real-edge match, they'll trust
   our stake suggestion because we proved we'd tell them to bet less.

## What I'm NOT proposing

- A separate "Fans" mode for the whole site. The taste pass on
  `/match` is the trojan horse; if Backing X works there it can
  graduate to a homepage entry point later.
- A live in-play "should I cash out" tool. Out of scope until the
  pre-match flow earns trust.
- Aggressive deeplinks like "you follow Brazil, here's your match".
  The user has to explicitly tap "Backing Brazil" each time. We are
  not pushing emotional bets at them.
- Removing the no-edge verdict from the standard view. If the user
  doesn't signal they're backing a side, they still see the honest
  "no clear edge" verdict.

## Implementation order

1. **Asian Handicap pricing** off the score grid (backend, ~1h).
2. **Best-alt-market picker** function — given a team code, return
   the highest-edge alternative market with our model fair price
   (~1.5h).
3. **`<BackingTab>` component** with the three cards (~3h).
4. **Backing entry point** on the match header — a small "Backing
   Brazil" / "Backing Scotland" toggle pair under each team name
   (~1h).
5. **"Your team's story" line** generator. Templated from lambda
   home/away + BTTS prob + O/U prob (~30min).
6. **Deeplink** from `/team/[code]` to `/match/[id]?backing=CODE`
   for users who land on the team page first (~30min).

Total estimated MVP: 7-8 hours.

## Validation gate

Before shipping the full feature, do a paper version of one match:

- Pick Scotland v Brazil. Write the three "Backing Brazil" cards by
  hand. Write the three "Backing Scotland" cards by hand.
- Show them to the user. Read the cards aloud. Do they sound like
  what a Brazilian / Scottish friend would actually want?

If yes, build the MVP. If no, fix the voice before any code.

## Reference: how this is different from existing sportsbook UX

- **Bet365** lets you "click the team" and shows you 200 markets in
  a list. No curation, no recommendation, no honest edge call.
- **FanDuel "Player & Game Props"** orders by popularity, not edge.
  The high-margin markets float to the top because they print money.
- **Pinnacle** has the sharpest odds but zero UX for the
  fan-betting use case. Their site assumes you already know what
  market you want.
- **Our angle:** the only product that openly says "you're betting
  on your country, here's how to do it best". No sportsbook can
  honestly do this because they make more money on the bad bets.
