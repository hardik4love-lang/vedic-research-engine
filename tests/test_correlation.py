"""
Phase 3 tests — correlation statistics.

Includes tests for the statistical helpers against known values, and a test
demonstrating that asymmetric aggregation inflates lift.
"""

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.correlation import (  # noqa: E402
    Aggregation,
    FactorAssociation,
    RuleSet,
    _aggregate,
    bonferroni,
    build_rule_set,
    check_aggregation_symmetry,
    chi2_sf_1df,
    chi_square_2x2,
    compute_associations,
    wilson_interval,
)
from engine.events import EventCategory  # noqa: E402
from engine.features import FeatureVector  # noqa: E402


def make_vector(when: date, factors: set[str]) -> list[FeatureVector]:
    """A group of one vector with a given factor set."""
    return [FeatureVector(when=when, factors=frozenset(factors))]


# ---------------------------------------------------------------------------
# Statistical helpers against known values
# ---------------------------------------------------------------------------


def test_chi2_sf_1df_known_values():
    # 1 df critical values: p=0.05 at chi2=3.841, p=0.01 at chi2=6.635
    assert chi2_sf_1df(3.841) == pytest.approx(0.05, abs=0.001)
    assert chi2_sf_1df(6.635) == pytest.approx(0.01, abs=0.001)
    assert chi2_sf_1df(0.0) == 1.0
    assert chi2_sf_1df(100.0) < 1e-10


def test_chi_square_2x2_perfect_association():
    # Factor perfectly predicts the class -> maximal chi-square
    chi2 = chi_square_2x2(10, 0, 0, 10)
    assert chi2 == pytest.approx(20.0)


def test_chi_square_2x2_no_association():
    assert chi_square_2x2(5, 5, 5, 5) == pytest.approx(0.0)


def test_chi_square_2x2_degenerate_tables():
    assert chi_square_2x2(0, 0, 0, 0) == 0.0
    assert chi_square_2x2(5, 5, 0, 0) == 0.0


def test_bonferroni_correction():
    assert bonferroni(0.01, 10) == pytest.approx(0.10)
    assert bonferroni(0.01, 50) == pytest.approx(0.50)
    # Corrected p-values are probabilities, so they cap at 1.0
    assert bonferroni(0.01, 1000) == 1.0
    assert bonferroni(0.05, 0) == 1.0


def test_wilson_interval_known_values():
    lo, hi = wilson_interval(50, 100)
    assert lo == pytest.approx(0.4038, abs=0.001)
    assert hi == pytest.approx(0.5962, abs=0.001)


def test_wilson_interval_handles_zero_counts():
    """The normal approximation would give a zero-width interval here."""
    lo, hi = wilson_interval(0, 10)
    assert lo == 0.0
    assert 0.0 < hi < 1.0
    lo, hi = wilson_interval(10, 10)
    assert hi == 1.0
    assert 0.0 < lo < 1.0


def test_wilson_interval_zero_sample():
    assert wilson_interval(0, 0) == (0.0, 1.0)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def test_consensus_is_intersection():
    group = [
        FeatureVector(when=date(2010, 1, 1), factors=frozenset({"a", "b"})),
        FeatureVector(when=date(2010, 2, 1), factors=frozenset({"b", "c"})),
    ]
    assert _aggregate(group, Aggregation.CONSENSUS) == frozenset({"b"})
    assert _aggregate(group, Aggregation.PRESENT) == frozenset({"a", "b", "c"})


def test_aggregate_empty_group():
    assert _aggregate([], Aggregation.CONSENSUS) == frozenset()
    assert _aggregate([], Aggregation.PRESENT) == frozenset()


# ---------------------------------------------------------------------------
# Association computation
# ---------------------------------------------------------------------------


def test_strong_association_is_detected():
    positives = [make_vector(date(2010, 1, 1), {"saturn_10th", "dasha=saturn"})
                 for _ in range(20)]
    negatives = [make_vector(date(2010, 2, 1), {"jupiter_9th"})
                 for _ in range(20)]

    assocs = compute_associations(
        EventCategory.CAREER, positives, negatives, min_support=5
    )
    by_factor = {a.factor: a for a in assocs}

    saturn = by_factor["saturn_10th"]
    assert saturn.a == 20
    assert saturn.c == 0
    assert saturn.confidence == 1.0
    assert saturn.false_positive_rate == 0.0
    assert saturn.lift == float("inf")
    assert saturn.p_value < 0.01

    jupiter = by_factor["jupiter_9th"]
    assert jupiter.c == 20
    assert jupiter.false_positive_rate == 1.0
    assert jupiter.lift == 0.0


