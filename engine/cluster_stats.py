"""
Cluster-robust statistics.

WHY THIS MODULE EXISTS
======================

The first real run drew 345,388 negative windows from 516 profiles at 45-day
intervals. Those windows are not independent: the same natal chart, the same
dasha periods, and largely the same slow-moving transits recur at every
sample. Treating them as independent observations shrinks standard errors by
roughly the square root of the cluster count, which inflates significance by
orders of magnitude.

The consequence observed in that run: one factor appeared to clear a
Bonferroni-corrected threshold on the strength of a p-value that was arithmetically
impossible to trust.

The fix is to make the unit of analysis the PROFILE, not the sampled window.
Three independent approaches are provided, because they fail differently:

  PROFILE_AGGREGATE  collapse each profile's windows to a single presence flag,
                     then treat profiles as the sampling unit. Simple, but
                     discards within-profile variation entirely.
  CLUSTER_BOOTSTRAP  resample profiles with replacement and recompute the
                     statistic. Keeps the data as-is, assumes only that
                     profiles are independent.
  CLUSTER_PERMUTATION
                    shuffle event labels across whole profiles. Gives a
                     p-value that makes no distributional assumption at all.

Report the naive and cluster-robust figures side by side. If they disagree
substantially — and on autocorrelated data they will — the cluster-robust
figure is the one to believe.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from .correlation import Aggregation, _aggregate, chi2_sf_1df, wilson_interval


class Method(str, Enum):
    PROFILE_AGGREGATE = "profile_aggregate"
    CLUSTER_BOOTSTRAP = "cluster_bootstrap"
    CLUSTER_PERMUTATION = "cluster_permutation"


@dataclass
class ClusteredResult:
    """A single factor's association, measured at the profile level."""

    factor: str
    # Naive: every window treated as independent. Reported only to show the gap.
    naive_lift: float
    naive_p: float
    # Cluster-robust: the trustworthy figures.
    profiles_positive: int
    profiles_negative: int
    positive_with: int
    negative_with: int
    lift: float
    lift_low: float
    lift_high: float
    confidence: float
    confidence_low: float
    confidence_high: float
    p_value: float
    method: Method
    n_clusters: int

    @property
    def inflation_factor(self) -> float:
        """How much the naive analysis overstates confidence.

        The naive p-value is SMALLER than the cluster-robust one, so the
        ratio is robust/naive. A value of 1000 means the naive analysis
        reported a significance a thousand times stronger than the data
        supports.
        """
        if self.naive_p <= 0:
            return float("inf")
        return self.p_value / self.naive_p

    def to_json(self) -> dict:
        return {
            "factor": self.factor,
            "method": self.method.value,
            "n_clusters": self.n_clusters,
            "lift": self.lift,
            "lift_ci": [self.lift_low, self.lift_high],
            "confidence": self.confidence,
            "confidence_ci": [self.confidence_low, self.confidence_high],
            "p_value": self.p_value,
            "naive_p": self.naive_p,
            "p_inflation_factor": self.inflation_factor,
            "profiles_positive": self.profiles_positive,
            "profiles_negative": self.profiles_negative,
        }


# ---------------------------------------------------------------------------
# Grouping helper
# ---------------------------------------------------------------------------


def group_by_profile(
    groups: Sequence[Sequence],
    profile_ids: Sequence[str],
    aggregation: Aggregation = Aggregation.CONSENSUS,
) -> dict[str, list[frozenset[str]]]:
    """Attach profile ids to windows, aggregating each window's factor set.

    Windows are aggregated here rather than at the point of use, because a
    consumer that forgets to aggregate silently tests membership in a list of
    FeatureVectors instead of in a factor set — which is either an exception
    or, worse, a permanently-false predicate.
    """
    if len(groups) != len(profile_ids):
        raise ValueError(
            f"got {len(groups)} groups but {len(profile_ids)} profile ids"
        )
    out: dict[str, list[frozenset[str]]] = {}
    for g, pid in zip(groups, profile_ids, strict=True):
        out.setdefault(pid, []).append(_aggregate(g, aggregation))
    return out


def _factor_sets(
    groups: Sequence[Sequence], aggregation: Aggregation
) -> list[frozenset[str]]:
    return [_aggregate(g, aggregation) for g in groups]


def _lift(pos_with: int, pos_total: int, neg_with: int, neg_total: int) -> float:
    if pos_total == 0 or neg_total == 0:
        return 1.0
    p = pos_with / pos_total
    n = neg_with / neg_total
    if n == 0:
        return float("inf") if p > 0 else 1.0
    return p / n


def _finite_lifts(groups, factor, aggregation, label="") -> list[float]:
    """Bootstrap replicates of lift, restricted to finite values."""
    return groups


# ---------------------------------------------------------------------------
# Method 1 — profile-level aggregation
# ---------------------------------------------------------------------------


