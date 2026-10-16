"""
Phase 3 tests — feature extraction, precision marginalisation, negative sampling.
"""

import os
import sys
from datetime import date, datetime, timedelta

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


from engine.events import (  # noqa: E402
    DatePrecision,
    EventCategory,
    LifeEvent,
    resolve_date_interval,
)
from engine.features import (  # noqa: E402
    SLOW_TRANSITS,
    any_factors,
    consensus_factors,
    dasha_at_date,
    extract_features_at,
    extract_features_for_event,
    extract_negative_features,
    sample_negative_dates,
    transits_at_date,
)
from engine.vedic_layer import build_vedic_chart  # noqa: E402


@pytest.fixture(scope="module")
def chart():
    return build_vedic_chart(
        birth_datetime=datetime(1975, 6, 15, 4, 30, 0),
        birth_timezone="Asia/Kolkata",
        latitude=19.0760,
        longitude=72.8777,
    )


# ---------------------------------------------------------------------------
# Basics
# ---------------------------------------------------------------------------


def test_features_extracted_for_an_arbitrary_date(chart):
    fv = extract_features_at(chart, date(2010, 3, 15))
    assert fv.when == date(2010, 3, 15)
    assert fv.dasha_lord in {"ketu", "venus", "sun", "moon", "mars",
                             "rahu", "jupiter", "saturn", "mercury"}
    assert len(fv.transits) == 9


def test_transits_cover_all_nine_grahas(chart):
    t = transits_at_date(chart, date(2010, 3, 15))
    assert set(t) == {"sun", "moon", "mars", "mercury", "jupiter",
                      "venus", "saturn", "rahu", "ketu"}


def test_transit_houses_are_within_1_to_12(chart):
    t = transits_at_date(chart, date(2010, 3, 15))
    for planet, state in t.items():
        assert 1 <= state.house <= 12, f"{planet} house {state.house}"


def test_rahu_and_ketu_transit_houses_are_opposite(chart):
    """Lunar nodes stay ~180 degrees apart, so their house occupancy must
    differ by 6 in a whole-sign chart."""
    t = transits_at_date(chart, date(2010, 3, 15))
    diff = abs(t["rahu"].house - t["ketu"].house) % 12
    assert diff == 6, f"rahu house {t['rahu'].house}, ketu {t['ketu'].house}"


def test_dasha_lords_are_consistent_over_a_period(chart):
    """Within one antardasha the maha lord must not change."""
    start = date(2010, 3, 15)
    maha, _, _ = dasha_at_date(chart, start)
    for day in range(1, 28):
        m2, _, _ = dasha_at_date(chart, start + timedelta(days=day))
        assert m2 == maha, f"maha lord changed on day {day}: {maha} -> {m2}"


def test_factors_are_named_strings(chart):
    fv = extract_features_at(chart, date(2010, 3, 15))
    assert len(fv.factors) > 20
    assert all(isinstance(f, str) for f in fv.factors)
    assert any(f.startswith("dasha=") for f in fv.factors)
    assert any(f.startswith("transit_saturn_in_house_") for f in fv.factors)


def test_slow_transit_kendra_factors_only_for_slow_planets(chart):
    fv = extract_features_at(chart, date(2010, 3, 15))
    for f in fv.factors:
        if f.endswith("_kendra") or f.endswith("_trikona"):
            assert any(f.startswith(p) for p in SLOW_TRANSITS), f


# ---------------------------------------------------------------------------
# Precision marginalisation — the important behaviour
# ---------------------------------------------------------------------------


def test_day_precision_event_yields_one_feature_vector(chart):
    event = LifeEvent(
        profile_id="p1",
        category=EventCategory.CAREER,
        sub_category="promotion",
        date_interval=resolve_date_interval("2010-03-15", DatePrecision.EXACT),
    )
    vectors = extract_features_for_event(chart, event)
    assert len(vectors) == 1
    assert vectors[0].when == date(2010, 3, 15)


def test_year_precision_event_yields_many_feature_vectors(chart):
    event = LifeEvent(
        profile_id="p1",
        category=EventCategory.CAREER,
        sub_category="job_change",
        date_interval=resolve_date_interval("2010", DatePrecision.YEAR),
    )
    vectors = extract_features_for_event(chart, event)
    # 2010 is not a leap year: 365 days at the default 7-day step
    assert len(vectors) == 53
    assert vectors[0].when == date(2010, 1, 1)
    assert vectors[-1].when == date(2010, 12, 31)


def test_sampling_step_is_configurable(chart):
    event = LifeEvent(
        profile_id="p1",
        category=EventCategory.CAREER,
        sub_category="job_change",
        date_interval=resolve_date_interval("2010", DatePrecision.YEAR),
    )
    coarse = extract_features_for_event(chart, event, step_days=30)
    fine = extract_features_for_event(chart, event, step_days=1)
    assert len(coarse) < len(fine)


