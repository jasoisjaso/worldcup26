"""Calibration-by-segment audit (option E from harvest-to-model plan).

Reads model_calibration_log + matches, buckets predictions by segment, and
prints a per-segment hit rate / Brier / calibration-error report. Designed to
answer: are we systematically over/under-confident in any segment?

Segments:
  - phase: group stage (matchday 1-3) vs knockout (matchday >= 4)
  - confidence band on the favorite: 33-50, 50-60, 60-70, 70-80, 80+
  - favorite side: home vs away (draw can never be the favourite in 1X2 unless
    we have a true coinflip — handled separately)

Output:
  - per-segment counts, observed hit rate, expected hit rate (mean p_favorite),
    calibration delta (observed - expected), Brier mean, log-loss mean
  - flagged segments where |delta| > 0.10 AND sample >= 10 (the only segments
    big enough + skewed enough to act on)

Run on VPS: docker exec wc26-backend python /app/scripts/calibration_audit.py
"""
from __future__ import annotations

import sqlite3
import statistics
from collections import defaultdict


DB_PATH = "/app/data/wc2026.db"


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    rows = con.execute("""
        SELECT l.match_id, l.home_score, l.away_score,
               l.pre_p_home, l.pre_p_draw, l.pre_p_away,
               l.brier_1x2, l.log_loss_1x2, l.favorite_correct,
               m.matchday, m."group", m.home_code, m.away_code
        FROM model_calibration_log l
        JOIN matches m ON m.id = l.match_id
        WHERE m.status = 'complete'
    """).fetchall()
    con.close()

    print(f"Audit over {len(rows)} settled predictions\n")

    # Overall summary
    briers = [r[6] for r in rows if r[6] is not None]
    logs = [r[7] for r in rows if r[7] is not None]
    fav_correct = [r[8] for r in rows if r[8] is not None]
    print("=== Overall ===")
    print(f"  mean Brier:    {statistics.mean(briers):.4f}")
    print(f"  mean log-loss: {statistics.mean(logs):.4f}")
    print(f"  favorite hit:  {statistics.mean(fav_correct):.1%}  ({sum(fav_correct)}/{len(fav_correct)})")
    print()

    # Group rows into segments
    def fav_prob(row):
        return max(row[3], row[4], row[5])

    def fav_side(row):
        ph, pd, pa = row[3], row[4], row[5]
        if pd >= ph and pd >= pa:
            return "draw"
        return "home" if ph >= pa else "away"

    def conf_band(p):
        if p < 0.40: return "33-40"
        if p < 0.50: return "40-50"
        if p < 0.60: return "50-60"
        if p < 0.70: return "60-70"
        if p < 0.80: return "70-80"
        return "80+"

    def phase(row):
        md = row[9] or 0
        return "group" if md <= 3 else "knockout"

    # 1. By confidence band
    print("=== By favourite-probability band ===")
    print(f"{'band':<8}{'n':>5}{'fav_hit':>10}{'mean_p_fav':>12}{'delta':>10}{'mean_brier':>13}")
    bands = defaultdict(list)
    for r in rows:
        bands[conf_band(fav_prob(r))].append(r)
    for band in ["33-40", "40-50", "50-60", "60-70", "70-80", "80+"]:
        bucket = bands[band]
        if not bucket: continue
        n = len(bucket)
        hit = sum(b[8] for b in bucket) / n
        mp = sum(fav_prob(b) for b in bucket) / n
        delta = hit - mp
        brier = sum(b[6] for b in bucket) / n
        print(f"{band:<8}{n:>5}{hit:>10.1%}{mp:>12.1%}{delta:>+10.1%}{brier:>13.4f}")
    print()

    # 2. By phase (group vs knockout)
    print("=== By tournament phase ===")
    print(f"{'phase':<10}{'n':>5}{'fav_hit':>10}{'mean_p_fav':>12}{'delta':>10}{'mean_brier':>13}")
    phases = defaultdict(list)
    for r in rows:
        phases[phase(r)].append(r)
    for p in ["group", "knockout"]:
        bucket = phases[p]
        if not bucket: continue
        n = len(bucket)
        hit = sum(b[8] for b in bucket) / n
        mp = sum(fav_prob(b) for b in bucket) / n
        delta = hit - mp
        brier = sum(b[6] for b in bucket) / n
        print(f"{p:<10}{n:>5}{hit:>10.1%}{mp:>12.1%}{delta:>+10.1%}{brier:>13.4f}")
    print()

    # 3. By favourite side
    print("=== By favourite side ===")
    print(f"{'side':<10}{'n':>5}{'fav_hit':>10}{'mean_p_fav':>12}{'delta':>10}{'mean_brier':>13}")
    sides = defaultdict(list)
    for r in rows:
        sides[fav_side(r)].append(r)
    for s in ["home", "away", "draw"]:
        bucket = sides[s]
        if not bucket: continue
        n = len(bucket)
        hit = sum(b[8] for b in bucket) / n
        mp = sum(fav_prob(b) for b in bucket) / n
        delta = hit - mp
        brier = sum(b[6] for b in bucket) / n
        print(f"{s:<10}{n:>5}{hit:>10.1%}{mp:>12.1%}{delta:>+10.1%}{brier:>13.4f}")
    print()

    # 4. Cross-tab: phase x confidence band
    print("=== Phase × confidence band ===")
    print(f"{'phase':<10}{'band':<8}{'n':>5}{'fav_hit':>10}{'mean_p_fav':>12}{'delta':>10}")
    cross = defaultdict(list)
    for r in rows:
        cross[(phase(r), conf_band(fav_prob(r)))].append(r)
    for p in ["group", "knockout"]:
        for band in ["33-40", "40-50", "50-60", "60-70", "70-80", "80+"]:
            bucket = cross[(p, band)]
            if not bucket: continue
            n = len(bucket)
            hit = sum(b[8] for b in bucket) / n
            mp = sum(fav_prob(b) for b in bucket) / n
            delta = hit - mp
            print(f"{p:<10}{band:<8}{n:>5}{hit:>10.1%}{mp:>12.1%}{delta:>+10.1%}")
    print()

    # 5. Notable miscalibration: any segment with |delta| > 0.10 AND n >= 10
    print("=== Notable miscalibration (|delta| > 10pp, n >= 10) ===")
    found = False
    for label, bucket in [("band:" + b, bands[b]) for b in bands] + \
                         [("phase:" + p, phases[p]) for p in phases] + \
                         [("side:" + s, sides[s]) for s in sides] + \
                         [(f"{p}/{b}", cross[(p, b)]) for p in ["group", "knockout"] for b in bands]:
        if len(bucket) < 10:
            continue
        n = len(bucket)
        hit = sum(r[8] for r in bucket) / n
        mp = sum(fav_prob(r) for r in bucket) / n
        delta = hit - mp
        if abs(delta) > 0.10:
            direction = "over-confident" if delta < 0 else "under-confident"
            print(f"  {label:<25} n={n:>4}  delta={delta:+.1%}  ({direction})")
            found = True
    if not found:
        print("  None — model is within 10pp on every n>=10 segment.")


if __name__ == "__main__":
    main()
