# /match page taste pass — proposal

Research-backed proposal for repositioning the public match page from
"data-rich tool" to "credible analyst product". Written 2026-06-24
before any code is touched.

## What the best products actually do

Patterns I extracted from theanalyst.com (Opta), FotMob, Apple Sports,
Pinnacle Betting Resources, The Athletic editorial guidelines.

| Product | What they nail | What we should steal |
|---|---|---|
| **theanalyst.com (Opta)** | Stat-led milestone narrative ("Messi breaks World Cup goal record" not "Argentina 2-0 Austria"). The model has a public name — **"Opta supercomputer"**. Per-match preview pieces driven by it. | Give our model a name + a voice. Stat-led headline above the verdict line. |
| **FotMob** | Facts / Stats / Lineup tabs. xG visible everywhere (team / player / match). Mini-stat strip on top, deep stats one tap away. | Tabbed depth instead of infinite scroll. xG as universal currency. Trust signal: "live xG" branding. |
| **Apple Sports** | One question only: *"what's the score?"* Pre-game = start time + records + odds. No video, no clutter. **Failure mode: blank screen when nothing's on.** | Single-purpose framing. Avoid the empty-state trap. |
| **Pinnacle Betting Resources** | Editorial voice that's "unashamedly no-gimmicks". Treats the reader as an adult. Confident but caveated. | Voice: no exclamation marks, no "WINNING BET!", no promotional language. Authority through restraint. |
| **The Athletic** | Editorial guidelines explicitly forbid staff betting except betting-desk experts. Trust is a brand asset. | Show calibration / hit rate / sample size as a TRUST STRIP, not a footnote. |

## Our spin (what makes us different)

We are NOT a bookmaker — we don't take bets. That's the strategic
gift the existing /match page doesn't fully exploit:

- We can be **more editorial** than Pinnacle (no compliance copy needed)
- We can be **more data-driven** than ESPN (no broadcast ad inventory)
- We can be **more transparent** than every model-driven service
  (FiveThirtyEight, Stats Perform) because we have nothing to sell

That means our differentiator should be: *the take you'd get from a
sharp friend who runs the numbers and tells you straight.*

## Proposed /match page architecture

Three layers, every one visible without scrolling on a phone.

### Layer 1 — The Verdict (above the fold, mobile-first)

```
─────────────────────────────────────────
                                        
   ARG -185   AUT +450   DRAW +320      
                                        
   Argentina · 64% to win                 
                                        
   ──────────────────────────────────   
                                        
   📈  +6.2% edge vs market consensus   
   The model rates Argentina shorter     
   than the books. Smart money pick.    
                                        
   Verdict: BACK · 1.2u stake (Kelly)   
   Fair price: $1.55                    
                                        
─────────────────────────────────────────
```

One sentence that tells you what to do, why, and how much. Everything
else is supporting evidence. Punter reads it in 5 seconds. If they
trust your earlier picks, they're done.

**Trust strip** (always present, under the verdict):

```
─────────────────────────────────────────
  ⚖  This model · 58.3% hit rate on    
     +EV picks · 247 graded · last cal: 
     2h ago · CLV +1.4% rolling 30d    
  →  How is this calculated?            
─────────────────────────────────────────
```

The Trust Strip is the single biggest credibility win — Opta has the
supercomputer brand; FiveThirtyEight had the calibration histogram on
their About page. Right now we have neither visible to the punter.

### Layer 2 — The Why (one scroll)

Three cards, side-by-side on desktop / stacked mobile:

1. **Form & strength** — Argentina's last 5 with xG-for, Austria's
   last 5. A sparkline per team. ELO delta.
2. **Tactical context** — Knockout-stage stakes? Squad rotation
   likely? (we already compute this in match_context.py). Show ONE
   sentence with the most impactful factor.
3. **Market read** — What the books are pricing in vs us. Where the
   line moved since open. Sharp-money signal if Pinnacle has been
   anchored.

Each card has a small `?` icon explaining the metric (same pattern as
admin). Demystifies xG / ELO / CLV inline.

### Layer 3 — Drill down (tabbed below)

Following FotMob's pattern but renamed for our audience:

- **Edge** (default) — the full factor breakdown chart we already
  have. Renamed from "Factor Contributions" — "Edge" speaks to a
  punter; "Factor Contributions" speaks to a quant.
- **Form** — recent results, sparklines, key absences (currently
  Players to Watch — keep this; great signal).
- **Markets** — every market we model (1X2, over/under, BTTS,
  goalscorers), with edge % vs market avg.
- **Calibration** — the model's hit rate ON SIMILAR MATCHES (this
  matchday/this venue/this style). Trust signal at the drill level.
- **History** — H2H, last meeting summary.

Five tabs max. Anything beyond gets a `Less prominent`. Apple Sports
discipline.

## Voice + copy guide (the editorial pass)

The biggest visual change is small; the biggest read-feel change is
the voice rewrite.

