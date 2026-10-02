"""
Tests for cluster-robust statistics.

The central test is `test_naive_p_value_is_violently_optimistic`, which
constructs data where the effect is entirely absent but windows are heavily
correlated within profiles. The naive analysis must report strong significance;
the cluster-robust analysis must not. If the naive test ever fails to show the
inflation, the hazard is being understated.
"""

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.cluster_stats import (  # noqa: E402
    cluster_bootstrap,
    cluster_permutation,
    compare_methods,
    group_by_profile,
    profile_aggregate,
    significant_under,
)
from engine.correlation import Aggregation  # noqa: E402
from engine.features import FeatureVector  # noqa: E402


def _vec(day: int, factors: set[str]) -> FeatureVector:
    return FeatureVector(when=date(2010, 1, 1), factors=frozenset(factors))


def _windows(pid: str, n: int, factor: str) -> list[list[FeatureVector]]:
    """n windows from one profile, ALL carrying the same factor.

    The constancy is the whole point. These windows are near-duplicates of
    one another, which is what a real chart sampled every 45 days produces.
    If the factor varied within a profile there would be no cluster
    structure and the naive analysis would be correct.
    """
    return [[_vec(i, {factor})] for i in range(n)]


# The builders return arguments in the SAME ORDER the analysis functions take
# them: (positive_groups, negative_groups, positive_ids, negative_ids, factors).
# An earlier interleaved ordering silently swapped the group and id lists.

