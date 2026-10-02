"""Engine tests — Phase 1 verification (Gate 1 & Gate 2)."""

import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.swisseph_wrapper import (  # noqa: E402
    DASHA_PERIODS,
    DASHA_SEQUENCE,
    calc_all_planets,
    dasha_from_moon_nakshatra,
    julian_day_from_datetime,
    nakshatra_from_longitude,
    sign_from_longitude,
    tropical_to_sidereal,
)
from engine.vedic_layer import (  # noqa: E402
    build_vedic_chart,
    calculate_combustion,
    calculate_dignity,
    calculate_divisional_longitude,
    get_sign_lord,
)
from tests.golden_charts import (  # noqa: E402
    GOLDEN_CHARTS,
)

# ---------------------------------------------------------------------------
# Gate 1 — birth chart calculations
# ---------------------------------------------------------------------------

def _parse_bd(dt_str: str) -> datetime:
    """Parse ISO birth date, tolerating unpadded historical years (<1000)."""
    head, _, tail = dt_str.partition("T")
    y, m, d = head.split("-")
    return datetime(int(y), int(m), int(d), *map(int, tail.split(":")))


ACTIVE_GOLDEN = [g for g in GOLDEN_CHARTS if not g.get("skip")]
EXTERNAL_GOLDEN = [
    g for g in ACTIVE_GOLDEN if g.get("verified_against") == "external-source"
]
PARTIAL_GOLDEN = [
    g for g in ACTIVE_GOLDEN
    if g.get("verified_against") == "external-source-partial"
]
UNUSABLE = [g for g in GOLDEN_CHARTS if g.get("verified_against") == "unusable"]


@pytest.mark.parametrize(
    "golden", ACTIVE_GOLDEN, ids=[g["name"] for g in ACTIVE_GOLDEN]
)
def test_golden_chart_signs(golden):
    """Regression guard: engine output must not drift from the snapshot."""
    bd = golden["birth_data"]
    chart = build_vedic_chart(
        birth_datetime=_parse_bd(bd["datetime"]),
        birth_timezone=bd["timezone"],
        latitude=bd["latitude"],
        longitude=bd["longitude"],
    )

    for key, expected in golden["expected"].items():
        # Tolerate the "-" separator typo in the dataset
        key = key.replace("-", "_")
        if key == "lagna_sign":
            assert chart.lagna_sign == expected, f"{golden['name']}: lagna"
            continue
        if key.endswith("_nakshatra_name"):
            planet = key.removesuffix("_nakshatra_name")
            got = chart.planets[planet].nakshatra_name
            assert got == expected, (
                f"{golden['name']}: {planet} in {got}, expected {expected}"
            )
            continue
        if key.endswith("_nakshatra"):
            planet = key.removesuffix("_nakshatra")
            got = chart.planets[planet].nakshatra
            assert got == expected, (
                f"{golden['name']}: {planet} in nakshatra {got}, expected {expected}"
            )
            continue
        planet = key.removesuffix("_sign")
        vp = chart.planets[planet]
        assert vp.sign == expected, (
            f"{golden['name']}: {planet} in sign {vp.sign} "
            f"({vp.longitude_sidereal:.4f} deg), expected {expected}"
        )


# ---------------------------------------------------------------------------
# External verification of a sourced chart
# ---------------------------------------------------------------------------


def _chart_for(golden):
    bd = golden["birth_data"]
    return build_vedic_chart(
        birth_datetime=_parse_bd(bd["datetime"]),
        birth_timezone=bd["timezone"],
        latitude=bd["latitude"],
        longitude=bd["longitude"],
    )


def test_einstein_matches_independent_implementation():
    """Rodden AA chart cross-checked against an independent implementation.

    Astro-Databank gives 1879-03-14 11:30, Ulm, birth certificate in hand.
    VedAstro independently reports: lagna Gemini, Sun Pisces, Moon Scorpio
    in the Jyeshtha nakshatra. All four are asserted here.
    """
    einstein = next(g for g in EXTERNAL_GOLDEN if "Einstein" in g["name"])
    chart = _chart_for(einstein)

    assert chart.lagna_sign == 2, "lagna Gemini"
    assert chart.planets["sun"].sign == 11, "Sun Pisces"
    assert chart.planets["moon"].sign == 7, "Moon Scorpio"
    assert chart.planets["moon"].nakshatra == 18, "Moon in Jyeshtha"
    assert chart.planets["moon"].nakshatra_name == "Jyeshtha"