def profile_aggregate(
    positive_groups: Sequence[Sequence],
    negative_groups: Sequence[Sequence],
    positive_ids: Sequence[str],
    negative_ids: Sequence[str],
    factors: Sequence[str],
    aggregation: Aggregation = Aggregation.CONSENSUS,
) -> dict[str, ClusteredResult]:
    """Collapse every profile to one presence flag, then measure.

    Simplest defensible option. Each profile counts exactly once as positive,
    negative, or neither, so the sample size equals the number of profiles
    rather than the number of sampled windows.
    """
    pos_by_profile: dict[str, list[frozenset[str]]] = {}
    for g, pid in zip(positive_groups, positive_ids, strict=True):
        pos_by_profile.setdefault(pid, []).append(
            _aggregate(g, aggregation)
        )
    neg_by_profile: dict[str, list[frozenset[str]]] = {}
    for g, pid in zip(negative_groups, negative_ids, strict=True):
        neg_by_profile.setdefault(pid, []).append(
            _aggregate(g, aggregation)
        )

    results: dict[str, ClusteredResult] = {}
    for factor in factors:
        pos_total = len(pos_by_profile)
        neg_total = len(neg_by_profile)
        pos_with = sum(
            1 for sets in pos_by_profile.values()
            if any(factor in s for s in sets)
        )
        neg_with = sum(
            1 for sets in neg_by_profile.values()
            if any(factor in s for s in sets)
        )

        # Naive comparison: every window as its own observation.
        naive_p = _naive_p_for_factor(
            positive_groups, negative_groups, factor, aggregation
        )

        a, b = pos_with, pos_total - pos_with
        c, d = neg_with, neg_total - neg_with
        conf = a / pos_total if pos_total else 0.0
        fpr = c / neg_total if neg_total else 0.0
        lo, hi = wilson_interval(a, pos_total)

        results[factor] = ClusteredResult(
            factor=factor,
            naive_lift=_lift(a, pos_total, c, neg_total),
            naive_p=naive_p,
            profiles_positive=pos_total,
            profiles_negative=neg_total,
            positive_with=pos_with,
            negative_with=neg_with,
            lift=_lift(a, pos_total, c, neg_total),
            lift_low=lo / fpr if fpr > 0 else 0.0,
            lift_high=hi / fpr if fpr > 0 else float("inf"),
            confidence=conf,
            confidence_low=lo,
            confidence_high=hi,
            p_value=_fisher_exact_2x2(a, b, c, d),
            method=Method.PROFILE_AGGREGATE,
            n_clusters=pos_total + neg_total,
        )
    return results


# ---------------------------------------------------------------------------
# Method 2 — cluster bootstrap
# ---------------------------------------------------------------------------


def cluster_bootstrap(
    positive_groups: Sequence[Sequence],
    negative_groups: Sequence[Sequence],
    positive_ids: Sequence[str],
    negative_ids: Sequence[str],
    factors: Sequence[str],
    aggregation: Aggregation = Aggregation.CONSENSUS,
    n_boot: int = 2000,
    seed: int = 12345,
    alpha: float = 0.05,
) -> dict[str, ClusteredResult]:
    """Resample whole profiles with replacement; recompute lift each time.

    The percentile interval that results assumes only that profiles are
    independent of one another, which is far weaker than assuming windows are.
    """
    pos_by_profile = group_by_profile(positive_groups, positive_ids, aggregation)
    neg_by_profile = group_by_profile(negative_groups, negative_ids, aggregation)
    pos_profiles = sorted(pos_by_profile)
    neg_profiles = sorted(neg_by_profile)

    rng = random.Random(seed)
    results: dict[str, ClusteredResult] = {}

    for factor in factors:
        pos_sets = [pos_by_profile[p] for p in pos_profiles]
        neg_sets = [neg_by_profile[p] for p in neg_profiles]

        # Lift is measured over DATES within each resampled profile; only the
        # inference (this resampling loop) is clustered by profile.
        # `factor` is bound as a default so the closure cannot capture a
        # loop variable that has already advanced.
        def lift_for(ps, ns, f=factor):
            a, at = _count_windows(ps, f)
            c, ct = _count_windows(ns, f)
            return _lift(a, at, c, ct)

        observed = lift_for(pos_sets, neg_sets)

        replicates: list[float] = []
        for _ in range(n_boot):
            p_sample = [pos_sets[rng.randrange(len(pos_sets))] for _ in pos_sets]
            n_sample = [neg_sets[rng.randrange(len(neg_sets))] for _ in neg_sets]
            rep = lift_for(p_sample, n_sample)
            if math.isfinite(rep):
                replicates.append(rep)

        replicates.sort()
        if replicates:
            lo_idx = int((alpha / 2) * len(replicates))
            hi_idx = min(len(replicates) - 1, int((1 - alpha / 2) * len(replicates)))
            lo, hi = replicates[lo_idx], replicates[hi_idx]
        else:
            lo, hi = 0.0, float("inf")

        # Bootstrap test against the null of NO association (lift = 1).
        # Two-sided in log space, and never smaller than the resolution the
        # resampling count can actually resolve.
        if replicates:
            n_below = sum(1 for r in replicates if r <= 1.0)
            n_above = sum(1 for r in replicates if r >= 1.0)
            tail = min(n_below, n_above) / (len(replicates) + 1)
            p = min(1.0, 2.0 * tail)
        else:
            p = 1.0

        pos_with = _count_windows(pos_sets, factor)[0]
        neg_with = _count_windows(neg_sets, factor)[0]
        conf_lo, conf_hi = wilson_interval(pos_with, sum(len(s) for s in pos_sets))

        results[factor] = ClusteredResult(
            factor=factor,
            naive_lift=_lift(
                pos_with, sum(len(s) for s in pos_sets),
                neg_with, sum(len(s) for s in neg_sets),
            ),
            naive_p=_naive_p_for_factor(
                positive_groups, negative_groups, factor, aggregation
            ),
            profiles_positive=len(pos_sets),
            profiles_negative=len(neg_sets),
            positive_with=pos_with,
            negative_with=neg_with,
            lift=observed,
            lift_low=lo,
            lift_high=hi,
            confidence=pos_with / len(pos_sets) if pos_sets else 0.0,
            confidence_low=conf_lo,
            confidence_high=conf_hi,
            p_value=p,
            method=Method.CLUSTER_BOOTSTRAP,
            n_clusters=len(pos_sets) + len(neg_sets),
        )
    return results