def _null_dataset(n_profiles: int = 61, windows_per_profile: int = 30):
    """No association between the factor and the label, but heavily clustered.

    The factor is fixed by profile parity while labels are assigned by an
    independent shuffle, so the two are unrelated by construction.

    The profile count is deliberately ODD. An even count splits exactly by
    parity and produces a perfectly balanced 50/50 split, for which even the
    naive chi-square correctly reports p = 1.0 — no inflation to observe. The
    odd count leaves a one-profile discrepancy, which is nothing at the
    profile level but looks overwhelming once each profile is counted as
    thirty independent observations.

    Returns (positive_groups, negative_groups, positive_ids, negative_ids,
    factors) — the same order the analysis functions take.
    """
    import random

    rng = random.Random(4242)
    labels = ["pos"] * (n_profiles // 2) + ["neg"] * (n_profiles - n_profiles // 2)
    rng.shuffle(labels)

    pos_g, neg_g, pos_i, neg_i = [], [], [], []
    for i in range(n_profiles):
        factor = "marker" if i % 2 == 0 else "other"
        g = _windows(f"p{i}", windows_per_profile, factor)
        if labels[i] == "pos":
            pos_g.extend(g)
            pos_i.extend([f"p{i}"] * windows_per_profile)
        else:
            neg_g.extend(g)
            neg_i.extend([f"p{i}"] * windows_per_profile)
    return pos_g, neg_g, pos_i, neg_i, ["marker"]


def _real_signal_dataset(n_profiles: int = 60, windows_per_profile: int = 30):
    """A genuine association: positives carry the factor far more often.

    Some negative profiles also carry it, so the lift is finite. Infinite
    lift is deliberately excluded from rule screening, so a test that needs
    the factor to be *reportable* must not produce one.
    """
    pos_g, neg_g, pos_i, neg_i = [], [], [], []
    for i in range(n_profiles):
        if i < n_profiles // 2:
            g = _windows(f"q{i}", windows_per_profile, "marker")
            pos_g.extend(g)
            pos_i.extend([f"q{i}"] * windows_per_profile)
        else:
            factor = "marker" if i % 4 == 0 else "other"
            g = _windows(f"q{i}", windows_per_profile, factor)
            neg_g.extend(g)
            neg_i.extend([f"q{i}"] * windows_per_profile)
    return pos_g, neg_g, pos_i, neg_i, ["marker"]


def _naive_only(n_profiles: int = 60, windows_per_profile: int = 30):
    d = _null_dataset(n_profiles, windows_per_profile)
    return d[0], d[1], d[2], d[3]


# ---------------------------------------------------------------------------
# The hazard
# ---------------------------------------------------------------------------


def test_naive_p_value_is_violently_optimistic():
    """No real association, but the naive analysis claims significance."""
    pos, neg, pos_ids, neg_ids, factors = _null_dataset()

    naive = profile_aggregate(pos, neg, pos_ids, neg_ids, factors)["marker"]

    # The factor is uncorrelated with the label, so the lift should be near 1.
    assert abs(naive.lift - 1.0) < 0.5, f"lift {naive.lift}"

    # Naive treats 1830 windows as independent observations drawn from 61.
    assert naive.n_clusters < 200, "the whole point is a small cluster count"
    assert naive.naive_p < 0.01, (
        f"expected the naive p-value to look significant, got {naive.naive_p}"
    )
    assert naive.p_value > 0.05, (
        f"cluster-robust should NOT find significance, got {naive.p_value}"
    )
    # The naive analysis understates the p-value by orders of magnitude.
    assert naive.inflation_factor > 100, (
        f"inflation only {naive.inflation_factor:.0f}x; the cluster hazard "
        "may be overstated"
    )


def test_window_count_does_not_inflate_significance():
    """Ten times the windows must not buy any extra confidence."""
    pos_s, neg_s, pos_i_s, neg_i_s = _naive_only(windows_per_profile=10)
    pos_l, neg_l, pos_i_l, neg_i_l = _naive_only(windows_per_profile=100)

    small = profile_aggregate(pos_s, neg_s, pos_i_s, neg_i_s, ["marker"])["marker"]
    large = profile_aggregate(pos_l, neg_l, pos_i_l, neg_i_l, ["marker"])["marker"]

    assert large.n_clusters == small.n_clusters
    assert large.p_value > 0.05
    # The naive p-value, by contrast, shrinks hard with more windows.
    assert large.naive_p < small.naive_p


# ---------------------------------------------------------------------------
# Real signal must still be found
# ---------------------------------------------------------------------------


def test_cluster_methods_recover_a_genuine_association():
    pos, neg, pos_ids, neg_ids, factors = _real_signal_dataset()
    r = profile_aggregate(
        pos, neg, pos_ids, neg_ids, factors, Aggregation.CONSENSUS
    )["marker"]
    assert r.lift > 2.0
    assert r.p_value < 0.05
    assert significant_under({"marker": r})

    b = cluster_bootstrap(
        pos, neg, pos_ids, neg_ids, factors, n_boot=600, seed=1
    )["marker"]
    assert b.lift > 2.0
    assert b.p_value < 0.05

    p = cluster_permutation(
        pos, neg, pos_ids, neg_ids, factors, n_perm=600, seed=1
    )["marker"]
    assert p.lift > 2.0
    assert p.p_value < 0.05


def test_bootstrap_interval_brackets_the_observed_lift():
    pos, neg, pos_ids, neg_ids, factors = _real_signal_dataset()
    r = cluster_bootstrap(
        pos, neg, pos_ids, neg_ids, factors, n_boot=800, seed=7
    )["marker"]
    assert r.lift_low <= r.lift <= r.lift_high


def test_permutation_makes_no_parametric_assumption():
    pos, neg, pos_ids, neg_ids, factors = _null_dataset()
    r = cluster_permutation(
        pos, neg, pos_ids, neg_ids, factors, n_perm=600, seed=3
    )["marker"]
    assert r.p_value > 0.05, (
        "a permutation test on null data must not find signal"
    )
    assert 0.0 <= r.p_value <= 1.0


# ---------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------


def test_group_by_profile_validates_lengths():
    with pytest.raises(ValueError, match="profile ids"):
        group_by_profile([[]], ["a", "b"])


def test_cluster_count_is_profiles_not_windows():
    pos, neg, pos_ids, neg_ids, factors = _null_dataset(
        n_profiles=20, windows_per_profile=10
    )
    r = profile_aggregate(pos, neg, pos_ids, neg_ids, factors)["marker"]
    assert r.n_clusters == 20
    assert r.profiles_positive == 10
    assert r.profiles_negative == 10


def test_confidence_interval_is_wilson_bounded():
    pos, neg, pos_ids, neg_ids, factors = _real_signal_dataset()
    r = profile_aggregate(pos, neg, pos_ids, neg_ids, factors)["marker"]
    assert 0.0 <= r.confidence_low <= r.confidence <= r.confidence_high <= 1.0


def test_compare_methods_returns_all_three():
    pos, neg, pos_ids, neg_ids, factors = _real_signal_dataset()
    out = compare_methods(pos, neg, pos_ids, neg_ids, factors, n_boot=200)
    assert set(out) == {
        "profile_aggregate", "cluster_bootstrap", "cluster_permutation"
    }
    for method, results in out.items():
        assert "marker" in results
        assert results["marker"].method.value == method


def test_empty_dataset_does_not_crash():
    r = profile_aggregate([], [], [], [], ["marker"])["marker"]
    assert r.p_value == 1.0
    assert r.lift == 1.0


def test_result_serialises():
    pos, neg, pos_ids, neg_ids, factors = _real_signal_dataset()
    import json

    r = profile_aggregate(pos, neg, pos_ids, neg_ids, factors)["marker"]
    payload = json.dumps(r.to_json(), sort_keys=True)
    assert "p_inflation_factor" in payload
    assert "n_clusters" in payload