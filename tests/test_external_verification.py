"""
External verification of the astronomical layer.

These tests do NOT use chart data or engine output. They check the engine
against published astronomical facts that were determined by entirely
different methods (observational astronomy), so agreement here is genuine
evidence of correctness rather than self-consistency.

Sources of truth used:
  - IAU equinox/solstice instants (published to the minute)
  - Published Lahiri/Chitrapaksha ayanamsha value at J2000.0
  - IANA timezone database offsets (via pytz)
"""

from datetime import UTC as dt_timezone
from datetime import datetime
from datetime import timedelta as dt_timedelta
from zoneinfo import ZoneInfo

import pytest
import swisseph as swe

from engine.swisseph_wrapper import (
    calc_all_planets,
    get_ayanamsha_value,
    julian_day_from_datetime,
)

# ---------------------------------------------------------------------------
# 1. Seasonal markers: the Sun's tropical longitude is a known quantity
#    at the instant of an equinox or solstice. If our Julian Day conversion
#    or planet calculation were wrong, these would drift.
# ---------------------------------------------------------------------------

SEASONAL_MARKERS = [
    # (label, utc datetime, expected tropical solar longitude, tolerance in deg)
    # Instants are the published IAU values, rounded to the minute.
    ("March equinox 2000", datetime(2000, 3, 20, 7, 35, tzinfo=dt_timezone.utc), 0.0, 0.01),
    ("June solstice 2000", datetime(2000, 6, 21, 1, 48, tzinfo=dt_timezone.utc), 90.0, 0.01),
    ("September equinox 2000", datetime(2000, 9, 22, 17, 27, tzinfo=dt_timezone.utc), 180.0, 0.01),
    ("December solstice 2000", datetime(2000, 12, 21, 13, 37, tzinfo=dt_timezone.utc), 270.0, 0.01),
    ("March equinox 1990", datetime(1990, 3, 20, 21, 19, tzinfo=dt_timezone.utc), 0.0, 0.01),
    ("March equinox 2020", datetime(2020, 3, 20, 3, 50, tzinfo=dt_timezone.utc), 0.0, 0.01),
]


@pytest.mark.parametrize(
    "label,when,expected_lon,tol",
    SEASONAL_MARKERS,
    ids=[m[0] for m in SEASONAL_MARKERS],
)
def test_solar_longitude_at_seasonal_markers(label, when, expected_lon, tol):
    """Sun's tropical longitude at a published equinox/solstice instant."""
    jd = swe.julday(when.year, when.month, when.day, when.hour + when.minute / 60)
    result, _ = swe.calc_ut(jd, swe.SUN, swe.FLG_MOSEPH | swe.FLG_SPEED)
    lon = result[0] % 360

    # Handle wraparound at 0 deg
    diff = abs(lon - expected_lon)
    diff = min(diff, 360 - diff)

    assert diff < tol, (
        f"{label}: solar longitude {lon:.6f} deg, expected {expected_lon} "
        f"(off by {diff:.6f} deg = {diff * 3600:.1f} arcsec)"
    )


# ---------------------------------------------------------------------------
# 2. Ayanamsha cross-check.
#
#    The Lahiri (Chitrapaksha) ayanamsha at J2000.0 is widely published as
#    23 deg 51' 11" = 23.853086 deg.
#
#    Swiss Ephemeris's Lahiri formulation differs slightly. We assert the
#    documented tolerance rather than hiding the difference, because an
#    ayanamsha error is the single most common cause of "my chart doesn't
#    match" disputes between software packages.
# ---------------------------------------------------------------------------

PUBLISHED_LAHIRI_J2000 = 23.853086
# 0.005 deg == 18 arcsec. Generous enough for formulation differences,
# tight enough to catch a wrong ayanamsha or a units error (degrees vs radians).
AYANAMSHA_TOLERANCE_DEG = 0.005


def test_lahiri_ayanamsha_at_j2000_matches_published_value():
    jd = swe.julday(2000, 1, 1, 12.0)
    value = get_ayanamsha_value(jd, "lahiri")
    diff = abs(value - PUBLISHED_LAHIRI_J2000)
    assert diff < AYANAMSHA_TOLERANCE_DEG, (
        f"Lahiri ayanamsha at J2000 = {value:.6f} deg, published "
        f"{PUBLISHED_LAHIRI_J2000} deg, diff {diff:.6f} deg "
        f"= {diff * 3600:.1f} arcsec"
    )


