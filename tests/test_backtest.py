"""
Phase 4 tests — blind backtesting.

The most important tests here are the negative ones: the harness must report
a null result on signal-free data.
"""

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.backtest import (  # noqa: E402
    BinaryScore,
    Prediction,
    TemporalSplit,
    TrainingSet,
    calibration_error,
    make_split,
    run_backtest,
    selftest_signal_recovery,
)
from engine.events import (  # noqa: E402
    DatePrecision,
    EventCategory,
    LifeEvent,
    resolve_date_interval,
)

# ---------------------------------------------------------------------------
# Splits
# ---------------------------------------------------------------------------


def test_split_is_chronological_and_disjoint():
    s = make_split(date(1960, 1, 1), date(1990, 1, 1), date(2024, 1, 1))
    assert s.train_start < s.train_end <= s.predict_start
    assert s.predict_start < s.predict_end <= s.eval_start
    assert s.eval_start < s.eval_end


def test_split_ratios_are_approximately_60_20_20():
    s = make_split(date(1960, 1, 1), date(1985, 1, 1), date(2025, 1, 1))
    total = (s.eval_end - s.train_start).days
    train = (s.train_end - s.train_start).days
    predict = (s.predict_end - s.predict_start).days
    assert 0.55 < train / total < 0.65
    assert 0.15 < predict / total < 0.25


def test_split_starts_at_adulthood():
    """Anchored at age 25 (approximated as 365-day years, so allow slack)."""
    s = make_split(date(1960, 1, 1), date(1970, 1, 1), date(2024, 1, 1))
    assert s.train_start >= date(1984, 1, 1)
    assert s.train_start < date(1986, 1, 1)


def test_short_lifespan_is_ineligible():
    """Adulthood starts 2015 and events stop 2020, so the training window
    cannot reach the 15-year minimum."""
    s = make_split(date(1990, 1, 1), date(2010, 1, 1), date(2020, 1, 1))
    ok, reason = s.is_eligible()
    assert ok is False
    assert reason


def test_eligible_split_reports_no_reason():
    s = make_split(date(1960, 1, 1), date(1990, 1, 1), date(2024, 1, 1))
    assert s.is_eligible() == (True, "")


# ---------------------------------------------------------------------------
# Leakage prevention — the core guarantee
# ---------------------------------------------------------------------------


def test_training_set_rejects_post_training_events():
    s = make_split(date(1960, 1, 1), date(1990, 1, 1), date(2024, 1, 1))
    late = LifeEvent(
        profile_id="p1",
        category=EventCategory.CAREER,
        sub_category="promotion",
        date_interval=resolve_date_interval("2022-05-05", DatePrecision.EXACT),
    )
    with pytest.raises(ValueError, match="leakage bug"):
        TrainingSet("p1", s, [late])


def test_training_set_accepts_pre_training_events():
    s = make_split(date(1960, 1, 1), date(1990, 1, 1), date(2024, 1, 1))
    early = LifeEvent(
        profile_id="p1",
        category=EventCategory.CAREER,
        sub_category="promotion",
        date_interval=resolve_date_interval("1995-05-05", DatePrecision.EXACT),
    )
    ts = TrainingSet("p1", s, [early])
    assert len(ts.events) == 1


def test_training_set_has_no_field_for_evaluation_data():
    """Structural blindness: there is no way to pass holdout events in."""
    fields = set(TrainingSet.__dataclass_fields__)
    assert "eval_events" not in fields
    assert "test_events" not in fields
    assert set(fields) == {"profile_id", "split", "events"}


# ---------------------------------------------------------------------------
# Scoring arithmetic
# ---------------------------------------------------------------------------


def test_binary_score_metrics():
    s = BinaryScore(tp=8, fp=2, tn=80, fn=2)
    assert s.precision == pytest.approx(0.8)
    assert s.recall == pytest.approx(0.8)
    assert s.f1 == pytest.approx(0.8)
    assert s.false_positive_rate == pytest.approx(2 / 82, abs=1e-3)
    assert s.coverage == pytest.approx(10 / 92)


def test_binary_score_handles_empty():
    s = BinaryScore()
    assert s.precision == 0.0
    assert s.recall == 0.0
    assert s.f1 == 0.0


def test_precision_zero_when_no_predictions():
    s = BinaryScore(tp=0, fp=0, tn=10, fn=5)
    assert s.precision == 0.0
    assert s.recall == 0.0


# ---------------------------------------------------------------------------
# Scoring against events
# ---------------------------------------------------------------------------


def _event(cat, when):
    from engine.events import SUB_CATEGORIES

    sub = sorted(SUB_CATEGORIES[cat])[0]
    return LifeEvent(
        profile_id="p1",
        category=cat,
        sub_category=sub,
        date_interval=resolve_date_interval(when.isoformat(), DatePrecision.EXACT),
    )