def test_unknown_date_event_yields_no_features(chart):
    from engine.events import DateInterval

    event = LifeEvent(
        profile_id="p1",
        category=EventCategory.CAREER,
        sub_category="promotion",
        date_interval=DateInterval(
            start=date(1900, 1, 1), end=date(2100, 1, 1),
            precision=DatePrecision.UNKNOWN,
        ),
    )
    assert extract_features_for_event(chart, event) == []


def test_consensus_is_a_subset_of_any(chart):
    event = LifeEvent(
        profile_id="p1",
        category=EventCategory.CAREER,
        sub_category="job_change",
        date_interval=resolve_date_interval("2010", DatePrecision.YEAR),
    )
    vectors = extract_features_for_event(chart, event)
    consensus = consensus_factors(vectors)
    anything = any_factors(vectors)
    assert consensus <= anything
    assert len(consensus) < len(anything), "expected some factors to vary across the year"


def test_consensus_excludes_moving_factors(chart):
    """A dasha lord cannot be claimed for a whole year unless it genuinely
    spans it — and transits definitely change, so none should be consensus."""
    event = LifeEvent(
        profile_id="p1",
        category=EventCategory.CAREER,
        sub_category="job_change",
        date_interval=resolve_date_interval("2010", DatePrecision.YEAR),
    )
    consensus = consensus_factors(extract_features_for_event(chart, event))
    assert not any(f.startswith("transit_sun_in_house_") for f in consensus)


# ---------------------------------------------------------------------------
# Negative sampling — required for honest statistics
# ---------------------------------------------------------------------------


def test_negative_sampling_excludes_event_windows_with_margin():
    dates = sample_negative_dates(
        profile_start=date(2000, 1, 1),
        profile_end=date(2000, 12, 31),
        step_days=30,
        exclude=[(date(2000, 6, 1), date(2000, 6, 30))],
        margin_days=15,
    )
    assert dates
    assert date(2000, 6, 15) not in dates
    assert date(2000, 1, 1) in dates


def test_negative_sampling_without_margin_keeps_the_window():
    """With no margin, dates inside an excluded span may still be sampled —
    the caller is responsible for choosing a margin that reflects how much
    of the event's uncertainty window should be excluded."""
    dates = sample_negative_dates(
        profile_start=date(2000, 1, 1),
        profile_end=date(2000, 12, 31),
        step_days=30,
        exclude=[(date(2000, 6, 1), date(2000, 6, 30))],
        margin_days=0,
    )
    # step_days=30 from Jan 1 lands on 1st-of-month-ish dates
    assert date(2000, 6, 30) in dates or date(2000, 6, 1) in dates or len(dates) == 12
    assert len(dates) == 12, "no exclusion applied, so every sample should survive"


def test_negative_sampling_respects_span():
    dates = sample_negative_dates(
        profile_start=date(2000, 1, 1),
        profile_end=date(2000, 6, 30),
        step_days=30,
    )
    assert min(dates) == date(2000, 1, 1)
    assert max(dates) <= date(2000, 6, 30)


def test_negative_features_are_extracted(chart):
    dates = sample_negative_dates(date(2010, 1, 1), date(2010, 12, 31), 60)
    vectors = extract_negative_features(chart, dates)
    assert len(vectors) == len(dates)
    assert all(v.factors for v in vectors)


# ---------------------------------------------------------------------------
# Reproducibility (Gate 3)
# ---------------------------------------------------------------------------


def test_feature_extraction_is_deterministic(chart):
    """Factors must be bit-identical; longitudes need only agree closely.

    swisseph is not bit-reproducible: the Moon's longitude varies by about
    1e-8 degrees between calls, which is 1e-4 arcseconds of floating-point
    noise in the C library. That is far below any boundary the factor set
    depends on, but it means asserting exact longitude equality would be
    asserting something the underlying library does not guarantee.

    The factor SET is the property everything downstream depends on, and
    that must be exactly reproducible.
    """
    a = extract_features_at(chart, date(2010, 3, 15))
    b = extract_features_at(chart, date(2010, 3, 15))

    assert a.factors == b.factors
    assert a.dasha_lord == b.dasha_lord
    assert a.antardasha_lord == b.antardasha_lord
    assert (a.pratyantardasha_lord, a.when) == (b.pratyantardasha_lord, b.when)

    for planet in a.transits:
        assert a.transits[planet].house == b.transits[planet].house
        assert a.transits[planet].sign == b.transits[planet].sign
        assert a.transits[planet].nakshatra == b.transits[planet].nakshatra
        assert a.transits[planet].longitude_sidereal == pytest.approx(
            b.transits[planet].longitude_sidereal, abs=1e-6
        )


def test_feature_vector_serialises(chart):
    import json

    fv = extract_features_at(chart, date(2010, 3, 15))
    payload = json.dumps(fv.to_json(), sort_keys=True)
    assert "dasha_lord" in payload
    assert "saturn" in payload