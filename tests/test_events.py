"""Phase 2 tests — event model, date precision, and Gate 3 reproducibility."""

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.events import (  # noqa: E402
    SUB_CATEGORIES,
    DateInterval,
    DatePrecision,
    EventCategory,
    LifeEvent,
    Profile,
    precision_distribution,
    resolve_date_interval,
)
from storage.event_store import EventStore, build_event  # noqa: E402

# ---------------------------------------------------------------------------
# Date precision: the core honesty guarantee
# ---------------------------------------------------------------------------


def test_exact_precision_is_a_point():
    iv = resolve_date_interval("2018-06-12", DatePrecision.EXACT)
    assert iv.is_point
    assert iv.start == date(2018, 6, 12)
    assert iv.span_days == 0


def test_month_precision_covers_the_whole_month():
    iv = resolve_date_interval("2018-02", DatePrecision.MONTH)
    assert iv.start == date(2018, 2, 1)
    assert iv.end == date(2018, 2, 28)  # 2018 is not a leap year


def test_month_precision_handles_leap_year():
    iv = resolve_date_interval("2016-02", DatePrecision.MONTH)
    assert iv.end == date(2016, 2, 29)


def test_quarter_precision_covers_three_months():
    for q, (ms, me) in enumerate([(1, 3), (4, 6), (7, 9), (10, 12)], start=1):
        iv = resolve_date_interval(f"2019-Q{q}", DatePrecision.QUARTER)
        assert iv.start == date(2019, ms, 1)
        assert iv.end.month == me
        assert iv.span_days >= 89


def test_year_precision_covers_365_or_366_days():
    assert resolve_date_interval("2018", DatePrecision.YEAR).span_days == 364
    assert resolve_date_interval("2020", DatePrecision.YEAR).span_days == 365


def test_unknown_precision_cannot_be_resolved():
    with pytest.raises(ValueError, match="no resolvable interval"):
        resolve_date_interval("2018", DatePrecision.UNKNOWN)


def test_imprecise_dates_expand_to_multiple_candidate_dates():
    """A year-precision event must not collapse to a single day."""
    iv = resolve_date_interval("2018", DatePrecision.YEAR)
    samples = iv.sample_dates(step_days=30)
    assert len(samples) > 12
    assert samples[0] == date(2018, 1, 1)
    assert samples[-1] == date(2018, 12, 31)


def test_sampling_always_includes_both_endpoints():
    iv = resolve_date_interval("2018-03", DatePrecision.MONTH)
    samples = iv.sample_dates(step_days=7)
    assert samples[0] == iv.start
    assert samples[-1] == iv.end


def test_interval_rejects_reversed_bounds():
    with pytest.raises(ValueError, match="precedes"):
        DateInterval(start=date(2020, 1, 1), end=date(2019, 1, 1),
                     precision=DatePrecision.EXACT)


# ---------------------------------------------------------------------------
# Event validation
# ---------------------------------------------------------------------------


def test_valid_event_is_accepted():
    e = build_event("p1", EventCategory.CAREER, "promotion", "2018-06-12",
                    DatePrecision.EXACT)
    assert e.is_point_event
    assert e.usable_for_timing_analysis


def test_invalid_sub_category_is_rejected():
    with pytest.raises(ValueError, match="not valid for"):
        LifeEvent(
            profile_id="p1",
            category=EventCategory.CAREER,
            sub_category="marriage",  # belongs to relationship
            date_interval=resolve_date_interval("2018", DatePrecision.YEAR),
        )


def test_impact_and_certainty_bounds_are_enforced():
    for bad in (0, 6, -1):
        with pytest.raises(ValueError, match="impact must be 1-5"):
            build_event("p1", EventCategory.CAREER, "promotion", "2018",
                        DatePrecision.YEAR, impact=bad)


def test_unknown_date_events_are_excluded_from_timing_analysis():
    e = LifeEvent(
        profile_id="p1",
        category=EventCategory.CAREER,
        sub_category="promotion",
        date_interval=DateInterval(
            start=date(1900, 1, 1), end=date(2100, 1, 1),
            precision=DatePrecision.UNKNOWN,
        ),
    )
    assert not e.usable_for_timing_analysis


def test_precision_distribution_reports_dataset_quality():
    events = [
        build_event("p1", EventCategory.CAREER, "promotion", "2018-06-12",
                    DatePrecision.EXACT),
        build_event("p1", EventCategory.CAREER, "job_loss", "2019",
                    DatePrecision.YEAR),
        build_event("p1", EventCategory.FINANCE, "major_gain", "2020-Q2",
                    DatePrecision.QUARTER),
    ]
    dist = precision_distribution(events)
    assert dist["exact"] == 1
    assert dist["year"] == 1
    assert dist["quarter"] == 1
    assert dist["unknown"] == 0


def test_every_category_has_a_taxonomy():
    for cat in EventCategory:
        assert SUB_CATEGORIES[cat], f"{cat.value} has no sub-categories"


# ---------------------------------------------------------------------------
# Gate 3 — storage and reproducibility
# ---------------------------------------------------------------------------


@pytest.fixture
def store():
    with EventStore(":memory:") as s:
        yield s


@pytest.fixture
def profile():
    return Profile(
        profile_id="p-einstein",
        birth_date=date(1879, 3, 14),
        birth_time="11:30:00",
        timezone="Europe/Berlin",
        latitude=48.3988,
        longitude=9.9916,
        city="Ulm",
        country="Germany",
    )