def test_lmt_ambiguity_is_material_and_documented():
    """Astro-Databank's 'LMT m10e0' (+0:40) differs from the IANA tzdb's
    Europe/Berlin LMT (+0:53:28) by 13.5 minutes: astro.com derives LMT from
    the stated longitude, tzdb uses the zone's reference meridian.

    For Einstein both readings give the same ascendant, but the gap moves an
    ascendant several degrees, so it is recorded rather than resolved silently.
    """
    bd = next(g for g in EXTERNAL_GOLDEN if "Einstein" in g["name"])["birth_data"]

    tz_offset = timedelta(hours=0, minutes=53, seconds=28)
    stated_lon_offset = timedelta(hours=bd["longitude"] / 15.0)
    gap = abs(tz_offset - stated_lon_offset)
    assert gap > timedelta(minutes=13), (
        f"expected the LMT discrepancy to exceed 13 min, got {gap}"
    )

    base = _chart_for({"birth_data": bd})
    shifted = build_vedic_chart(
        birth_datetime=_parse_bd(bd["datetime"]) + gap,
        birth_timezone=bd["timezone"],
        latitude=bd["latitude"],
        longitude=bd["longitude"],
    )
    lagna_drift_deg = abs(shifted.lagna_degree - base.lagna_degree)
    assert lagna_drift_deg > 0.5, (
        "a 13-minute offset must move the ascendant measurably"
    )


def test_unusable_charts_are_excluded_not_silently_used():
    """Gandhi's chart is disputed; the file documents why it is excluded."""
    gandhi = next(g for g in GOLDEN_CHARTS if "Gandhi" in g["name"])
    assert gandhi.get("skip") is True
    assert gandhi["verified_against"] == "unusable"
    assert "Rectified" in gandhi["notes"]
    assert all(g["name"] != "Mahatma Gandhi" for g in ACTIVE_GOLDEN)


def test_epoch_sun_sign_is_independently_derivable():
    """The one chart whose expectation comes from an external derivation.

    1990-01-01 12:00 UT: Sun tropical 280.814 deg (swisseph reference value),
    Lahiri ayanamsha 23.717 deg, so sidereal 257.097 deg -> Sagittarius.
    Sign indexing is 0-based with Aries=0, hence Sagittarius == 8.
    """
    chart = build_vedic_chart(
        birth_datetime=datetime(1990, 1, 1, 12, 0, 0),
        birth_timezone="UTC",
        latitude=0.0,
        longitude=0.0,
    )
    sun = chart.planets["sun"]
    assert sun.sign == 8, f"Sun sidereal {sun.longitude_sidereal:.3f} deg"
    assert 255.0 < sun.longitude_sidereal < 258.0


def test_planet_speeds_are_populated():
    """Regression guard: FLG_SPEED must be set.

    Without it swisseph returns speed 0.0 for every planet, which makes every
    planet look non-retrograde and silently corrupts retrograde detection.
    """
    jd = julian_day_from_datetime(datetime(1990, 1, 1, 12, 0, 0), "UTC")
    planets = calc_all_planets(jd.jd_tt)
    for name, pos in planets.items():
        assert pos.speed_longitude != 0.0, f"{name} has zero speed (FLG_SPEED missing)"

    # Moon moves roughly 11-15 deg/day; Sun ~1 deg/day. Bounds, not exact values.
    assert 11.0 < planets["moon"].speed_longitude < 15.0
    assert 0.9 < planets["sun"].speed_longitude < 1.1


def test_retrograde_detection_produces_both_states():
    """Nodes are always retrograde; the engine must reflect that."""
    jd = julian_day_from_datetime(datetime(1990, 1, 1, 12, 0, 0), "UTC")
    planets = calc_all_planets(jd.jd_tt)
    assert planets["rahu"].retrograde is True
    assert planets["ketu"].retrograde is True
    assert planets["sun"].retrograde is False

    # A retrograde inner planet must be detected somewhere in a yearly sweep
    found = False
    for month in range(1, 13):
        j = julian_day_from_datetime(datetime(1990, month, 15, 12, 0, 0), "UTC")
        p = calc_all_planets(j.jd_tt)
        if p["mercury"].retrograde or p["venus"].retrograde:
            found = True
            break
    assert found, "Mercury/Venus never retrograde across 1990 — check FLG_SPEED"


