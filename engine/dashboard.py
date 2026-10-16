"""
Accuracy dashboard.

Reports MEASURED performance. There is no path through this module that
produces a number which was not computed from data, and no code path that
renders a rule-derived score as though it were a probability.

The current dataset yields a null result across every category, and that is
what the dashboard shows. A dashboard that could only ever display good news
would not be a dashboard, it would be marketing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .correlation import wilson_interval


@dataclass
class CategoryPerformance:
    """Measured performance for one event category."""

    category: str
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    lift: float
    lift_low: float
    lift_high: float
    bootstrap_p: float
    permutation_p: float
    naive_p: float
    support: int
    confounded: bool = False
    confound_notes: list[str] = field(default_factory=list)

    @property
    def precision(self) -> float:
        d = self.true_positives + self.false_positives
        return self.true_positives / d if d else 0.0

    @property
    def recall(self) -> float:
        d = self.true_positives + self.false_negatives
        return self.true_positives / d if d else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def false_positive_rate(self) -> float:
        d = self.false_positives + self.true_negatives
        return self.false_positives / d if d else 0.0

    @property
    def coverage(self) -> float:
        total = (self.true_positives + self.false_positives
                 + self.true_negatives + self.false_negatives)
        return ((self.true_positives + self.false_positives) / total) if total else 0.0

    @property
    def significant(self) -> bool:
        """Significant only if BOTH cluster-robust methods agree and the
        interval excludes no association."""
        return (
            not self.confounded
            and self.bootstrap_p <= 0.05
            and self.permutation_p <= 0.05
            and self.lift_low > 1.0
        )

    @property
    def evidence(self) -> str:
        if self.support == 0:
            return "no data"
        if self.confounded:
            return "not interpretable"
        if self.significant:
            return "supported"
        return "no association detected"

    def to_json(self) -> dict[str, Any]:
        prec_lo, prec_hi = wilson_interval(
            self.true_positives, self.true_positives + self.false_positives
        )
        return {
            "category": self.category,
            "evidence": self.evidence,
            "significant": self.significant,
            "confounded": self.confounded,
            "confound_notes": self.confound_notes,
            "counts": {
                "true_positives": self.true_positives,
                "false_positives": self.false_positives,
                "true_negatives": self.true_negatives,
                "false_negatives": self.false_negatives,
            },
            "precision": self.precision,
            "precision_ci": [prec_lo, prec_hi],
            "recall": self.recall,
            "f1": self.f1,
            "false_positive_rate": self.false_positive_rate,
            "coverage": self.coverage,
            "lift": self.lift,
            "lift_ci": [self.lift_low, self.lift_high],
            "p_values": {
                "bootstrap": self.bootstrap_p,
                "permutation": self.permutation_p,
                "naive_not_valid": self.naive_p,
            },
            "support": self.support,
        }


def build_dashboard(
    per_category: list[CategoryPerformance],
    sample_description: str,
    method_notes: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble the dashboard payload.

    Deliberately reports the number of categories analysed and the number
    showing support, so a reader can see at a glance that zero is the answer
    rather than having to infer it.
    """
    analysed = [c for c in per_category if c.support > 0]
    supported = [c for c in analysed if c.significant]
    confounded = [c for c in analysed if c.confounded]

    return {
        "sample": sample_description,
        "categories_analysed": len(analysed),
        "categories_supported": len(supported),
        "categories_not_interpretable": len(confounded),
        "verdict": _verdict(supported, analysed),
        "categories": [c.to_json() for c in per_category],
        "method_notes": method_notes or [],
        "disclaimer": (
            "Figures are measured out-of-sample or, where stated, "
            "association-only on a convenience sample. Absence of detected "
            "association is not proof of absence; it reflects this dataset "
            "and these confounds."
        ),
    }


def _verdict(supported: list[CategoryPerformance],
             analysed: list[CategoryPerformance]) -> str:
    if not analysed:
        return "No category had enough data to analyse."
    if supported:
        names = ", ".join(c.category for c in supported)
        return (
            f"Association detected for {len(supported)} of {len(analysed)} "
            f"categories: {names}. Requires replication on an independent "
            f"cohort before it should be relied upon."
        )
    return (
        f"No association detected in any of the {len(analysed)} categories "
        f"analysed. This is a null result on the stated sample, not evidence "
        f"that the relationship is absent in general."
    )


def calibration_bins(
    predictions: list[tuple[float, bool]],
    bins: int = 5,
) -> list[dict[str, Any]]:
    """Reliability diagram data: predicted score vs observed frequency."""
    buckets: list[list[tuple[float, bool]]] = [[] for _ in range(bins)]
    for score, hit in predictions:
        idx = min(int(score * bins), bins - 1)
        buckets[idx].append((score, hit))

    out = []
    for i, bucket in enumerate(buckets):
        if not bucket:
            out.append({
                "bin": f"{i / bins:.1f}-{(i + 1) / bins:.1f}",
                "n": 0,
                "mean_predicted": None,
                "observed_frequency": None,
            })
            continue
        mean_score = sum(s for s, _ in bucket) / len(bucket)
        hits = sum(1 for _, h in bucket if h)
        lo, hi = wilson_interval(hits, len(bucket))
        out.append({
            "bin": f"{i / bins:.1f}-{(i + 1) / bins:.1f}",
            "n": len(bucket),
            "mean_predicted": mean_score,
            "observed_frequency": hits / len(bucket),
            "observed_ci": [lo, hi],
            "gap": mean_score - hits / len(bucket),
        })
    return out


def expected_calibration_error(bins: list[dict[str, Any]]) -> float:
    total = sum(b["n"] for b in bins)
    if total == 0:
        return 1.0
    return sum(b["n"] / total * abs(b["gap"]) for b in bins if b["n"])
