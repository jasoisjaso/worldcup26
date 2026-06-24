# Follow-match notifications — research
*Date: 2026-06-23. Scope: research only, no code changes.*
*Question: how do Google / FotMob / Apple Sports etc. do per-match
"follow this match" notifications so users get goals, red cards, full-
time score etc. without opening the app — and what would it take for
wc26.tinjak.com to ship the same thing?*

---

## 1. What we already have in the codebase

Web Push works end-to-end today. Foundations:

* `backend/db/models.py::PushSubscription` — `(endpoint, p256dh, auth,
  user_agent, last_used, failed_count)`. One row per browser. Survives
  deploys.
* `backend/db/models.py::PushSent` — `(dedup_key)` so the same event
  can't notify twice.
* `backend/api/routes/push.py::send_push(...)` — calls `pywebpush`,
  fans out to every subscriber, prunes 404/410, logs failures.
* VAPID keys live in env (`VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`,
  `VAPID_SUB`).
* Two trigger types fire today:
  1. `backend/data/prediction_logger.py` — value pick (`Value pick:
     Brazil ... edge +6.2% · 56% model`).
  2. `backend/data/fetchers/live.py` — big-swing alert (≥15pt WP move,
     `Brazil 1-0 Mexico — Brazil up to 78% live — 67'`).
* `frontend/components/common/PushSubscribe.tsx` +
  `NotificationBell.tsx` give a generic "turn on notifications" toggle.

**The critical gap:** `send_push` fans out to *every* subscriber.
There's no per-user filtering at all — no per-team, per-match, or
per-player gate. Adding a "follow this match" button means we need:

  (a) a subscription model that knows which devices want which match,
  (b) event-trigger dispatch (goal / red / HT / FT / suspension / lineup),
  (c) UI to subscribe from a match card without opening the app first,
  (d) a survival story on iOS (tightest platform).

The rest of this doc is the research backing each of those four pieces.

---

## 2. How the market does it — five reference implementations

### 2a. Google (Knowledge Panel + Google app)
Source: support.google.com, Google Pixel reddit thread, lumsx-bbb fast-
dispatch guide.

* User searches a team or match → Google Search shows a knowledge
  panel with a **Follow** button.
* Tapping Follow registers the team/match in the user's Google
  Assistant "My Sports" list.
* Google app then pushes goal / red / FT / important game updates as
  native notifications, with the score live-updating in the
  notification body (uses native Android notification re-render APIs).
* Granularity is per-team and per-match. The "follow this match" entry
  point appears on any match panel — you don't need to follow the team.
* User-side controls live in **Google app → Settings → Notifications →
  Sports** (per-sport on/off, per-team list).

**Takeaway:** the *entry point* is the panel button. The user does NOT
have to install an app or land on a settings page first. That's the
"Google style" the user is asking about.

### 2b. FotMob (20M users, gold standard for soccer)
Source: App Store listing + macrumors article.

* Two-axis subscription model:
  - **Per-team** — tap heart on team page → goal/red/lineup/FT for every
    fixture, every competition.
  - **Per-match** — long-press a fixture in the schedule → same event
    types but scoped to that one fixture.
* Event types user can toggle: goals (split by your team vs opponent),
  red cards, kickoff, lineup published, full-time, *VAR review*,
  *substitution involving favourite player*.
* Uses **Apple Live Activities** on iOS 16.1+ — score appears live on
  the Lock Screen + Dynamic Island, dressed in country colours during
  WC. (Native iOS only — not available to PWAs.)
* Home Screen widgets show live score on a 30-60s refresh.
* Reviews flag two failure modes worth pinning in our design:
  - **Wrong-player goal attribution** (Cole Palmer goal credited to
    Christopher Nkunku). Implies they read api-football event payload
    directly and the event.player.id can be wrong on fast-developing
    plays. Mitigation: confirm-on-second-tick before notifying.
  - **Late red-card reporting** (4-28 Sounders/LAFC red cards from
    minute 18 not pushed until after FT). Implies they batched events
    or hit a queue. Mitigation: per-event ack queue, not periodic.