def test_profile_roundtrip(store, profile):
    pid = store.add_profile(profile)
    assert pid == "p-einstein"
    loaded = store.get_profile(pid)
    assert loaded.birth_date == date(1879, 3, 14)
    assert loaded.calc_config["ayanamsha"] == "lahiri"
    assert loaded.calc_config["house_system"] == "whole_sign"


def test_event_roundtrip_preserves_precision_interval(store, profile):
    store.add_profile(profile)
    eid = store.add_event(
        build_event("p-einstein", EventCategory.CAREER, "job_change", "2018",
                    DatePrecision.YEAR, impact=4, certainty=5)
    )
    loaded = store.get_event(eid)
    assert loaded.date_interval.precision is DatePrecision.YEAR
    assert loaded.date_interval.start == date(2018, 1, 1)
    assert loaded.date_interval.end == date(2018, 12, 31)
    assert loaded.impact == 4
    assert loaded.certainty == 5


def test_cascade_delete(store, profile):
    store.add_profile(profile)
    eid = store.add_event(
        build_event("p-einstein", EventCategory.CAREER, "promotion", "2018-06-12",
                    DatePrecision.EXACT)
    )
    store.conn.execute("DELETE FROM profiles WHERE profile_id = ?", ("p-einstein",))
    store.conn.commit()
    assert store.get_event(eid) is None


def test_chart_fingerprint_is_stable_and_sensitive(store, profile):
    fp1 = profile.chart_fingerprint()
    fp2 = profile.chart_fingerprint()
    assert fp1 == fp2

    changed = Profile(
        profile_id="p-einstein",
        birth_date=profile.birth_date,
        birth_time=profile.birth_time,
        timezone=profile.timezone,
        latitude=profile.latitude,
        longitude=profile.longitude,
        calc_config={**profile.calc_config, "ayanamsha": "raman"},
    )
    assert changed.chart_fingerprint() != fp1


def test_features_are_stamped_with_chart_fingerprint(store, profile):
    """Gate 3: derived features must record the config they came from."""
    store.add_profile(profile)
    eid = store.add_event(
        build_event("p-einstein", EventCategory.CAREER, "promotion", "2018-06-12",
                    DatePrecision.EXACT)
    )
    store.add_features(eid, "p-einstein", {"dasha_lord": "saturn"})
    feats = store.get_features(eid)
    assert feats == [{"dasha_lord": "saturn"}]

    stored_fp = store.conn.execute(
        "SELECT chart_fingerprint FROM event_features WHERE event_id = ?", (eid,)
    ).fetchone()["chart_fingerprint"]
    assert stored_fp == profile.chart_fingerprint()


def test_stale_features_are_detectable_after_config_change(store, profile):
    """Changing the ayanamsha must make old features detectable as stale."""
    store.add_profile(profile)
    eid = store.add_event(
        build_event("p-einstein", EventCategory.CAREER, "promotion", "2018-06-12",
                    DatePrecision.EXACT)
    )
    store.add_features(eid, "p-einstein", {"dasha_lord": "saturn"})
    assert store.find_stale_features() == []

    # Simulate re-deriving the profile under a different ayanamsha.
    store.conn.execute(
        "UPDATE profiles SET calc_config = ? WHERE profile_id = ?",
        ('{"ayanamsha": "raman", "house_system": "whole_sign"}', "p-einstein"),
    )
    store.conn.commit()

    stale = store.find_stale_features()
    assert len(stale) == 1
    assert stale[0][0] == eid


def test_dataset_summary_reports_m3_benchmark(store, profile):
    store.add_profile(profile)
    for year, sub in [(2000, "first_job"), (2002, "promotion"), (2004, "job_change"),
                      (2006, "promotion"), (2008, "job_loss"), (2010, "job_change"),
                      (2012, "promotion"), (2014, "job_change"), (2016, "retirement"),
                      (2018, "business_launch")]:
        store.add_event(
            build_event("p-einstein", EventCategory.CAREER, sub, str(year),
                        DatePrecision.YEAR)
        )

    summary = store.dataset_summary("p-einstein")
    assert summary["total_events"] == 10
    assert summary["usable_events"] == 10
    assert summary["meets_m3_benchmark"] is True
    assert summary["categories"]["career"] == 10


def test_dataset_summary_flags_insufficient_events(store, profile):
    store.add_profile(profile)
    store.add_event(
        build_event("p-einstein", EventCategory.CAREER, "promotion", "2018",
                    DatePrecision.YEAR)
    )
    assert store.dataset_summary("p-einstein")["meets_m3_benchmark"] is False


def test_usable_only_filter_excludes_unknown_dates(store, profile):
    store.add_profile(profile)
    store.add_event(
        build_event("p-einstein", EventCategory.CAREER, "promotion", "2018",
                    DatePrecision.YEAR)
    )
    store.add_event(
        LifeEvent(
            profile_id="p-einstein",
            category=EventCategory.OTHER,
            sub_category="other",
            date_interval=DateInterval(
                start=date(1900, 1, 1), end=date(2100, 1, 1),
                precision=DatePrecision.UNKNOWN,
            ),
        )
    )
    assert len(store.get_events("p-einstein")) == 2
    assert len(store.get_events("p-einstein", usable_only=True)) == 1


def test_events_sort_by_interval_start(store, profile):
    store.add_profile(profile)
    store.add_event(
        build_event("p-einstein", EventCategory.CAREER, "job_loss", "2010",
                    DatePrecision.YEAR)
    )
    store.add_event(
        build_event("p-einstein", EventCategory.CAREER, "first_job", "2005",
                    DatePrecision.YEAR)
    )
    starts = [e.date_interval.start.year for e in store.get_events("p-einstein")]
    assert starts == [2005, 2010]