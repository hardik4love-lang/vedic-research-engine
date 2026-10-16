"""Persist the cluster-robust evaluation so the dashboard has real figures."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.dashboard import (  # noqa: E402
    CategoryPerformance,
    build_dashboard,
)

# Measured by scripts/corrected_run.py on 332 profiles with day-precision
# marriage dates. Negatives age-matched to within +/-6 years of each
# profile's own event age, clustered by profile.
#
# Counts are not separately meaningful here: the analysis is an association
# test on single event dates against matched non-event dates, so the
# conventional confusion-matrix counts do not apply. tp/fp/tn/fn are left at
# zero and the dashboard shows the association statistics that were measured.
PERF = [
    ("dasha=rahu", 1.040, 0.80, 1.34, 0.8032, 0.0100, 0.701),
    ("dasha=sun", 1.248, 0.75, 1.95, 0.3916, 0.0010, 0.262),
    ("dasha=jupiter", 0.945, 0.69, 1.29, 0.7173, 0.0010, 0.633),
    ("dasha=venus", 0.994, 0.72, 1.34, 0.9710, 0.0040, 0.957),
    ("dasha=saturn", 0.978, 0.66, 1.38, 0.8791, 0.0010, 0.883),
    ("dasha=moon", 0.815, 0.46, 1.32, 0.3576, 0.0010, 0.350),
    ("dasha=mercury", 1.049, 0.68, 1.62, 0.7852, 0.0480, 0.760),
    ("dasha=mars", 1.013, 0.53, 1.75, 0.9191, 0.0010, 0.959),
    ("dasha=ketu", 0.951, 0.42, 1.75, 0.8851, 0.0020, 0.861),
]

cats = [
    CategoryPerformance(
        category=name,
        true_positives=0, false_positives=0,
        true_negatives=0, false_negatives=0,
        lift=lift, lift_low=lo, lift_high=hi,
        bootstrap_p=boot_p, permutation_p=perm_p, naive_p=naive_p,
        support=332,
    )
    for name, lift, lo, hi, boot_p, perm_p, naive_p in PERF
]

payload = build_dashboard(
    cats,
    sample_description=(
        "332 public figures with Rodden-AA birth records and day-precision "
        "marriage dates. Negative dates sampled within +/-6 years of each "
        "subject's own event age, clustered by subject. Association analysis, "
        "not prediction: no blind forecast was performed."
    ),
    method_notes=[
        "Inference clustered by profile. The naive analysis overstates "
        "significance by ~28 million times on autocorrelated windows; its "
        "p-values are shown only to be discounted.",
        "Negatives age-matched. Vimshottari dashas run sequentially through "
        "life, so an unmatched comparison measures age rather than timing.",
        "Day-precision events only, so positive and negative sides are "
        "compared at matching granularity.",
        "Significant requires agreement between bootstrap and permutation "
        "AND a confidence interval excluding lift = 1.",
    ],
)

out = ROOT / "data" / "evaluation.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

print(f"categories analysed : {payload['categories_analysed']}")
print(f"categories supported: {payload['categories_supported']}")
print(f"verdict             : {payload['verdict']}")
print(f"written to          : {out}")