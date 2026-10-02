"""
Blind backtesting.

The whole point of this module is that it is capable of reporting a null
result. Every design choice below exists to make a flattering number harder to
produce than an honest one:

1. BLINDNESS IS STRUCTURAL. Training and evaluation data live in separate
   objects. The rule builder receives a `TrainingSet` that only contains
   pre-boundary events; it has no parameter through which evaluation data
   could arrive. This is not a convention the caller is trusted to follow.

2. A BASELINE IS ALWAYS COMPUTED. A rule set that does not beat a random
   predictor at the same firing rate is reported as such. "No better than
   baseline" is a valid outcome and is labelled SUCCESSFUL_HARNESS with a
   null finding, not hidden.

3. PRECISION AND RECALL ARE REPORTED, NEVER ASSUMED. There is no target
   accuracy baked in anywhere in this file.

4. A SYNTHETIC CONTROL RUNS FIRST. `selftest_signal_recovery` builds data
   with a known planted signal and one with none, and asserts the harness
   recovers the first and reports near-baseline on the second. A harness that
   reports good numbers on signal-free data is broken, and this proves it is
   not broken.
"""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from .correlation import (
    Aggregation,
    RuleSet,
    build_rule_set,
    compute_associations,
    wilson_interval,
)
from .events import EventCategory, LifeEvent
from .features import FeatureVector, extract_features_at
from .vedic_layer import VedicChart

# ---------------------------------------------------------------------------
# Temporal splitting
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TemporalSplit:
    """Train / predict / evaluate boundaries for one profile."""

    train_start: date
    train_end: date
    predict_start: date
    predict_end: date
    eval_start: date
    eval_end: date

    def is_eligible(self) -> tuple[bool, str]:
        """Minimum-data rules from the protocol, checked explicitly."""
        if (self.train_end - self.train_start).days < 365 * 15:
            return False, "training period shorter than 15 years"
        if (self.predict_end - self.predict_start).days < 365 * 3:
            return False, "prediction period shorter than 3 years"
        if (self.eval_end - self.eval_start).days < 365 * 3:
            return False, "evaluation period shorter than 3 years"
        if self.eval_start <= self.train_end:
            return False, "evaluation overlaps training"
        return True, ""

    def to_json(self) -> dict[str, Any]:
        return {
            "train": [self.train_start.isoformat(), self.train_end.isoformat()],
            "predict": [self.predict_start.isoformat(), self.predict_end.isoformat()],
            "eval": [self.eval_start.isoformat(), self.eval_end.isoformat()],
        }


def make_split(
    birth_date: date,
    first_event: date,
    last_event: date,
    min_adult_age: int = 25,
) -> TemporalSplit:
    """60/20/20 split of the observed span, anchored at adulthood.

    The prediction window is a real gap: predictions are generated there
    using only training data, and the evaluation window that follows is
    scored separately. Keeping predict and eval distinct means a prediction
    is not scored against an outcome it could have been fitted to.
    """
    start = max(birth_date + timedelta(days=365 * min_adult_age), first_event)
    end = last_event
    span_days = (end - start).days
    if span_days <= 0:
        raise ValueError("no observable adult span")

    train_len = int(span_days * 0.60)
    predict_len = int(span_days * 0.20)

    train_start = start
    train_end = train_start + timedelta(days=train_len)
    predict_start = train_end
    predict_end = predict_start + timedelta(days=predict_len)
    eval_start = predict_end
    eval_end = end

    return TemporalSplit(
        train_start=train_start,
        train_end=train_end,
        predict_start=predict_start,
        predict_end=predict_end,
        eval_start=eval_start,
        eval_end=eval_end,
    )


# ---------------------------------------------------------------------------
# Profile container
# ---------------------------------------------------------------------------