### 2c. Apple Sports app
Source: support.apple.com.

* Per-team follow ("My Sports"). No per-match follow — Apple's bet is
  that you'll follow your team and never need finer granularity.
* Live Activities for *every* followed team's live games — Lock Screen
  + Dynamic Island + Apple Watch.
* "More Frequent Updates" toggle in Apple TV → Live Activities lets
  power users opt into higher refresh rate (cost: battery).
* No web/PWA equivalent — Live Activities is a closed iOS-native API.

### 2d. Sofascore / ESPN / LiveScore (the long tail)
Source: LiveScore help, Sofascore site, ESPN scoreboard.

* All three offer per-team and per-match alerts.
* LiveScore is the most granular — per-sport toggle, then per-event-type
  within sport (goals only, vs goals + cards + lineups, etc.).
* All three currently use **native apps** for Live Activities and ship
  PWA-like web pages too, but the web page only supports basic Web Push
  (not Live Activities).

### 2e. Bookmaker pattern — bet365 Live Match Alerts
Source: extra.nj.bet365.com.

* Subscribe only fires once a bet is placed on the match — built into
  the bet slip flow.
* Event types fixed (kickoff, goal, red, FT) — no granular controls.
* Quiet hours respected.

**Relevance to us:** the bookmaker pattern is "you have skin in the
game, here are the updates". That maps perfectly onto our model multis
and value picks — when a user adds a pick to their accumulator, we
*automatically* subscribe them to the underlying match events. Zero
friction. (Not just a follow button — an implicit follow on bet add.)

---

## 3. What event types actually matter — convergent list

Cross-checking FotMob + Apple Sports + bet365 + LiveScore, the
default-on event set for a followed football match is:

| Event | Default on? | Notes |
|-------|-------------|-------|
| Kickoff | yes | Sometimes a "starting in 15 min" pre-roll too |
| Lineup published | optional | FotMob default-off, ESPN default-on |
| Goal (any) | yes | Title carries new score; body carries scorer + minute |
| Red card | yes | Split into red vs second-yellow on Sofascore |
| Penalty awarded | optional | Sofascore default-on, FotMob default-off |
| Penalty missed | optional | Tied to penalty awarded toggle |
| Half-time score | yes | One push at HT, body = "HT 1-0" |
| Full-time score | yes | One push at FT, body = "FT 2-1" |
| Match suspended | ALWAYS ON, no toggle | What FRA-IRQ should have triggered |
| Match resumed | ALWAYS ON, no toggle | Match-not-finished users care |
| VAR review | optional | Sofascore/FotMob, default-off |
| Big chance | optional, FotMob only | Sourced from xG threshold |
| Substitution (favourite player) | requires per-player follow | Out of scope until we add player follow |

**Reasonable starter set for us (no per-event toggle in v1):** Kickoff,
goal, red, HT, FT, suspended, resumed. That's 7 trigger types — enough
to feel complete, small enough to ship.

---

## 4. iOS is the hard wall — must address before any FE work

Source: magicbell.com PWA limitations guide, mobiloud.com PWA iOS guide.

### What works today (iOS 16.4+, March 2023 onward):
* Web Push API
* VAPID-based subscriptions (same plumbing we already use)
* Background delivery (notification arrives even when browser closed)
* Notification actions (buttons in notification)
* Badging API (number on home-screen icon)

### What does NOT work and won't anytime soon:
* **Live Activities** (lock-screen live score widget) — native-only.
  This is the biggest competitive disadvantage vs FotMob/Apple Sports.
* **Background Sync / Periodic Background Sync** — PWA can't refresh
  data when closed.
* **`beforeinstallprompt` event** — no native install prompt; user
  must manually Add-to-Home-Screen.
* **Push at all without home-screen install** — Safari tab visit alone
  gives nothing. User MUST install the PWA first.
* **EU users on iOS 17.4+** — Apple removed standalone PWA support
  under DMA. PWAs open in Safari tabs, no push at all.