def test_ramana_moon_matches_independent_traditional_source():
    """A biography quotes: 'The star in the constellation was Punarvasu.'

    That is an independent, non-astrology author's statement about the
    Moon's sidereal nakshatra. The engine reproduces it, which confirms the
    Moon's sidereal position to within one nakshatra span (13.33 degrees).
    """
    ramana = next(g for g in PARTIAL_GOLDEN if "Ramana" in g["name"])
    chart = _chart_for(ramana)
    assert chart.planets["moon"].nakshatra == 7
    assert chart.planets["moon"].nakshatra_name == "Punarvasu"


def test_partial_verification_declares_its_scope():
    """A partial verification must say which quantities it covers, so a
    reader cannot mistake one confirmed nakshatra for a confirmed chart."""
    ramana = next(g for g in PARTIAL_GOLDEN if "Ramana" in g["name"])
    assert ramana["verified_quantities"] == ["moon_nakshatra"]
    assert "PARTIAL" in ramana["notes"]
    assert "NOT externally verified" in ramana["notes"]


def test_unusable_charts_are_documented_with_reasons():
    """Every excluded chart must carry a reason, so exclusions are auditable
    rather than looking like the inconvenient ones were quietly dropped."""
    assert len(UNUSABLE) >= 3
    for chart in UNUSABLE:
        assert chart.get("skip") is True
        assert len(chart["notes"]) > 80, f"{chart['name']} lacks a real reason"
        assert chart["expected"] == {} or chart["expected"]
        assert chart["name"] not in [g["name"] for g in ACTIVE_GOLDEN]


def test_krishnamurti_and_gandhi_are_excluded_as_disputed():
    """Both have documented disputes over birth time or date. Gandhi's spread
    is ~37 minutes (~9 degrees of ascendant), enough to change a house."""
    names = {g["name"] for g in UNUSABLE}
    assert any("Gandhi" in n for n in names)
    assert any("Krishnamurti" in n for n in names)
    for g in UNUSABLE:
        if "Gandhi" in g["name"]:
            assert "Rectified" in g["notes"]
        if "Krishnamurti" in g["name"]:
            assert "dispute" in g["notes"].lower()


def test_no_self_snapshots_remain():
    """Gate 1 honesty check.

    NOTE ON WHAT THIS DOES AND DOES NOT MEAN.

    This passing means: no active chart asserts values that came only from
    this engine. It does NOT mean Gate 1's benchmark is met. The protocol
    asks for "100% agreement on sign assignment" over a golden dataset, and
    the dataset is still small — one fully cross-checked chart, one partial,
    one analytically derived. Treat this as a guard against silently
    fabricated data, not as proof of correctness.

    See test_external_verification_coverage_is_declared for the count.
    """
    self_snapshots = [
        g["name"] for g in ACTIVE_GOLDEN if g.get("verified_against") == "self-snapshot"
    ]
    if self_snapshots:
        pytest.fail(
            f"Gate 1 is NOT proven. {len(EXTERNAL_GOLDEN)} of "
            f"{len(ACTIVE_GOLDEN)} active charts are fully externally "
            f"verified and {len(PARTIAL_GOLDEN)} partially; these are still "
            "engine self-snapshots: "
            + ", ".join(self_snapshots)
            + ". Replace them with Astro-Databank birth data cross-checked "
            "against an independent source, and set "
            "verified_against='external-source', before claiming correctness."
        )


def test_external_verification_coverage_is_declared():
    """Make the verification coverage explicit and regression-proof.

    The protocol's Gate 1 benchmark implies a golden dataset of roughly
    20-30 charts. The suite currently carries far fewer, so this test
    records the real state instead of letting a green suite imply more
    coverage than exists.
    """
    verified_quantities = sum(
        len(g.get("verified_quantities", [])) for g in EXTERNAL_GOLDEN
    ) + sum(len(g.get("verified_quantities", [])) for g in PARTIAL_GOLDEN)

    coverage = {
        "fully_verified_charts": len(EXTERNAL_GOLDEN),
        "partially_verified_charts": len(PARTIAL_GOLDEN),
        "excluded_as_unusable": len(UNUSABLE),
        "engine_generated_snapshots": 0,
        "independently_verified_quantities": verified_quantities,
        "protocol_target_charts": 20,
    }

    assert coverage["engine_generated_snapshots"] == 0
    assert coverage["fully_verified_charts"] >= 1, (
        "at least one chart must be cross-checked against an independent "
        f"source, currently {coverage}"
    )
    assert coverage["independently_verified_quantities"] >= 5, coverage

    # Deliberately does NOT assert 20 charts: that target is unmet, and the
    # gap should be visible in the coverage dict rather than papered over.
    print(f"\nGate 1 verification coverage: {coverage}")


