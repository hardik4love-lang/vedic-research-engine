"""
Correlation statistics.

Given FeatureVectors observed at event dates (positives) and at dates with no
event (negatives), measure which factors are actually associated with a
category, and how confident we are in that.

THE PRECISION TRAP
------------------
An imprecise event spans an interval, so it yields several candidate
FeatureVectors. A factor present in SOME of them is weaker evidence than one
present in ALL of them. Comparing "factor present in any candidate vector"
for positives against "factor present on this one date" for negatives would
systematically inflate lift, because the positive side is being asked about a
whole year and the negative side about a single day.

Two coherent aggregation modes are provided and must not be mixed:

  AGG_CONSENSUS  factor must be present in ALL candidate vectors
                 (positives and negatives both treated as intervals)
  AGG_PRESENT    factor present in AT LEAST ONE candidate vector
                 (same convention on both sides)

Mixing them biases lift upward. `check_aggregation_symmetry` exists to catch
that mistake.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .events import EventCategory
from .features import FeatureVector


class Aggregation(str, Enum):
    CONSENSUS = "consensus"  # present in every candidate vector
    PRESENT = "present"      # present in at least one candidate vector


def _aggregate(vectors: Sequence[FeatureVector], mode: Aggregation) -> frozenset[str]:
    if not vectors:
        return frozenset()
    if mode is Aggregation.CONSENSUS:
        common = set(vectors[0].factors)
        for v in vectors[1:]:
            common &= v.factors
        return frozenset(common)
    result: set[str] = set()
    for v in vectors:
        result |= v.factors
    return frozenset(result)


# ---------------------------------------------------------------------------
# Statistics helpers (no SciPy dependency)
# ---------------------------------------------------------------------------


def chi2_sf_1df(chi2: float) -> float:
    """Survival function of the chi-squared distribution with 1 df.

    For 1 df this has the closed form erfc(sqrt(x/2)).
    """
    if chi2 <= 0:
        return 1.0
    return math.erfc(math.sqrt(chi2 / 2.0))


def chi_square_2x2(a: int, b: int, c: int, d: int) -> float:
    """Pearson chi-square for the 2x2 table [[a, b], [c, d]].

    Returns 0.0 when a cell is empty, because the statistic is undefined
    there rather than infinite.
    """
    n = a + b + c + d
    if n == 0:
        return 0.0
    denom = (a + b) * (c + d) * (a + c) * (b + d)
    if denom == 0:
        return 0.0
    return (n * (a * d - b * c) ** 2) / denom


def bonferroni(p_value: float, n_tests: int) -> float:
    """Bonferroni-adjusted p-value, capped at 1.0."""
    if n_tests <= 0:
        return 1.0
    return min(1.0, p_value * n_tests)


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a proportion.

    Preferred over the normal approximation because association support is
    often small, and the normal approximation misbehaves badly at 0 or 1.
    """
    if total == 0:
        return (0.0, 1.0)
    phat = successes / total
    denom = 1 + z**2 / total
    centre = (phat + z**2 / (2 * total)) / denom
    margin = (z / denom) * math.sqrt(phat * (1 - phat) / total + z**2 / (4 * total**2))
    return (max(0.0, centre - margin), min(1.0, centre + margin))


# ---------------------------------------------------------------------------
# Association results
# ---------------------------------------------------------------------------


@dataclass
class FactorAssociation:
    """How strongly a single factor tracks a single event category."""

    category: EventCategory
    factor: str
    a: int  # positives with factor
    b: int  # positives without
    c: int  # negatives with factor
    d: int  # negatives without

    p_value: float = 0.0
    p_value_corrected: float = 1.0
    chi2: float = 0.0
    lift: float = 1.0
    confidence: float = 0.0  # P(factor | positive)
    false_positive_rate: float = 0.0  # P(factor | negative)
    confidence_low: float = 0.0
    confidence_high: float = 0.0

    sufficient_data: bool = True
    insufficient_reason: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "factor": self.factor,
            "counts": {
                "positives_with": self.a,
                "positives_without": self.b,
                "negatives_with": self.c,
                "negatives_without": self.d,
            },
            "p_value": self.p_value,
            "p_value_corrected": self.p_value_corrected,
            "chi2": self.chi2,
            "lift": self.lift,
            "confidence": self.confidence,
            "false_positive_rate": self.false_positive_rate,
            "confidence_ci": [self.confidence_low, self.confidence_high],
            "sufficient_data": self.sufficient_data,
            "insufficient_reason": self.insufficient_reason,
        }