* **Cache > 50MB / older than 7 days** — risky for storing offline data.

### Implications for product copy + onboarding:

* Subscribe button on iOS must lead through "Add to Home Screen" first.
  Skipping this = silent failure for ~40% of our traffic.
* On macOS / Android / Windows: push works in any browser tab, no
  install needed. Onboarding is just the permission prompt.
* No Live Activities means we can't compete head-to-head with FotMob on
  iOS lock-screen experience. Two viable counter-moves:
  1. Rich notification text (`France 2-1 Iraq · 87'`) updated every
     goal — visible on lock screen, just doesn't live-tick.
  2. Eventually wrap the PWA in a thin native shell that uses
     ActivityKit (Live Activities API). Out of scope for this batch.

---

## 5. Subscription model — what the schema should look like

Three new tables (additive, follow the same pattern as PushSubscription):

```
class FollowedMatch(Base):
    id        — surrogate
    endpoint  — FK to PushSubscription.endpoint
    match_id  — FK to Match.id
    created_at
    -- event_mask INTEGER  (bitmask of enabled event types; default = all 7)
    -- unique (endpoint, match_id)

class FollowedTeam(Base):
    id, endpoint, team_code, created_at, event_mask
    -- unique (endpoint, team_code)
    -- on insert: backfill rows into FollowedMatch for every upcoming
       fixture of that team within the next 14 days, refreshed nightly.

class NotificationEventLog(Base):
    id, match_id, event_type, event_key, fired_at, recipients
    -- event_key: 'goal:M042:67:fr' (match, minute, scoring side) so we
       can dedup even if api-football re-emits the same event in
       multiple polls
    -- recipients: count of devices the push was sent to
    -- powers the admin "what fired today" view
```

The existing `PushSent` (dedup_key) becomes irrelevant for follow-match
notifications — replaced by `NotificationEventLog.event_key`. Value-pick
and big-swing notifications stay on `PushSent` since they're not
per-match.

`send_push(...)` grows a `recipients` filter:

```
def send_push(
    db, *, title, body, url, dedup_key,
    recipients: Iterable[str] | None = None,  # endpoint allowlist
    require_interaction=False,
):
    subs = db.query(PushSub).filter(PushSub.failed_count < 3)
    if recipients is not None:
        subs = subs.filter(PushSub.endpoint.in_(recipients))
    ...
```

For a goal event:
1. Live poller detects new MatchEvent type='Goal'.
2. Compute event_key = `goal:{match_id}:{elapsed}:{team_code}`.
3. If event_key already in NotificationEventLog → skip (dedup).
4. Build recipient list: `endpoint IN (SELECT endpoint FROM
   FollowedMatch WHERE match_id = M042 UNION SELECT endpoint FROM
   FollowedTeam WHERE team_code IN (home_code, away_code))`.
5. Render title/body. Title carries new score so it's useful even when
   notification is collapsed. Body carries scorer/assist.
6. send_push(..., recipients=that_list, dedup_key=event_key).
7. Insert NotificationEventLog row.

**Wrong-player attribution mitigation (the FotMob bug):** queue the
goal event for 30s before firing. If the second poll re-confirms the
same player_id, fire. If it changes, fire with the corrected name.
Costs one 30s delay per goal, eliminates the embarrassing
"Nkunku scored" when it was Palmer.

---

## 6. UI entry points — where the "Follow" button goes

Ordered by leverage:

1. **Match card** (`frontend/components/match/MatchCard.tsx`) — small
   bell icon in the header next to the Group badge. Tap → POST
   `/api/push/follow-match` with `match_id`. Toggles to filled state if
   already followed. This is the "Google-style" instant follow.

2. **Match detail page** (`/match/[id]`) — full follow card with
   per-event-type toggles (goal/red/HT/FT defaults on, lineup/VAR
   defaults off). Power-user view; most users never visit.