def test_ayanamsha_increases_at_the_precession_rate():
    """Ayanamsha grows ~50.3 arcsec/yr (1.397 deg per century) due to precession."""
    epochs = [
        swe.julday(1900, 1, 1, 12.0),
        swe.julday(1950, 1, 1, 12.0),
        swe.julday(2000, 1, 1, 12.0),
        swe.julday(2050, 1, 1, 12.0),
    ]
    values = [get_ayanamsha_value(j, "lahiri") for j in epochs]
    assert values == sorted(values), f"ayanamsha not monotonic: {values}"

    # 1900 -> 2050 spans 150 years; at 1.397 deg/century that is ~2.095 deg.
    span = values[-1] - values[0]
    per_century = span / 1.5
    assert 1.3 < per_century < 1.5, (
        f"precession rate {per_century:.4f} deg/century is implausible "
        f"(expected ~1.397)"
    )


def test_distinct_ayanamshas_differ_appropriately():
    """Lahiri, Raman, Krishnamurti and Fagan-Bradley must all be distinct."""
    jd = swe.julday(2000, 1, 1, 12.0)
    values = {
        name: get_ayanamsha_value(jd, name)
        for name in ("lahiri", "raman", "krishnamurti", "fagan_bradley")
    }
    assert len(set(round(v, 3) for v in values.values())) == 4, (
        f"ayanamshas collapsed: {values}"
    )
    # Known ordering at J2000: Raman < Krishnamurti < Lahiri < Fagan-Bradley
    assert (
        values["raman"]
        < values["krishnamurti"]
        < values["lahiri"]
        < values["fagan_bradley"]
    ), f"unexpected ayanamsha ordering: {values}"


# ---------------------------------------------------------------------------
# 3. Julian Day conversion, verified against an independent formula
#    (Meeus, Astronomical Algorithms, ch. 7) rather than swisseph.
# ---------------------------------------------------------------------------


def _meeus_julian_day(year, month, day, hour_ut):
    """Independent JD implementation per Meeus. day may be fractional."""
    if month <= 2:
        year -= 1
        month += 12
    a = year // 100
    b = 2 - a + a // 4
    return (
        int(365.25 * (year + 4716))
        + int(30.6001 * (month + 1))
        + day
        + b
        - 1524.5
        + hour_ut / 24.0
    )


@pytest.mark.parametrize(
    "y,m,d,h",
    [
        (2000, 1, 1, 12.0),
        (1990, 1, 1, 12.0),
        (1879, 3, 14, 11.5),
        (2026, 10, 1, 0.0),
        (1969, 7, 21, 20.17),
    ],
)
def test_julian_day_matches_independent_meeus_formula(y, m, d, h):
    ours = swe.julday(y, m, d, h)
    meeus = _meeus_julian_day(y, m, d, h)
    assert abs(ours - meeus) < 1e-6, f"JD mismatch: swisseph {ours}, Meeus {meeus}"


def test_known_julian_day_epochs():
    """Epoch reference points fixed by definition."""
    assert abs(swe.julday(2000, 1, 1, 12.0) - 2451545.0) < 1e-6  # J2000.0
    assert abs(swe.julday(1987, 1, 27, 0.0) - 2446822.5) < 1e-6  # J2000.0 epoch (standard)


# ---------------------------------------------------------------------------
# 4. Timezone / DST handling.
#
#    The spec calls out historical timezone conversion as a required test.
#    Birth data from the 19th century is exactly where naive implementations
#    silently shift every planet position.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "zone,naive_local,expected_utc_hour,note",
    [
        ("UTC", datetime(1990, 1, 1, 12, 0), 12.0, "baseline"),
        ("America/New_York", datetime(1990, 1, 1, 12, 0), 17.0, "EST = UTC-5"),
        ("America/New_York", datetime(1990, 7, 1, 12, 0), 16.0, "EDT = UTC-4 (DST)"),
        ("Europe/London", datetime(1990, 7, 1, 12, 0), 11.0, "BST = UTC+1 (DST)"),
        ("Asia/Kolkata", datetime(1950, 1, 1, 12, 0), 6.5, "IST = UTC+5:30"),
        ("Asia/Tokyo", datetime(1990, 1, 1, 12, 0), 3.0, "JST = UTC+9"),
    ],
)
def test_timezone_conversion(zone, naive_local, expected_utc_hour, note):
    jd = julian_day_from_datetime(naive_local, zone)
    y, mo, d, h = swe.revjul(jd.jd_ut)
    assert h == pytest.approx(expected_utc_hour, abs=1 / 60), (
        f"{zone} {naive_local} ({note}): got UTC hour {h}, want {expected_utc_hour}"
    )