def test_no_association_gives_lift_near_one():
    positives = [make_vector(date(2010, 1, 1), {"x"} if i % 2 else set())
                 for i in range(20)]
    negatives = [make_vector(date(2010, 2, 1), {"x"} if i % 2 else set())
                 for i in range(20)]

    assocs = compute_associations(
        EventCategory.CAREER, positives, negatives, min_support=5
    )
    x = next(a for a in assocs if a.factor == "x")
    assert x.lift == pytest.approx(1.0)
    assert x.p_value > 0.5


def test_insufficient_data_is_flagged_not_reported_as_significant():
    """Three positives can trivially look significant. We must say so."""
    positives = [make_vector(date(2010, 1, 1), {"rare"}) for _ in range(3)]
    negatives = [make_vector(date(2010, 2, 1), set()) for _ in range(50)]

    assocs = compute_associations(
        EventCategory.CAREER, positives, negatives, min_support=5
    )
    rare = next(a for a in assocs if a.factor == "rare")
    assert rare.sufficient_data is False
    assert "needs >=5" in rare.insufficient_reason


def test_counts_are_reported_for_auditability():
    positives = [make_vector(date(2010, 1, 1), {"a"}) for _ in range(8)]
    positives += [make_vector(date(2010, 1, 2), set()) for _ in range(2)]
    negatives = [make_vector(date(2010, 2, 1), {"a"}) for _ in range(3)]
    negatives += [make_vector(date(2010, 2, 2), set()) for _ in range(7)]

    assocs = compute_associations(
        EventCategory.CAREER, positives, negatives, min_support=5
    )
    a = next(x for x in assocs if x.factor == "a")
    assert (a.a, a.b, a.c, a.d) == (8, 2, 3, 7)
    assert a.confidence == pytest.approx(0.8)
    assert a.false_positive_rate == pytest.approx(0.3)


# ---------------------------------------------------------------------------
# Rule screening
# ---------------------------------------------------------------------------


def _mk(category, factor, a, b, c, d, p=0.001, lift=3.0):
    assoc = FactorAssociation(category=category, factor=factor, a=a, b=b, c=c, d=d)
    assoc.p_value = p
    assoc.chi2 = 100.0
    assoc.lift = lift
    assoc.confidence = a / (a + b) if (a + b) else 0.0
    assoc.false_positive_rate = c / (c + d) if (c + d) else 0.0
    assoc.sufficient_data = True
    return assoc


def test_rules_pass_the_screen():
    assocs = {
        EventCategory.CAREER: [
            _mk(EventCategory.CAREER, "strong", 20, 5, 2, 30),
            _mk(EventCategory.CAREER, "weak", 20, 5, 15, 17, lift=1.1),
            _mk(EventCategory.CAREER, "null", 20, 5, 19, 13, lift=1.0),
        ]
    }
    rs = build_rule_set(assocs, version="test-1", min_support=5)
    factors = [r.factor for r in rs.rules]
    assert "strong" in factors
    assert "weak" not in factors, "lift below threshold must be screened out"
    assert "null" not in factors


def test_insufficient_data_never_becomes_a_rule():
    assoc = _mk(EventCategory.CAREER, "thin", 3, 20, 2, 30)
    assoc.sufficient_data = False
    assoc.insufficient_reason = "too few"
    rs = build_rule_set({EventCategory.CAREER: [assoc]}, version="t")
    assert rs.rules == []


def test_infinite_lift_never_becomes_a_rule():
    rs = build_rule_set(
        {EventCategory.CAREER: [_mk(EventCategory.CAREER, "inf", 20, 5, 0, 30,
                                     lift=float("inf"))]},
        version="t",
    )
    assert rs.rules == []