def compute_associations(
    category: EventCategory,
    positives: Sequence[Sequence[FeatureVector]],
    negatives: Sequence[Sequence[FeatureVector]],
    aggregation: Aggregation = Aggregation.CONSENSUS,
    min_support: int = 5,
    n_tests_hint: int | None = None,
) -> list[FactorAssociation]:
    """Associate factors with one category.

    ``positives`` and ``negatives`` are each a sequence of *groups*, one group
    per event or per negative window, so that an imprecise event contributes
    its whole candidate-date group. Both sides use the same aggregation mode.
    """
    pos_sets = [_aggregate(g, aggregation) for g in positives]
    neg_sets = [_aggregate(g, aggregation) for g in negatives]

    all_factors: set[str] = set()
    for s in pos_sets:
        all_factors |= s
    for s in neg_sets:
        all_factors |= s

    results: list[FactorAssociation] = []
    n_tests = n_tests_hint or len(all_factors)

    for factor in sorted(all_factors):
        a = sum(1 for s in pos_sets if factor in s)
        b = len(pos_sets) - a
        c = sum(1 for s in neg_sets if factor in s)
        d = len(neg_sets) - c

        assoc = FactorAssociation(
            category=category, factor=factor, a=a, b=b, c=c, d=d
        )

        # Insufficient data is reported explicitly rather than as a
        # p-value that would look significant on a handful of points.
        if a + b < min_support or c + d < min_support:
            assoc.sufficient_data = False
            assoc.insufficient_reason = (
                f"needs >={min_support} observations per class, "
                f"got {a + b} positive / {c + d} negative"
            )
        elif (a + b) == 0 or (c + d) == 0 or a + c == 0 or b + d == 0:
            assoc.sufficient_data = False
            assoc.insufficient_reason = "degenerate contingency table"

        conf = a / (a + b) if (a + b) else 0.0
        fpr = c / (c + d) if (c + d) else 0.0
        assoc.confidence = conf
        assoc.false_positive_rate = fpr
        assoc.confidence_low, assoc.confidence_high = wilson_interval(a, a + b)
        assoc.lift = (conf / fpr) if fpr > 0 else float("inf") if conf > 0 else 1.0

        assoc.chi2 = chi_square_2x2(a, b, c, d)
        assoc.p_value = chi2_sf_1df(assoc.chi2)
        assoc.p_value_corrected = bonferroni(assoc.p_value, n_tests)

        results.append(assoc)

    return results


# ---------------------------------------------------------------------------
# Rule sets
# ---------------------------------------------------------------------------


@dataclass
class Rule:
    """A factor that passed the statistical screen for a category."""

    category: EventCategory
    factor: str
    weight: float
    threshold_lift: float
    support: int
    observed_lift: float
    p_value_corrected: float
    false_positive_rate: float

    def to_json(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "factor": self.factor,
            "weight": self.weight,
            "threshold_lift": self.threshold_lift,
            "support": self.support,
            "observed_lift": self.observed_lift,
            "p_value_corrected": self.p_value_corrected,
            "false_positive_rate": self.false_positive_rate,
        }


@dataclass
class RuleSet:
    """The frozen rule set produced by training. Version it, never mutate."""

    version: str
    rules: list[Rule] = field(default_factory=list)
    aggregation: Aggregation = Aggregation.CONSENSUS
    min_lift: float = 1.5
    max_p_corrected: float = 0.05
    min_support: int = 5
    categories_tested: int = 0
    factors_tested: int = 0

    def rules_for(self, category: EventCategory) -> list[Rule]:
        return [r for r in self.rules if r.category is category]

    def score(self, factors: Iterable[str]) -> dict[EventCategory, float]:
        """Score a set of factors against every category's rules.

        Weight is a bounded, monotone function of lift, so one extreme
        factor cannot dominate a prediction on its own.
        """
        present = set(factors)
        scores: dict[EventCategory, float] = {}
        for category in EventCategory:
            cat_rules = self.rules_for(category)
            if not cat_rules:
                continue
            total = sum(r.weight for r in cat_rules)
            hit = sum(r.weight for r in cat_rules if r.factor in present)
            scores[category] = hit / total if total else 0.0
        return scores

    def to_json(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "aggregation": self.aggregation.value,
            "screening": {
                "min_lift": self.min_lift,
                "max_p_corrected": self.max_p_corrected,
                "min_support": self.min_support,
            },
            "categories_tested": self.categories_tested,
            "factors_tested": self.factors_tested,
            "rule_count": len(self.rules),
            "rules": [r.to_json() for r in self.rules],
        }