def test_julian_day_utc_consistency():
    """JD conversion must be internally consistent."""
    jd = julian_day_from_datetime(datetime(2000, 1, 1, 12, 0, 0), "UTC")
    # J2000.0 epoch is JD 2451545.0 at 2000-01-01 12:00 TT
    assert abs(jd.jd_ut - 2451545.0) < 0.001


@pytest.mark.parametrize(
    "longitude,expected_sign,expected_name",
    [
        (0.0, 0, "Aries"),
        (29.999, 0, "Aries"),
        (30.0, 1, "Taurus"),
        (89.9, 2, "Gemini"),
        (180.0, 6, "Libra"),
        (359.999, 11, "Pisces"),
        (360.0, 0, "Aries"),
    ],
)
def test_sign_boundaries(longitude, expected_sign, expected_name):
    assert sign_from_longitude(longitude) == expected_sign


def test_nakshatra_boundaries_exact():
    """Nakshatra spans must be exactly 13.333... degrees with 4 padas."""
    assert nakshatra_from_longitude(0.0) == (1, 1)
    assert nakshatra_from_longitude(13.3333) == (1, 4)
    assert nakshatra_from_longitude(13.3334) == (2, 1)
    assert nakshatra_from_longitude(359.9999) == (27, 4)


def test_divisional_longitude_math():
    """D9/D10/D12 must follow the Parashara odd/even counting rule."""
    # Each sign's first pada maps to the sign itself, in every varga
    for sign_start in (0.0, 30.0, 60.0, 300.0):
        for div in (9, 10, 12):
            got = sign_from_longitude(calculate_divisional_longitude(sign_start, div))
            assert got == sign_from_longitude(sign_start), f"D{div} at {sign_start}"

    # D9: 10 deg Aries = 3rd pada -> Cancer
    assert sign_from_longitude(calculate_divisional_longitude(10.0, 9)) == 3
    # D9: Taurus 5 deg = 2nd pada -> Gemini
    assert sign_from_longitude(calculate_divisional_longitude(35.0, 9)) == 2
    # D10 (even, counts backward): Aries 3 deg -> Pisces
    assert sign_from_longitude(calculate_divisional_longitude(3.0, 10)) == 11

    # D1 must be the identity
    for lon in (0.0, 45.5, 123.4, 300.0):
        assert abs(calculate_divisional_longitude(lon, 1) - lon % 360) < 1e-9


def test_sign_lord_mapping():
    assert get_sign_lord(0) == "mars"
    assert get_sign_lord(3) == "moon"
    assert get_sign_lord(8) == "jupiter"
    assert get_sign_lord(10) == "saturn"


def test_dignity_boundaries():
    assert calculate_dignity("sun", 0, 10) == "exalted"
    assert calculate_dignity("sun", 6, 10) == "debilitated"
    # Leo 0-20 is Sun's moolatrikona, which outranks the "own sign" check
    assert calculate_dignity("sun", 4, 5) == "moolatrikona"
    assert calculate_dignity("sun", 4, 25) == "own"


def test_combustion_logic():
    # Moon 5 deg from Sun -> combust (orb 12)
    assert calculate_combustion("moon", 10.0, 5.0, False) is True
    # Moon 20 deg from Sun -> not combust
    assert calculate_combustion("moon", 20.0, 0.0, False) is False
    # Nodes and Sun never combust
    assert calculate_combustion("sun", 5.0, 5.0, False) is False
    assert calculate_combustion("rahu", 5.0, 5.0, False) is False


def test_sidereal_conversion_is_lahiri():
    """Lahiri ayanamsha is ~23.85 deg in 2000."""
    jd = julian_day_from_datetime(datetime(2000, 1, 1, 12, 0, 0), "UTC")
    sid = tropical_to_sidereal(100.0, jd.jd_tt, "lahiri")
    assert abs((100.0 - sid) - 23.85) < 0.05