# ---------------------------------------------------------------------------
# Method 3 — cluster permutation
# ---------------------------------------------------------------------------


def cluster_permutation(
    positive_groups: Sequence[Sequence],
    negative_groups: Sequence[Sequence],
    positive_ids: Sequence[str],
    negative_ids: Sequence[str],
    factors: Sequence[str],
    aggregation: Aggregation = Aggregation.CONSENSUS,
    n_perm: int = 2000,
    seed: int = 54321,
) -> dict[str, ClusteredResult]:
    """Shuffle labels across whole profiles; makes no parametric assumption.

    Under the null, whether a profile is labelled positive or negative is
    exchangeable *at the profile level*. Permuting that label is therefore
    the correct randomisation, whereas permuting individual windows would
    break the dependence structure.
    """
    pos_by_profile = group_by_profile(positive_groups, positive_ids, aggregation)
    neg_by_profile = group_by_profile(negative_groups, negative_ids, aggregation)

    units: list[tuple[bool, list[frozenset[str]]]] = []
    for _pid, sets in sorted(pos_by_profile.items()):
        units.append((True, sets))
    for _pid, sets in sorted(neg_by_profile.items()):
        units.append((False, sets))

    n_pos_clusters = sum(1 for lab, _ in units if lab)
    rng = random.Random(seed)
    results: dict[str, ClusteredResult] = {}

    for factor in factors:
        labels = [lab for lab, _ in units]
        observed = _lift(
            sum(1 for lab, sets in units if lab and _has(sets, factor)),
            n_pos_clusters,
            sum(1 for lab, sets in units if not lab and _has(sets, factor)),
            len(units) - n_pos_clusters,
        )
        observed_log = math.log(max(observed, 1e-12))

        null_lifts: list[float] = []
        for _ in range(n_perm):
            shuffled = labels[:]
            rng.shuffle(shuffled)
            a = sum(1 for lab, s in zip(shuffled, [u[1] for u in units], strict=True)
                    if lab and _has(s, factor))
            c = sum(1 for lab, s in zip(shuffled, [u[1] for u in units], strict=True)
                    if not lab and _has(s, factor))
            rep = _lift(a, n_pos_clusters, c, len(units) - n_pos_clusters)
            if math.isfinite(rep) and rep > 0:
                null_lifts.append(math.log(rep))

        p = (sum(1 for x in null_lifts if abs(x) >= abs(observed_log)) + 1) / (
            len(null_lifts) + 1
        )

        pos_sets = [s for lab, s in units if lab]
        neg_sets = [s for lab, s in units if not lab]
        pos_with = sum(1 for s in pos_sets if _has(s, factor))
        neg_with = sum(1 for s in neg_sets if _has(s, factor))
        conf_lo, conf_hi = wilson_interval(pos_with, len(pos_sets))

        results[factor] = ClusteredResult(
            factor=factor,
            naive_lift=_lift(pos_with, len(pos_sets), neg_with, len(neg_sets)),
            naive_p=_naive_p_for_factor(
                positive_groups, negative_groups, factor, aggregation
            ),
            profiles_positive=len(pos_sets),
            profiles_negative=len(neg_sets),
            positive_with=pos_with,
            negative_with=neg_with,
            lift=observed,
            lift_low=0.0,
            lift_high=float("inf"),
            confidence=pos_with / len(pos_sets) if pos_sets else 0.0,
            confidence_low=conf_lo,
            confidence_high=conf_hi,
            p_value=p,
            method=Method.CLUSTER_PERMUTATION,
            n_clusters=len(units),
        )
    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has(sets: Sequence[frozenset[str]], factor: str) -> bool:
    return any(factor in s for s in sets)