def test_bonferroni_across_categories_is_stricter_than_within():
    """Testing many categories must raise the bar for significance.

    p=0.01 passes when 1 category x 3 factors are tested (0.01*3 = 0.03)
    but fails when 9 categories x 3 factors are tested (0.01*27 = 0.27).
    """
    weak = [_mk(EventCategory.CAREER, f"f{i}", 20, 5, 10, 20, p=0.01, lift=2.0)
            for i in range(3)]

    few = build_rule_set(
        {EventCategory.CAREER: weak}, version="few", min_support=5
    )
    many = build_rule_set(
        {cat: weak for cat in EventCategory}, version="many", min_support=5
    )
    assert len(few.rules) == 3
    assert len(many.rules) == 0


def test_rule_weights_are_bounded():
    rs = build_rule_set(
        {EventCategory.CAREER: [_mk(EventCategory.CAREER, "huge", 50, 5, 1, 50,
                                     lift=64.0)]},
        version="t",
    )
    rule = rs.rules[0]
    assert 0.0 < rule.weight <= 1.0
    assert rule.weight == pytest.approx(1.0)


def test_scoring_is_bounded_and_category_specific():
    rs = RuleSet(
        version="t",
        rules=[
            _rule(EventCategory.CAREER, "a", 0.5),
            _rule(EventCategory.CAREER, "b", 0.5),
            _rule(EventCategory.FINANCE, "z", 1.0),
        ],
    )
    scores = rs.score({"a"})
    assert scores[EventCategory.CAREER] == pytest.approx(0.5)
    assert scores[EventCategory.FINANCE] == 0.0
    assert all(0.0 <= v <= 1.0 for v in scores.values())


def _rule(category, factor, weight):
    from engine.correlation import Rule

    return Rule(
        category=category, factor=factor, weight=weight,
        threshold_lift=1.5, support=10, observed_lift=2.0,
        p_value_corrected=0.01, false_positive_rate=0.1,
    )


def test_rule_set_serialises():
    rs = build_rule_set(
        {EventCategory.CAREER: [_mk(EventCategory.CAREER, "a", 20, 5, 2, 30)]},
        version="v1",
    )
    payload = rs.to_json()
    assert payload["version"] == "v1"
    assert payload["rule_count"] == len(rs.rules)
    assert payload["screening"]["min_lift"] == 1.5


# ---------------------------------------------------------------------------
# The precision trap
# ---------------------------------------------------------------------------


def test_asymmetric_aggregation_inflates_lift():
    """Positives aggregated across an interval vs negatives at single dates
    overstates association. This is the bias the guard exists to catch."""

    # Each positive spans a year: the factor is present in only one month.
    positives = []
    for _ in range(20):
        positives.append([
            FeatureVector(when=date(2010, m, 1), factors=frozenset(
                {"rare_factor"} if m == 3 else {"common"}
            ))
            for m in range(1, 13)
        ])

    # Negatives are single dates, where the factor essentially never occurs.
    negatives = [make_vector(date(2012, 1, 1), {"common"}) for _ in range(20)]

    report = check_aggregation_symmetry(positives, negatives)
    assert report["biased_mean_lift"] > report["fair_mean_lift"]
    assert report["exceeds_tolerance"] is True
    assert "inflates lift" in report["verdict"]


def test_symmetric_aggregation_shows_no_inflation():
    positives = []
    for _ in range(20):
        positives.append([
            FeatureVector(when=date(2010, m, 1), factors=frozenset({"stable"}))
            for m in range(1, 13)
        ])
    negatives = [
        [FeatureVector(when=date(2012, m, 1), factors=frozenset({"stable"}))
         for m in range(1, 13)]
        for _ in range(20)
    ]
    report = check_aggregation_symmetry(positives, negatives)
    assert report["exceeds_tolerance"] is False
    assert "symmetric" in report["verdict"]


def test_consensus_mode_ignores_transient_factors():
    """A factor present in only one month of a year is not consensus."""
    positives = [[
        FeatureVector(when=date(2010, m, 1), factors=frozenset(
            {"transient"} if m == 3 else {"persistent"}
        ))
        for m in range(1, 13)
    ]]
    negatives = [make_vector(date(2012, 1, 1), {"persistent"}) for _ in range(30)]

    consensus = compute_associations(
        EventCategory.CAREER, positives, negatives,
        aggregation=Aggregation.CONSENSUS, min_support=0,
    )
    names = {a.factor for a in consensus}
    assert "persistent" in names
    assert "transient" not in names
