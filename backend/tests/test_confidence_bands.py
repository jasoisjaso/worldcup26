"""Tests for the confidence-band reliability breakdown.

The per-match calibration log stores each pre-kickoff 1X2 vector + whether the
model's favourite won. confidence_band_record() buckets settled predictions by
the model's top probability and reports the REALISED hit-rate per band — the
honest 'when we said ~60%, it happened X% of the time' signal we surface on the
match page and report card.
"""
from __future__ import annotations

from backend.data.calibration_logger import _band_for, confidence_bands_from_rows


def test_band_bucketing():
    assert _band_for(0.34) == "<40%"
    assert _band_for(0.40) == "40-50%"
    assert _band_for(0.49) == "40-50%"
    assert _band_for(0.55) == "50-60%"
    assert _band_for(0.62) == "60-70%"
    assert _band_for(0.78) == "70-85%"
    assert _band_for(0.92) == "85%+"


def test_confidence_bands_aggregate():
    # (top_prob, favourite_correct) rows.
    rows = [
        (0.55, 1), (0.55, 0), (0.58, 1), (0.58, 1),   # 50-60% band: 3/4 = 75%
        (0.62, 1), (0.66, 0),                          # 60-70% band: 1/2 = 50%
        (0.90, 1),                                     # 85%+ band: 1/1 = 100%
    ]
    out = confidence_bands_from_rows(rows)
    bands = {b["band"]: b for b in out}
    assert bands["50-60%"]["n"] == 4
    assert bands["50-60%"]["hit_rate"] == 0.75
    assert bands["50-60%"]["expected"] == 0.565  # mean of the 4 top-probs
    assert bands["60-70%"]["n"] == 2
    assert bands["60-70%"]["hit_rate"] == 0.5
    assert bands["85%+"]["n"] == 1
    assert bands["85%+"]["hit_rate"] == 1.0


def test_empty_rows_returns_empty():
    assert confidence_bands_from_rows([]) == []


def test_only_bands_with_data_returned():
    rows = [(0.55, 1), (0.55, 1)]
    out = confidence_bands_from_rows(rows)
    assert len(out) == 1
    assert out[0]["band"] == "50-60%"
