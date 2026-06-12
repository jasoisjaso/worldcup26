"""Model version tag, stamped onto logged prediction snapshots so live calibration
can be attributed to a specific model revision. Bump when the engine changes."""

# v2: lowered DC time-decay xi (0.00325->0.0018), shifted DC/ELO blend toward ELO,
# removed backwards MD1 rho, Shin de-vig + OU blend, capped modifier stack, unified
# the logger with the live route. See memory: wc2026-model-findings.
MODEL_VERSION = "2.0"