**Verdict line patterns** (templated, generated server-side from
the model's outputs — not LLM):

| Edge band | Voice | Example |
|---|---|---|
| > +8% | confident, brief | "Strong back — model has Argentina 6% shorter than fair." |
| +3 to +8% | measured | "Lean Argentina — small edge, sample's modest." |
| -3 to +3% | honest | "Pass — fair pricing, no edge here." |
| < -3% | contrarian | "Avoid — Argentina overpriced. Market sees something we don't." |

**Headline patterns** (always stat-led, never score-led):

- Pre-match: *"Argentina's 8-match unbeaten run meets Austria's
  zero clean sheets in 2026."*
- Live: *"Messi's 9th World Cup goal puts Argentina on bracket-watch."*
- Post-match: *"Austria's two missed pens cost them more than the
  scoreline shows."*

Stolen from Opta. No "BIG MATCH!" energy.

**What to KILL from current voice:**
- Emoji as decoration (keep functional ones: ⚽ red ✕ for shootout)
- ALL CAPS for emphasis (use weight + size)
- "Predicted" / "Forecasted" — every verb is overconfident. Use
  "model rates", "edge", "lean".
- Decimal odds with 3+ places ($1.847) — round to 2 ($1.85)

## Visual / typography

The current /match page has 3-4 visually equivalent layers competing
for attention. Premium products use ~6 distinct text sizes / weights:

| Role | Size | Weight | Where |
|---|---|---|---|
| Hero (the headline number) | 36-48px | 900 | Verdict probability, key score |
| Verdict line | 18px | 700 | One sentence under hero |
| Section heading | 13-14px | 700, uppercase, tracked | Tab labels, card titles |
| Body | 14-15px | 500 | Cards, explanations |
| Stat number (inline) | 14px | 700, tabular-nums | Inside text |
| Caption / metadata | 10-11px | 500, slate-500 | Timestamps, footnotes |

Currently we use 3-4 sizes. Bumping to 6 with disciplined hierarchy
costs nothing and is the single biggest "professional vs indie" lever.

**Colour discipline:**

- Brand accent: emerald (keep)
- Edge positive: emerald, edge negative: rose
- Warning: amber
- Everything else: slate scale (50 / 200 / 400 / 500 / 600 / 700)
- **Forbid:** more than ONE non-grayscale colour per card

**Iconography:**

Replace emoji decorations with Lucide icons (already trivial to
install). Keep ⚽ for goals because it's universally recognised.
Replace 🟨 / 🟥 with small filled rectangles (Apple Sports style).
Replace section header emojis (📈, ⚖) with Lucide.

## What changes vs current /match

| Section | Current | Proposed |
|---|---|---|
| Top | Match header + status pill | **Verdict block** with 1X2 odds + edge + one-sentence call |
| Below header | Score / kickoff | **Trust strip** with model hit rate + CLV + sample |
| Next | Multiple stacked tiles | **3-card Why row** (Form, Context, Market) |
| Drill | Long scrollable list | **5-tab drill** (Edge / Form / Markets / Calibration / History) |
| Voice | "Predicted", "Forecasted" | "Model rates", "Edge", "Lean" |
| Type | 3-4 visual layers | 6 disciplined layers |
| Icons | Emoji decorations | Lucide + functional emoji only |

## Model branding (the Opta supercomputer move)

The Opta supercomputer is a useful brand because people remember it
and the company can roll out updates against a recognisable name
("the supercomputer's been updated"). We should do the same.

Three name candidates, with rationale:

1. **MAESTRO** — Model for Anticipating Event Strength, Tactics, Rotation, Outcomes. Has musical/conducting feel that fits "running the numbers". Easy to anthropomorphise ("MAESTRO sees Argentina at 64%").
2. **The Reference** — Borrowed from Pinnacle ("the reference price"). Quietly authoritative. Less character but more credible.
3. **Sharp** — Single word, betting-native term, brand-yourself-as-the-sharp move. Risk: too generic / collides with "sharp money" usage.

My pick: **MAESTRO**. Has personality, ours not theirs, room to grow
("MAESTRO's calibration", "MAESTRO's pick of the day", "Ask MAESTRO").

## Implementation order

Shipping discipline — one PR per layer so each lands as a visible
improvement and you can redirect after seeing it real.

1. **Verdict block + trust strip** (highest visible payoff, ~2-3h)
2. **Voice rewrite** (templated verdict lines + headline copy) (~1h)
3. **Type + colour discipline pass** (every card touched, ~2h)
4. **Lucide icons** + emoji audit (~30min)
5. **3-card Why row** refactor (~2h)
6. **5-tab drill** restructure (~3h)
7. **MAESTRO branding** (logo / mark / mentions) (~2h)

Total: a focused 2-3 day pass. If you redirect after #1 the rest gets
a different shape, which is why I'm proposing this as a doc not just
shipping it.

## What I am NOT proposing (deliberately)

- A complete redesign of every public page (other pages get their own
  pass — /match is the highest-traffic decision surface to prove
  the direction first)
- A dark/light mode toggle (dark works for the audience)
- A native app rewrite (PWA is fine for now)
- Anything that hides the data behind logins / paywalls (free tier is
  the trust-building phase; paywall comes post-WC per [[wc2026-pivot-strategy]])
- Animation flourishes (premium products are restrained on motion —
  use it ONLY for state changes like goals)

## Validation plan

After shipping #1 (Verdict + Trust Strip):

- Show two pages side-by-side on phone (old vs new)
- Read the new verdict line aloud — does it sound like a real take?
- Open both on desktop — does the new page feel like a different
  category of product?

If "yes" on both: ship #2 onwards. If "no": back to research, this
proposal is wrong.