def build_rule_set(
    associations_by_category: dict[EventCategory, list[FactorAssociation]],
    version: str,
    aggregation: Aggregation = Aggregation.CONSENSUS,
    min_lift: float = 1.5,
    max_p_corrected: float = 0.05,
    min_support: int = 5,
) -> RuleSet:
    """Screen associations into rules.

    Bonferroni correction is applied across categories x factors, not just
    factors, because testing many categories inflates the family-wise error
    rate as well.
    """
    factors_tested = sum(
        len(v) for v in associations_by_category.values()
    )
    n_tests = factors_tested * max(1, len(associations_by_category))

    rules: list[Rule] = []
    for category, assocs in associations_by_category.items():
        for assoc in assocs:
            if not assoc.sufficient_data:
                continue
            corrected = bonferroni(assoc.p_value, n_tests)
            if assoc.lift < min_lift or corrected > max_p_corrected:
                continue
            if assoc.a < min_support:
                continue
            if not math.isfinite(assoc.lift):
                continue
            # Bounded weight: log-scaled lift compressed into [0, 1).
            weight = min(1.0, math.log2(assoc.lift) / 4.0)
            rules.append(
                Rule(
                    category=category,
                    factor=assoc.factor,
                    weight=weight,
                    threshold_lift=min_lift,
                    support=assoc.a,
                    observed_lift=assoc.lift,
                    p_value_corrected=corrected,
                    false_positive_rate=assoc.false_positive_rate,
                )
            )

    rules.sort(key=lambda r: (r.category.value, -r.observed_lift))
    return RuleSet(
        version=version,
        rules=rules,
        aggregation=aggregation,
        min_lift=min_lift,
        max_p_corrected=max_p_corrected,
        min_support=min_support,
        categories_tested=len(associations_by_category),
        factors_tested=factors_tested,
    )


# ---------------------------------------------------------------------------
# Guards against methodological mistakes
# ---------------------------------------------------------------------------


def check_aggregation_symmetry(
    positives: Sequence[Sequence[FeatureVector]],
    negatives: Sequence[Sequence[FeatureVector]],
    tolerance: float = 0.15,
) -> dict[str, Any]:
    """Report the lift inflation caused by asymmetric aggregation.

    Compares a fair comparison (same aggregation both sides) against the
    biased one (positives aggregated across an interval, negatives treated as
    single dates). A large gap means the analysis is not measuring association
    but measurement granularity.
    """
    fair = compute_associations(
        EventCategory.OTHER,
        positives,
        negatives,
        aggregation=Aggregation.CONSENSUS,
        min_support=0,
    )
    pos_any = [_aggregate(g, Aggregation.PRESENT) for g in positives]
    neg_consensus = [_aggregate(g, Aggregation.CONSENSUS) for g in negatives]

    if not pos_any or not neg_consensus:
        return {
            "fair_mean_lift": 0.0,
            "biased_mean_lift": 0.0,
            "inflation": 0.0,
            "exceeds_tolerance": False,
            "tolerance": tolerance,
            "verdict": "No data to compare.",
        }

    biased: list[float] = []
    for factor in set().union(*pos_any) | set().union(*neg_consensus):
        a = sum(1 for s in pos_any if factor in s)
        c = sum(1 for s in neg_consensus if factor in s)
        if a == 0 or c == 0:
            continue
        biased.append((a / len(pos_any)) / (c / len(neg_consensus)))

    fair_lifts = [x.lift for x in fair if x.lift > 0 and math.isfinite(x.lift)]
    fair_mean = sum(fair_lifts) / len(fair_lifts) if fair_lifts else 0.0
    finite_biased = [x for x in biased if math.isfinite(x)]
    biased_mean = sum(finite_biased) / len(finite_biased) if finite_biased else 0.0

    inflation = biased_mean - fair_mean
    return {
        "fair_mean_lift": fair_mean,
        "biased_mean_lift": biased_mean,
        "inflation": inflation,
        "exceeds_tolerance": inflation > tolerance,
        "tolerance": tolerance,
            "verdict": (
                "Aggregation is symmetric; lift is interpretable."
                if inflation <= tolerance
                else "Asymmetric aggregation inflates lift. Use the same "
                "aggregation mode on both sides."
            ),
    }