3. **Team page** — bell next to team name. "Follow team" auto-follows
   every fixture in the next 14 days. Highest leverage per click —
   user gets every WC2026 match for their nation without per-game
   action.

4. **Bet slip / "Add to Acca"** — when user adds a pick to a multi or
   creates a single bet, auto-follow that match. Industry-standard
   bookmaker pattern (bet365). Zero friction, signal-rich.

5. **Settings page** — list of currently-followed matches/teams with
   bulk unfollow.

**Onboarding overlay for iOS (essential):** the first time an iOS user
taps Follow, intercept with a tutorial card:
> "Get goal alerts even when the app is closed. Add WC26 to your Home
> Screen first — it only takes 5 seconds."
> [step 1: tap Share] [step 2: scroll, tap Add to Home Screen] [step
> 3: tap Add]
> Then return to this page and tap Follow again.

Without this, ~40% of iOS users will hit the silent failure path.

---

## 7. Cost / quota implications

* Notifications themselves are free (Web Push has no per-message cost
  at the platform layer).
* Server-side overhead: `pywebpush.webpush()` is ~50ms per recipient
  (network-bound on TLS handshake to push services). For a 10k-
  subscriber base × 7 events × 5 matches = 350k pushes per matchday.
  At 50ms each, single-threaded that's 5 hours. **Will need a worker
  pool or batching** (concurrent.futures, ~50 workers brings it to
  ~6 minutes).
* api-football quota: no new calls required — we already pull event
  data every 30s for the live poller. The push dispatch reads
  MatchEvent rows that exist already.
* SQLite contention: a new `NotificationEventLog` write per event +
  N writes for failed-count bumps could become hot. Batch the success
  ack ("touch all these endpoints' last_used") into a single
  bulk-update statement.

---

## 8. Recommended ship order (when we get to building)

1. **Schema migration** — `FollowedMatch`, `FollowedTeam`,
   `NotificationEventLog`. Additive, zero-risk.
2. **`send_push` extension** — accept `recipients` param. Backwards
   compatible.
3. **Event-trigger dispatch** — hook into existing live poller's per-
   tick path. Add 30s confirm-queue for goal events.
4. **POST /api/push/follow-match + /follow-team** endpoints.
5. **UI: bell on MatchCard** (Google-style instant follow). Highest
   visible leverage.
6. **iOS install onboarding overlay.** Without this, iOS users churn
   silently.
7. **UI: full per-event toggles on match detail page.**
8. **UI: bell on team page.**
9. **Auto-follow on Add-to-Acca / pick logged.** Bookmaker pattern.
10. **Worker pool for fan-out** — only when subscriber count makes the
    serial loop a real bottleneck.

Live Activities deliberately omitted — that's a native-shell decision,
not a feature to ship inside the PWA.

---

## 9. Decisions (researched 2026-06-23, user delegated calls)

### 9a. Per-event toggles in v1 — YES (user confirmed)
Ship the 7-event toggle surface from day one. Defaults:
* Goal — ON
* Red card — ON
* Half-time — ON
* Full-time — ON
* Match suspended — ON (no toggle, always fires per §3)
* Match resumed — ON (no toggle, always fires per §3)
* Kickoff — ON
* Lineup published — OFF (FotMob default; lineups are 60min pre-KO,
  users following the actual match find them in-app)
* VAR review — OFF (FotMob default; noisy, only enthusiasts care)
* Penalty awarded/missed — OFF (rolled into goal alerts effectively)

Implementation: `event_mask` integer bitfield on FollowedMatch /
FollowedTeam. Bit positions defined as a constant in
`backend/api/routes/push_follow.py`. Toggling a checkbox in the FE
just flips a bit and PATCHes the row. Single round-trip per toggle.

### 9b. Quiet hours — NO, trust the OS
Researched: FotMob, Sofascore, Apple Sports, Yahoo Sports, theScore
— none of them ship app-level quiet hours. They all rely on the OS:
iOS Focus modes (Sleep/Bedtime/Work), Android Bedtime mode, both
filter notifications during the user's sleep window automatically.