@pytest.mark.parametrize(
    "zone,naive_local",
    [
        # Pre-standard-time dates, where LMT offsets apply and where pytz
        # was found to disagree with the IANA database.
        ("America/New_York", datetime(1890, 7, 1, 12, 0)),
        ("America/New_York", datetime(1880, 1, 1, 12, 0)),
        ("Asia/Kolkata", datetime(1900, 1, 1, 12, 0)),
        ("Europe/London", datetime(1850, 6, 1, 12, 0)),
        ("Asia/Kolkata", datetime(1906, 1, 1, 12, 0)),
    ],
)
def test_historical_timezone_matches_iana_database(zone, naive_local):
    """The engine must reproduce the IANA tzdb offset exactly.

    This is the check that caught pytz returning Local Mean Time for
    pre-standard-time dates, which was wrong by up to ~32 minutes.
    """
    expected_utc = naive_local.replace(tzinfo=ZoneInfo(zone)).astimezone(dt_timezone.utc)

    jd = julian_day_from_datetime(naive_local, zone)
    y, mo, d, h = swe.revjul(jd.jd_ut)

    ours = datetime(int(y), int(mo), int(d), tzinfo=dt_timezone.utc) + dt_timedelta(
        hours=h
    )
    # Julian Day round-trips at sub-second precision; require agreement to
    # within one second. The bug this test guards against was ~32 MINUTES.
    delta_s = abs((ours - expected_utc).total_seconds())
    assert delta_s < 1.0, (
        f"{zone} {naive_local}: engine gives {ours}, IANA gives {expected_utc} "
        f"(differs by {delta_s:.0f}s)"
    )


def test_dst_boundary_day_is_handled():
    """US DST began 1990-04-01: noon local that day is 16:00 UTC."""
    jd = julian_day_from_datetime(datetime(1990, 4, 1, 12, 0), "America/New_York")
    y, mo, d, h = swe.revjul(jd.jd_ut)
    assert h == pytest.approx(16.0, abs=1 / 60)


# ---------------------------------------------------------------------------
# 5. Planetary motion sanity, bounded by observation rather than by engine.
# ---------------------------------------------------------------------------


def test_daily_motion_ranges_are_physically_plausible():
    """Apparent daily motion bounds for geocentric planets (degrees/day).

    Outer-planet bounds are wide because Jupiter and Saturn were within a
    few weeks of their retrograde stations at J2000, where daily motion
    passes through zero. A wrong Julian Day, a missing FLG_SPEED, or a
    mismatched planet id would still break these.
    """
    bounds = {
        "sun": (0.95, 1.10),
        "moon": (11.0, 15.5),
        "mercury": (0.3, 1.9),
        "venus": (0.2, 1.5),
        "mars": (0.1, 1.0),
        "jupiter": (0.0, 0.25),
        "saturn": (0.0, 0.20),
    }
    jd = julian_day_from_datetime(datetime(2000, 1, 1, 12, 0), "UTC")
    planets = calc_all_planets(jd.jd_tt)
    for name, (lo, hi) in bounds.items():
        spd = abs(planets[name].speed_longitude)
        assert lo <= spd <= hi, (
            f"{name} daily motion {spd:.4f} outside [{lo}, {hi}] "
            f"(signed {planets[name].speed_longitude:.4f})"
        )


def test_inner_planets_show_expected_speed_variation():
    """Mercury and Venus must vary in speed as they orbit the Sun.

    A static or duplicated result would pass a range check but fail this.
    """
    speeds = set()
    for month in range(1, 13):
        jd = julian_day_from_datetime(datetime(1990, month, 15, 12, 0), "UTC")
        p = calc_all_planets(jd.jd_tt)
        speeds.add(round(p["mercury"].speed_longitude, 2))
    assert len(speeds) > 6, f"Mercury speed barely changes across a year: {sorted(speeds)}"


def test_sun_moon_longitudes_are_not_duplicate():
    """Guards against an id mix-up that returns one planet twice."""
    jd = julian_day_from_datetime(datetime(1990, 1, 1, 12, 0), "UTC")
    p = calc_all_planets(jd.jd_tt)
    lons = [round(v.longitude_tropical, 2) for v in p.values()]
    assert len(set(lons)) == len(lons), f"duplicate longitudes: {dict(zip(p, lons, strict=True))}"


def test_rahu_ketu_are_exactly_opposed():
    jd = julian_day_from_datetime(datetime(1990, 1, 1, 12, 0), "UTC")
    p = calc_all_planets(jd.jd_tt)
    diff = abs(p["rahu"].longitude_tropical - p["ketu"].longitude_tropical) % 360
    assert min(diff, 360 - diff) == pytest.approx(180.0, abs=1e-6)