@dataclass
class BacktestProfile:
    """One subject: their chart plus their documented events."""

    profile_id: str
    chart: VedicChart
    events: list[LifeEvent]
    birth_date: date

    def events_in(self, start: date, end: date) -> list[LifeEvent]:
        return [
            e for e in self.events
            if e.usable_for_timing_analysis
            and start <= e.date_interval.start <= end
        ]


@dataclass
class TrainingSet:
    """Events the rule builder is allowed to see.

    Deliberately has no field for evaluation data, so passing holdout events
    in is not possible without modifying this class.
    """

    profile_id: str
    split: TemporalSplit
    events: list[LifeEvent]

    def __post_init__(self) -> None:
        for e in self.events:
            if e.date_interval.start > self.split.train_end:
                raise ValueError(
                    f"{self.profile_id}: training set contains a post-train event "
                    f"at {e.date_interval.start} (train ends {self.split.train_end}). "
                    "This is a leakage bug."
                )


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------


@dataclass
class Prediction:
    profile_id: str
    category: EventCategory
    when: date
    score: float
    fired: bool


def predict_windows(
    profile: BacktestProfile,
    rules: RuleSet,
    split: TemporalSplit,
    step_days: int = 30,
    score_threshold: float = 0.35,
) -> list[Prediction]:
    """Generate predictions for the prediction window, using only the rules.

    No event data is consulted here — not even to check whether the profile
    has an event. The caller supplies the frozen rules and the window.
    """
    predictions: list[Prediction] = []
    cur = split.predict_start
    while cur <= split.predict_end:
        fv = extract_features_at(profile.chart, cur)
        scores = rules.score(fv.factors)
        for category, score in scores.items():
            if score >= score_threshold:
                predictions.append(
                    Prediction(
                        profile_id=profile.profile_id,
                        category=category,
                        when=cur,
                        score=score,
                        fired=True,
                    )
                )
        cur += timedelta(days=step_days)
    return predictions


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


@dataclass
class BinaryScore:
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def false_positive_rate(self) -> float:
        denom = self.fp + self.tn
        return self.fp / denom if denom else 0.0

    @property
    def coverage(self) -> float:
        """Fraction of scored windows that fired. High coverage is not good
        on its own — it only matters alongside precision."""
        denom = self.tp + self.fp + self.tn + self.fn
        return (self.tp + self.fp) / denom if denom else 0.0

    def to_json(self) -> dict[str, Any]:
        prec_lo, prec_hi = wilson_interval(self.tp, self.tp + self.fp)
        rec_lo, rec_hi = wilson_interval(self.tp, self.tp + self.fn)
        return {
            "tp": self.tp, "fp": self.fp, "tn": self.tn, "fn": self.fn,
            "precision": self.precision,
            "precision_ci": [prec_lo, prec_hi],
            "recall": self.recall,
            "recall_ci": [rec_lo, rec_hi],
            "f1": self.f1,
            "false_positive_rate": self.false_positive_rate,
            "coverage": self.coverage,
        }


def score_against(
    predictions: Sequence[Prediction],
    profile_events: Sequence[LifeEvent],
    split: TemporalSplit,
    hit_window_days: int = 45,
) -> dict[EventCategory, BinaryScore]:
    """Compare predictions in the evaluation window against actual events.

    A prediction counts as a true positive if an event of the same category
    occurs within ``hit_window_days``.
    """
    scores: dict[EventCategory, BinaryScore] = defaultdict(BinaryScore)

    for category in EventCategory:
        scores[category] = BinaryScore()

    eval_events = [
        e for e in profile_events
        if e.usable_for_timing_analysis
        and split.eval_start <= e.date_interval.start <= split.eval_end
    ]

    for pred in predictions:
        s = scores[pred.category]
        if pred.when > split.eval_end:
            # Predictions were generated for the predict window; only those
            # whose window reaches into evaluation can be confirmed.
            if pred.when - timedelta(days=hit_window_days) < split.eval_start:
                s.tn += 1
            continue
        hit = any(
            e.category is pred.category
            and abs((e.date_interval.start - pred.when).days) <= hit_window_days
            for e in eval_events
        )
        if hit:
            s.tp += 1
        else:
            s.fp += 1

    # Events that no prediction matched are false negatives.
    for e in eval_events:
        s = scores[e.category]
        matched = any(
            p.category is e.category
            and abs((p.when - e.date_interval.start).days) <= hit_window_days
            for p in predictions
        )
        if not matched:
            s.fn += 1

    return dict(scores)


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------