Two arguments to skip app-level quiet hours:

1. **Users who tapped Follow want the alert.** The Reddit complaint
   pattern across NHL/MLB/EPL apps is "I get notifications I didn't
   ask for", never "I asked for them but they came at the wrong
   time". Adding quiet hours would suppress alerts the user
   explicitly opted into — that's worse UX than ringing at 3am.
2. **For Brisbane users specifically:** WC2026 kickoffs land
   11pm-7am local time. A user who follows France-Iraq *is* the
   user who wants the 3am goal ping — they're awake or they've put
   the phone face-down and accepted it. iOS Focus handles "actually
   sleeping" cleanly without us guessing the boundary.

Save the dev time. Document in the subscribe-flow tooltip:
> "Goal alerts respect your phone's Do Not Disturb / Bedtime
> settings. Set those if you don't want pings at 3am."

### 9c. Anonymous v1, account-attach v2
Industry pattern (Pushpad, Engagespot, FotMob): Web Push subscriptions
are *inherently* anonymous — one endpoint per device, nothing tying
them to a user account by default. Mapping to a real account is a
separate optional step needed only for cross-device sync.

Decision for v1: **stay anonymous, per-device.** A user who follows
France on their phone and wants the same on their laptop just taps
Follow twice. That's the same UX every competitor ships and zero
friction to build.

When accounts land for the post-WC pivot (per
`docs/POST_WC_PIVOT.md`):

* Add nullable `user_id` column to PushSubscription (additive,
  zero-risk).
* On login, scan existing endpoints by `user_agent` and offer:
  > "Claim 3 device subscriptions for this account?"
* Once claimed, FollowedMatch / FollowedTeam rows continue to key
  on endpoint — no schema change. User_id is metadata, not the
  primary lookup key.

This keeps v1 build cost minimal AND keeps the v2 migration
cost minimal. Best of both.

### 9d. Auto-follow on Add-to-Acca — YES with explicit-unfollow precedence
bet365 model. When a user adds a leg to their accumulator OR creates a
single bet, auto-insert a `FollowedMatch` row for the underlying
match. Zero friction, signal-rich (they've signalled stake-level
interest in this fixture).

Explicit unfollow wins: if a user later taps the bell off on that
match card, we DELETE the FollowedMatch row AND set a "do not auto-
re-follow" flag (new column, default false) so the next Add-to-Acca
doesn't silently re-subscribe them. Without that flag, the unfollow
would be undone by the next pick add — infuriating.

---

## 10. Final shape v1 ships in

Schema:
```
FollowedMatch(endpoint, match_id, event_mask, source, no_auto_refollow)
FollowedTeam(endpoint, team_code, event_mask)
NotificationEventLog(match_id, event_type, event_key, fired_at, recipients)
```
(`source` = 'manual' | 'auto_pick' so the FE can show why a match is
followed and whether unfollowing should set the no-auto-refollow flag.)

Events (7): kickoff, goal, red, HT, FT, suspended, resumed.
Toggle surface: goal/red/HT/FT/kickoff per-match + per-team.
Suspended + resumed are forced-on (the FRA-IRQ class of bug).

UI entry points (ordered by ship priority):
1. Bell on MatchCard (Google-style instant follow, no settings detour)
2. Bell on team page
3. Auto-follow on Add-to-Acca
4. Per-event toggle drawer on match detail page (power-user surface)
5. Settings page with bulk unfollow

iOS gates:
* Detect iPhone + non-standalone → show install-to-Home-Screen
  overlay before subscribe flow.
* EU iOS users get a "Web Push isn't available on iPhone in the EU
  yet — sorry, blame Apple" disclosure instead of a broken Follow
  button. Better than silent failure.

Out of scope for v1 (queued for v2):
* Live Activities (requires native shell)
* Per-player follow (no player profiles in the public UI yet)
* Apple Watch complications
* Cross-device sync (waits for accounts)
* App-level quiet hours (see §9b)

---

**No code touched in this doc.** Implementation queued for go-ahead.
