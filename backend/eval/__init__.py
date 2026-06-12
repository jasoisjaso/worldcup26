"""Offline evaluation / backtest harness for the WC2026 predictor.

Nothing in here runs in the live API path — it is a research/validation tool
used to measure calibration and discrimination (RPS, log-loss, Brier) of the
goal model on historical internationals, so that model changes can be validated
empirically instead of hand-tuned.
"""