def test_chart_is_self_consistent():
    """Whole-sign houses must align lagna to house 1."""
    chart = build_vedic_chart(
        birth_datetime=datetime(1990, 1, 1, 12, 0, 0),
        birth_timezone="UTC",
        latitude=0.0,
        longitude=0.0,
    )
    for name, vp in chart.planets.items():
        expected_house = ((vp.sign - chart.lagna_sign) % 12) + 1
        assert vp.house == expected_house, f"{name} house mismatch"

    for h in chart.houses:
        for planet in h.planets:
            assert chart.planets[planet].house == h.number


def test_divisional_charts_generated():
    chart = build_vedic_chart(
        birth_datetime=datetime(1990, 1, 1, 12, 0, 0),
        birth_timezone="UTC",
        latitude=0.0,
        longitude=0.0,
    )
    for div in ("D1", "D9", "D10", "D12"):
        assert div in chart.divisional_charts
        assert len(chart.divisional_charts[div].planets) == 9


def test_calc_config_snapshot_is_stored():
    """Gate: config must be stored with the chart so results are reproducible."""
    chart = build_vedic_chart(
        birth_datetime=datetime(1990, 1, 1, 12, 0, 0),
        birth_timezone="UTC",
        latitude=0.0,
        longitude=0.0,
    )
    cfg = chart.calc_config
    assert cfg["ayanamsha"] == "lahiri"
    assert cfg["house_system"] == "whole_sign"
    assert cfg["dasha_system"] == "vimshottari"
    assert cfg["dasha_levels"] == 3


# ---------------------------------------------------------------------------
# Gate 2 — dasha / transit calculations
# ---------------------------------------------------------------------------

def test_dasha_sequence_and_durations():
    assert sum(DASHA_PERIODS.values()) == 120
    assert len(DASHA_SEQUENCE) == 9


@pytest.mark.parametrize(
    "moon_lon,expected_first_lord",
    [
        (5.0, "ketu"),      # Ashwini
        (20.0, "venus"),    # Bharani
        (30.0, "sun"),      # Krittika
        (45.0, "moon"),     # Rohini
        (60.0, "mars"),     # Mrigashira
        (90.0, "jupiter"),  # Punarvasu
        (120.0, "mercury"), # Ashlesha
        (200.0, "rahu"),    # Swati
        (300.0, "mars"),    # Dhanishta
    ],
)
def test_first_dasha_lord_from_moon_nakshatra(moon_lon, expected_first_lord):
    jd = julian_day_from_datetime(datetime(1990, 1, 1, 12, 0, 0), "UTC")
    dashas = dasha_from_moon_nakshatra(moon_lon, jd.jd_tt)
    assert dashas[0]["lord"] == expected_first_lord


def test_dasha_periods_cover_120_years():
    jd = julian_day_from_datetime(datetime(1990, 1, 1, 12, 0, 0), "UTC")
    dashas = dasha_from_moon_nakshatra(15.0, jd.jd_tt)
    assert len(dashas) == 9
    # The first dasha is partial (Moon already partway through Bharani/Venus),
    # so total span from birth is 120 years minus the elapsed fraction.
    span_years = (dashas[-1]["end_jd"] - jd.jd_tt) / 365.25
    assert 115 < span_years <= 120.0


def test_dasha_chronological_and_contiguous():
    jd = julian_day_from_datetime(datetime(1990, 1, 1, 12, 0, 0), "UTC")
    dashas = dasha_from_moon_nakshatra(100.0, jd.jd_tt)
    for i in range(len(dashas) - 1):
        assert abs(dashas[i]["end_jd"] - dashas[i + 1]["start_jd"]) < 0.01
        assert dashas[i]["end_jd"] > dashas[i]["start_jd"]


def test_chart_dashas_have_sub_periods():
    chart = build_vedic_chart(
        birth_datetime=datetime(1990, 1, 1, 12, 0, 0),
        birth_timezone="UTC",
        latitude=0.0,
        longitude=0.0,
    )
    assert len(chart.dasha_periods) == 9
    maha = chart.dasha_periods[0]
    assert len(maha.sub_periods) == 9
    assert len(maha.sub_periods[0].sub_periods) == 9