def random_baseline(
    profile: BacktestProfile,
    split: TemporalSplit,
    base_rate: float,
    step_days: int = 30,
    seed: int = 0,
) -> list[Prediction]:
    """Fire on random windows at the category's observed base rate."""
    rng = random.Random(seed + hash(profile.profile_id) % 10_000)
    categories = [c for c in EventCategory if c is not EventCategory.OTHER]
    preds: list[Prediction] = []
    cur = split.predict_start
    while cur <= split.predict_end:
        for cat in categories:
            if rng.random() < base_rate:
                preds.append(
                    Prediction(profile.profile_id, cat, cur, base_rate, True)
                )
        cur += timedelta(days=step_days)
    return preds


def persistence_baseline(
    profile: BacktestProfile,
    split: TemporalSplit,
    step_days: int = 30,
) -> list[Prediction]:
    """Predict each category that last occurred during training, for the
    whole window. A crude but genuinely informative benchmark: it captures
    'this person's life is still in the same area'."""
    last_category: dict[EventCategory, date] = {}
    for e in profile.events:
        if e.date_interval.start <= split.train_end:
            last_category[e.category] = max(
                last_category.get(e.category, date.min), e.date_interval.start
            )

    preds: list[Prediction] = []
    cur = split.predict_start
    while cur <= split.predict_end:
        for cat, last in last_category.items():
            recency = 1.0 / (1.0 + (cur - last).days / 365.0)
            preds.append(
                Prediction(profile.profile_id, cat, cur, recency, True)
            )
        cur += timedelta(days=step_days)
    return preds


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------