def test_prediction_near_event_is_a_true_positive():
    split = TemporalSplit(
        date(1990, 1, 1), date(2000, 1, 1),
        date(2000, 1, 1), date(2010, 1, 1),
        date(2010, 1, 1), date(2020, 1, 1),
    )
    preds = [Prediction("p1", EventCategory.CAREER, date(2012, 6, 1), 0.8, True)]
    events = [_event(EventCategory.CAREER, date(2012, 7, 1))]

    scored = _score(preds, events, split)
    assert scored[EventCategory.CAREER].tp == 1
    assert scored[EventCategory.CAREER].fp == 0


def test_prediction_far_from_event_is_a_false_positive():
    split = TemporalSplit(
        date(1990, 1, 1), date(2000, 1, 1),
        date(2000, 1, 1), date(2010, 1, 1),
        date(2010, 1, 1), date(2020, 1, 1),
    )
    preds = [Prediction("p1", EventCategory.CAREER, date(2012, 1, 1), 0.8, True)]
    events = [_event(EventCategory.CAREER, date(2018, 7, 1))]

    scored = _score(preds, events, split)
    assert scored[EventCategory.CAREER].fp == 1
    assert scored[EventCategory.CAREER].fn == 1


def test_unmatched_event_is_a_false_negative():
    split = TemporalSplit(
        date(1990, 1, 1), date(2000, 1, 1),
        date(2000, 1, 1), date(2010, 1, 1),
        date(2010, 1, 1), date(2020, 1, 1),
    )
    events = [_event(EventCategory.FINANCE, date(2015, 3, 1))]
    scored = _score([], events, split)
    assert scored[EventCategory.FINANCE].fn == 1


def _score(preds, events, split):
    from engine.backtest import score_against

    return score_against(preds, events, split)


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------


def test_perfect_calibration_scores_near_zero():
    split = TemporalSplit(
        date(1990, 1, 1), date(2000, 1, 1),
        date(2000, 1, 1), date(2010, 1, 1),
        date(2010, 1, 1), date(2020, 1, 1),
    )
    preds = [
        Prediction("p1", EventCategory.CAREER, date(2012, 1, 1), 1.0, True),
        Prediction("p1", EventCategory.CAREER, date(2013, 1, 1), 1.0, True),
    ]
    events = [
        _event(EventCategory.CAREER, date(2012, 1, 5)),
        _event(EventCategory.CAREER, date(2013, 1, 5)),
    ]
    assert calibration_error(preds, events, split) < 0.01


def test_overconfident_predictions_score_badly():
    split = TemporalSplit(
        date(1990, 1, 1), date(2000, 1, 1),
        date(2000, 1, 1), date(2010, 1, 1),
        date(2010, 1, 1), date(2020, 1, 1),
    )
    preds = [
        Prediction("p1", EventCategory.CAREER, date(2012, 1, 1), 1.0, True),
        Prediction("p1", EventCategory.CAREER, date(2013, 1, 1), 1.0, True),
    ]
    events = [_event(EventCategory.CAREER, date(2012, 1, 5))]
    # Claims 1.0 confidence but only half are right
    assert calibration_error(preds, events, split) > 0.4


# ---------------------------------------------------------------------------
# The self-test: can the harness tell signal from noise?
# ---------------------------------------------------------------------------


def test_harness_recovers_planted_signal():
    result = selftest_signal_recovery()
    assert result["signal_detected_when_present"] is True
    assert result["signal_lift"] > 2.0


def test_harness_does_not_invent_signal_from_noise():
    result = selftest_signal_recovery()
    assert result["false_signal_on_noise"] is False, (
        "the harness reported signal on independent data, which means the "
        "statistics are miscalibrated"
    )


def test_harness_selftest_overall_verdict():
    assert selftest_signal_recovery()["harness_is_sound"] is True


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def test_backtest_reports_data_problem_when_nothing_is_eligible():
    report = run_backtest([], version="empty")
    assert report.n_profiles == 0
    assert "data" in report.finding.lower()
    assert "not a negative result" in report.finding


def test_backtest_excludes_profiles_with_too_few_events():
    from engine.backtest import BacktestProfile

    chart = _dummy_chart()
    events = [
        _event(EventCategory.CAREER, date(2010, 1, 1))
    ]
    profiles = [BacktestProfile("p1", chart, events, date(1960, 1, 1))]
    report = run_backtest(profiles, version="t")
    assert report.n_profiles == 0
    assert "fewer than 5 dated events" in report.exclusion_reasons


def test_backtest_output_is_json_serialisable():
    import json

    report = run_backtest([], version="t")
    payload = json.dumps(report.to_json(), sort_keys=True)
    assert "finding" in payload
    assert "macro_f1" in payload


def test_backtest_markdown_includes_baseline_comparison():
    report = run_backtest([], version="t")
    md = report.to_markdown()
    assert "Baseline macro F1" in md
    assert "Calibration error" in md


def _dummy_chart():
    from datetime import datetime

    from engine.vedic_layer import build_vedic_chart

    return build_vedic_chart(
        birth_datetime=datetime(1960, 3, 15, 6, 0, 0),
        birth_timezone="Asia/Kolkata",
        latitude=28.6139,
        longitude=77.2090,
    )