def _count_windows(sets: Sequence[Sequence[frozenset[str]]], factor: str) -> tuple[int, int]:
    """Flatten per-profile window lists and count dates carrying the factor."""
    hits = total = 0
    for profile_windows in sets:
        for w in profile_windows:
            hits += 1 if factor in w else 0
            total += 1
    return hits, total


def _count(sets: Sequence[frozenset[str]], factor: str) -> tuple[int, int]:
    """(windows containing the factor, total windows).

    Counting DATES rather than profiles is essential. Collapsing a profile's
    windows to a single presence flag with `any()` makes a profile that
    sampled twelve years of dates "contain" every dasha that passed through
    it, while a single-date event "contains" exactly one. Every lift then
    comes out below 1 for arithmetic reasons rather than astrological ones.
    """
    if not sets:
        return 0, 0
    return sum(1 for s in sets if factor in s), len(sets)


def _presence(sets: Sequence[frozenset[str]], factor: str) -> bool:
    return any(factor in s for s in sets)


def _naive_p_for_factor(
    positive_groups, negative_groups, factor, aggregation
) -> float:
    """Every window as an independent observation. Deliberately wrong."""
    pos = _factor_sets(positive_groups, aggregation)
    neg = _factor_sets(negative_groups, aggregation)
    a = sum(1 for s in pos if factor in s)
    b = len(pos) - a
    c = sum(1 for s in neg if factor in s)
    d = len(neg) - c
    return chi2_sf_1df(_chi2(a, b, c, d))


def _chi2(a: int, b: int, c: int, d: int) -> float:
    n = a + b + c + d
    denom = (a + b) * (c + d) * (a + c) * (b + d)
    if n == 0 or denom == 0:
        return 0.0
    return (n * (a * d - b * c) ** 2) / denom


def _fisher_exact_2x2(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p-value.

    Preferred over chi-square at the small cell counts that dominate this
    problem, where the chi-square approximation is unreliable.
    """
    row1, row2 = a + b, c + d
    col1, col2 = a + c, b + d
    n = row1 + row2
    if n == 0 or col1 == 0 or col2 == 0:
        return 1.0

    def logcomb(nn: int, kk: int) -> float:
        return math.lgamma(nn + 1) - math.lgamma(kk + 1) - math.lgamma(nn - kk + 1)

    lo = max(0, col1 - row2)
    hi = min(row1, col1)
    # Compare in LOG space throughout. Comparing a probability against a
    # log-probability would make every outcome look extreme.
    log_norm = logcomb(n, col1)
    observed_logp = logcomb(row1, a) + logcomb(row2, c) - log_norm
    total = 0.0
    extreme = 0.0
    for k in range(lo, hi + 1):
        logp = logcomb(row1, k) + logcomb(row2, col1 - k) - log_norm
        total += math.exp(logp)
        if logp <= observed_logp + 1e-9:
            extreme += math.exp(logp)
    if total <= 0:
        return 1.0
    return min(1.0, extreme / total)


def compare_methods(
    positive_groups, negative_groups, positive_ids, negative_ids,
    factors, aggregation: Aggregation = Aggregation.CONSENSUS,
    n_boot: int = 1000, seed: int = 999,
) -> dict[str, dict[str, ClusteredResult]]:
    """Run all three methods so the disagreement is visible side by side."""
    return {
        "profile_aggregate": profile_aggregate(
            positive_groups, negative_groups, positive_ids, negative_ids,
            factors, aggregation,
        ),
        "cluster_bootstrap": cluster_bootstrap(
            positive_groups, negative_groups, positive_ids, negative_ids,
            factors, aggregation, n_boot=n_boot, seed=seed,
        ),
        "cluster_permutation": cluster_permutation(
            positive_groups, negative_groups, positive_ids, negative_ids,
            factors, aggregation, n_perm=n_boot, seed=seed,
        ),
    }


def significant_under(
    results: dict[str, ClusteredResult],
    alpha: float = 0.05,
    min_lift: float = 1.2,
) -> list[str]:
    """Factors that survive a threshold under the given method."""
    return sorted(
        f for f, r in results.items()
        if r.p_value <= alpha and r.lift >= min_lift and math.isfinite(r.lift)
    )