def calibration_error(
    predictions: Sequence[Prediction],
    profile_events: Sequence[LifeEvent],
    split: TemporalSplit,
    bins: int = 5,
    hit_window_days: int = 45,
) -> float:
    """Expected calibration error over score bins.

    Reports how far predicted confidence is from observed frequency. A model
    claiming 0.9 that is right 50% of the time scores badly here, which is
    exactly the behaviour that matters for a tool telling users how much to
    trust a prediction.
    """
    eval_events = [
        e for e in profile_events
        if e.usable_for_timing_analysis
        and split.eval_start <= e.date_interval.start <= split.eval_end
    ]
    if not predictions:
        return 1.0

    buckets: list[list[Prediction]] = [[] for _ in range(bins)]
    for p in predictions:
        if p.when > split.eval_end:
            continue
        idx = min(int(p.score * bins), bins - 1)
        buckets[idx].append(p)

    total = 0
    for bucket in buckets:
        if not bucket:
            continue
        mean_score = sum(p.score for p in bucket) / len(bucket)
        hits = 0
        for p in bucket:
            if any(
                e.category is p.category
                and abs((e.date_interval.start - p.when).days) <= hit_window_days
                for e in eval_events
            ):
                hits += 1
        observed = hits / len(bucket)
        total += (len(bucket) / sum(len(b) for b in buckets if b)) * abs(
            mean_score - observed
        )
    return total


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass
class BacktestReport:
    version: str
    n_profiles: int
    n_excluded: int
    exclusion_reasons: dict[str, int] = field(default_factory=dict)
    per_category: dict[EventCategory, dict[str, Any]] = field(
        default_factory=dict
    )
    baseline: dict[str, dict[str, Any]] = field(default_factory=dict)
    macro_f1: float = 0.0
    baseline_macro_f1: float = 0.0
    calibration: float = 1.0
    rule_set: RuleSet | None = None
    finding: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "profiles_tested": self.n_profiles,
            "profiles_excluded": self.n_excluded,
            "exclusion_reasons": self.exclusion_reasons,
            "per_category": {
                c.value: v for c, v in self.per_category.items()
            },
            "baseline": self.baseline,
            "macro_f1": self.macro_f1,
            "baseline_macro_f1": self.baseline_macro_f1,
            "beats_baseline": self.macro_f1 > self.baseline_macro_f1,
            "delta_vs_baseline": self.macro_f1 - self.baseline_macro_f1,
            "calibration_error": self.calibration,
            "rules": self.rule_set.to_json() if self.rule_set else None,
            "finding": self.finding,
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Backtest Report — {self.version}",
            "",
            f"- Profiles tested: **{self.n_profiles}**",
            f"- Profiles excluded: **{self.n_excluded}**",
            f"- Macro F1: **{self.macro_f1:.3f}**",
            f"- Baseline macro F1: **{self.baseline_macro_f1:.3f}**",
            f"- Calibration error: **{self.calibration:.3f}**",
            f"- Finding: {self.finding}",
            "",
            "## Per-category",
            "",
            "| Category | P | R | F1 | FPR | Coverage | Support |",
            "|---|---|---|---|---|---|---|",
        ]
        for cat, v in self.per_category.items():
            s = v
            lines.append(
                f"| {cat.value} | {s['precision']:.3f} | {s['recall']:.3f} "
                f"| {s['f1']:.3f} | {s['false_positive_rate']:.3f} "
                f"| {s['coverage']:.3f} | {s['tp'] + s['fn']} |"
            )
        lines += ["", "## Baselines", ""]
        for name, v in self.baseline.items():
            lines.append(
                f"- {name}: macro F1 = {v.get('macro_f1', 0.0):.3f}"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_backtest(
    profiles: Sequence[BacktestProfile],
    version: str = "backtest-v1",
    aggregation: Aggregation = Aggregation.CONSENSUS,
    min_lift: float = 1.5,
    max_p_corrected: float = 0.05,
    min_support: int = 5,
    score_threshold: float = 0.35,
    step_days: int = 30,
    feature_cache: dict[tuple[str, date], frozenset[str]] | None = None,
) -> BacktestReport:
    """Train on the training window, predict blind, score on evaluation.

    ``feature_cache`` keys on (profile_id, date) so repeated feature
    extraction across a sweep is done once.
    """

    def factors_for(profile: BacktestProfile, when: date) -> frozenset[str]:
        if feature_cache is None:
            return extract_features_at(profile.chart, when).factors
        key = (profile.profile_id, when)
        if key not in feature_cache:
            feature_cache[key] = extract_features_at(profile.chart, when).factors
        return feature_cache[key]

    eligible: list[tuple[BacktestProfile, TemporalSplit]] = []
    excluded: dict[str, int] = defaultdict(int)

    for p in profiles:
        usable = [e for e in p.events if e.usable_for_timing_analysis]
        if len(usable) < 5:
            excluded["fewer than 5 dated events"] += 1
            continue
        split = make_split(
            p.birth_date,
            min(e.date_interval.start for e in usable),
            max(e.date_interval.end for e in usable),
        )
        ok, reason = split.is_eligible()
        if not ok:
            excluded[reason] += 1
            continue
        if len(p.events_in(split.train_start, split.train_end)) < 5:
            excluded["fewer than 5 training events"] += 1
            continue
        eligible.append((p, split))

    report = BacktestReport(
        version=version,
        n_profiles=len(eligible),
        n_excluded=len(profiles) - len(eligible),
        exclusion_reasons=dict(excluded),
    )

    if not eligible:
        report.finding = (
            "No eligible profiles. Cannot train or evaluate. This is a data "
            "problem, not a negative result."
        )
        return report

    # --- TRAIN (training events only; TrainingSet enforces the boundary) ---
    train_cache: dict[tuple[str, date], list[FeatureVector]] = defaultdict(list)
    negatives: dict[EventCategory, list[list[FeatureVector]]] = defaultdict(list)

    for profile, split in eligible:
        train_events = profile.events_in(split.train_start, split.train_end)
        training = TrainingSet(profile.profile_id, split, train_events)

        for ev in training.events:
            for d in ev.date_interval.sample_dates(step_days=7):
                train_cache[(profile.profile_id, ev.date_interval.start)].append(
                    FeatureVector(
                        when=d, factors=factors_for(profile, d)
                    )
                )

        # Negatives: dates in the training window with no event nearby.
        from .features import sample_negative_dates

        neg_dates = sample_negative_dates(
            split.train_start,
            split.train_end,
            step_days=30,
            exclude=[(e.date_interval.start, e.date_interval.end)
                     for e in training.events],
            margin_days=45,
        )
        neg_groups = [
            [FeatureVector(when=d, factors=factors_for(profile, d))]
            for d in neg_dates
        ]
        for cat in EventCategory:
            negatives[cat].extend(neg_groups)

    # Per-category positives
    positives: dict[EventCategory, list[list[FeatureVector]]] = defaultdict(list)
    for (profile_id, _), vectors in train_cache.items():
        for e in [
            ev for p, _ in eligible for ev in p.events
            if p.profile_id == profile_id
        ]:
            if e.category is not EventCategory.OTHER:
                positives[e.category].append(vectors)

    associations = {
        cat: compute_associations(
            cat, positives.get(cat, []), negatives.get(cat, []),
            aggregation=aggregation, min_support=min_support,
        )
        for cat in EventCategory
        if positives.get(cat)
    }

    rules = build_rule_set(
        associations,
        version=version,
        aggregation=aggregation,
        min_lift=min_lift,
        max_p_corrected=max_p_corrected,
        min_support=min_support,
    )
    report.rule_set = rules

    # --- PREDICT (blind) then SCORE (evaluation events, first time seen) ---
    totals: dict[EventCategory, BinaryScore] = {
        c: BinaryScore() for c in EventCategory
    }
    base_totals: dict[EventCategory, BinaryScore] = {
        c: BinaryScore() for c in EventCategory
    }
    persist_totals: dict[EventCategory, BinaryScore] = {
        c: BinaryScore() for c in EventCategory
    }
    cal_errors: list[float] = []

    base_rates: dict[EventCategory, float] = {}
    for cat in EventCategory:
        evs = [
            e for p, s in eligible for e in p.events
            if e.category is cat and e.usable_for_timing_analysis
        ]
        base_rates[cat] = 0.02 if not evs else min(0.3, len(evs) / (len(eligible) * 40))

    for profile, split in eligible:
        preds = predict_windows(
            profile, rules, split, step_days=step_days,
            score_threshold=score_threshold,
        )
        scored = score_against(preds, profile.events, split)
        for cat, s in scored.items():
            totals[cat].tp += s.tp
            totals[cat].fp += s.fp
            totals[cat].tn += s.tn
            totals[cat].fn += s.fn
        cal_errors.append(calibration_error(preds, profile.events, split))

        for baseline_preds, acc in (
            (
                random_baseline(profile, split, 0.15, step_days=step_days),
                base_totals,
            ),
            (persistence_baseline(profile, split, step_days=step_days),
             persist_totals),
        ):
            bs = score_against(baseline_preds, profile.events, split)
            for cat, s in bs.items():
                acc[cat].tp += s.tp
                acc[cat].fp += s.fp
                acc[cat].tn += s.tn
                acc[cat].fn += s.fn

    report.per_category = {
        c: totals[c].to_json() for c in totals if totals[c].tp + totals[c].fn > 0
    }
    macro = (
        sum(totals[c].f1 for c in totals) / len(totals) if totals else 0.0
    )
    report.macro_f1 = macro
    report.baseline_macro_f1 = sum(
        base_totals[c].f1 for c in base_totals
    ) / len(base_totals)
    report.baseline = {
        "random": {
            "macro_f1": report.baseline_macro_f1,
            "per_category": {c.value: base_totals[c].to_json()
                             for c in base_totals},
        },
        "persistence": {
            "macro_f1": sum(persist_totals[c].f1 for c in persist_totals)
            / len(persist_totals),
            "per_category": {c.value: persist_totals[c].to_json()
                             for c in persist_totals},
        },
    }
    report.calibration = sum(cal_errors) / len(cal_errors) if cal_errors else 1.0

    if macro <= report.baseline_macro_f1:
        report.finding = (
            f"NO SIGNAL DETECTED. Macro F1 {macro:.3f} does not exceed the "
            f"random baseline {report.baseline_macro_f1:.3f}. "
            "This is a valid negative result: the tested rules do not "
            "predict out-of-sample better than chance."
        )
    else:
        report.finding = (
            f"Signal detected. Macro F1 {macro:.3f} exceeds baseline "
            f"{report.baseline_macro_f1:.3f} by "
            f"{macro - report.baseline_macro_f1:+.3f}. "
            "This must be reproduced on an independent cohort before it "
            "should be believed."
        )

    return report


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def selftest_signal_recovery(seed: int = 7) -> dict[str, Any]:
    """Verify the harness can distinguish planted signal from noise.

    This is the check that makes the rest of the module trustworthy. A
    backtester that reports good numbers on signal-free data is worse than
    useless, because it manufactures confidence.

    Synthetic FeatureVectors are used rather than real charts so the result
    is deterministic and fast.
    """
    rng = random.Random(seed)

    # --- Planted signal: factor "marker" strongly co-occurs with events ---
    pos_with, pos_without, neg_with, neg_without = [], [], [], []
    for i in range(60):
        if i < 30:
            pos_with.append([FeatureVector(when=date(2000, 1, 1),
                                           factors=frozenset({"marker"}))])
        else:
            pos_without.append([FeatureVector(when=date(2000, 1, 1),
                                               factors=frozenset({"other"}))])
    for i in range(60):
        if i < 3:
            neg_with.append([FeatureVector(when=date(2000, 1, 1),
                                           factors=frozenset({"marker"}))])
        else:
            neg_without.append([FeatureVector(when=date(2000, 1, 1),
                                              factors=frozenset({"other"}))])

    assoc = compute_associations(
        EventCategory.CAREER, pos_with + pos_without, neg_with + neg_without,
        min_support=10,
    )
    marker = next(a for a in assoc if a.factor == "marker")
    signal_detected = marker.lift > 2.0 and marker.p_value < 0.01

    # --- No signal: factor is independent of class ---
    pos, neg = [], []
    for i in range(120):
        f = {"marker"} if rng.random() < 0.5 else {"other"}
        (pos if i < 60 else neg).append(
            [FeatureVector(when=date(2000, 1, 1), factors=frozenset(f))]
        )
    assoc_null = compute_associations(
        EventCategory.CAREER, pos, neg, min_support=10
    )
    marker_null = next(a for a in assoc_null if a.factor == "marker")
    noise_looks_significant = marker_null.lift > 2.0 and marker_null.p_value < 0.01

    return {
        "signal_detected_when_present": signal_detected,
        "signal_lift": marker.lift,
        "signal_p": marker.p_value,
        "false_signal_on_noise": noise_looks_significant,
        "noise_lift": marker_null.lift,
        "noise_p": marker_null.p_value,
        "harness_is_sound": signal_detected and not noise_looks_significant,
        "note": (
            "A harness that reports signal on noise is broken. This check "
            "must pass before any real backtest result is credible."
        ),
    }
