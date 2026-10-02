"""
Feature extraction for historical correlation.

Given a natal chart and a moment in time, produce a FeatureVector describing
the astrological state: dasha lords, transits, house activations, conditions.

Two properties matter more than the feature list itself:

1. IMPRECISE DATES. A year-precision event has a whole year of plausible
   dates. We extract a FeatureVector for each and keep them all, rather than
   picking one. Downstream association statistics then see the full set of
   configurations consistent with what the user actually told us.

2. NEGATIVE SAMPLES. extract_features_at() works for any date, not just event
   dates. That is what makes it possible to compute expected frequency and
   false-positive rate. An engine that can only look at events can never
   measure a false positive, so it cannot tell signal from a rule that fires
   constantly.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from .events import LifeEvent
from .swisseph_wrapper import (
    calc_all_planets,
    julian_day_from_datetime,
    nakshatra_from_longitude,
    sign_from_longitude,
    tropical_to_sidereal,
)
from .vedic_layer import (
    VedicChart,
    calculate_combustion,
    get_sign_lord,
    planet_aspects_house,
)

PLANETS = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn", "rahu", "ketu")

# Slow-moving bodies that dominate long-horizon timing in Vedic practice.
SLOW_TRANSITS = ("jupiter", "saturn", "rahu", "ketu")


@dataclass(frozen=True)
class TransitState:
    """Where one planet sits on one day, relative to the natal chart."""

    planet: str
    longitude_sidereal: float
    sign: int
    house: int          # house occupied by the transiting planet
    retrograde: bool
    combust: bool
    nakshatra: int


@dataclass
class FeatureVector:
    """Astrological state at a single moment."""

    when: date
    dasha_lord: str | None = None
    antardasha_lord: str | None = None
    pratyantardasha_lord: str | None = None
    transits: dict[str, TransitState] = field(default_factory=dict)
    factors: frozenset[str] = frozenset()

    def to_json(self) -> dict[str, Any]:
        return {
            "when": self.when.isoformat(),
            "dasha_lord": self.dasha_lord,
            "antardasha_lord": self.antardasha_lord,
            "pratyantardasha_lord": self.pratyantardasha_lord,
            "transits": {
                p: {
                    "sign": t.sign,
                    "house": t.house,
                    "retrograde": t.retrograde,
                    "combust": t.combust,
                    "nakshatra": t.nakshatra,
                }
                for p, t in self.transits.items()
            },
            "factors": sorted(self.factors),
        }


# ---------------------------------------------------------------------------
# Dasha lookup
# ---------------------------------------------------------------------------


def _to_date(jd: float) -> date:
    import swisseph as swe

    y, m, d, _ = swe.revjul(jd)
    return date(int(y), int(m), int(d))


def dasha_at_date(chart: VedicChart, when: date) -> tuple[str | None, str | None, str | None]:
    """Return (maha, antar, praty) lords active on ``when``."""
    jd = julian_day_from_datetime(
        datetime.combine(when, time(12, 0)), chart.birth_timezone
    ).jd_tt

    for maha in chart.dasha_periods:
        if not (maha.start_jd <= jd <= maha.end_jd):
            continue
        antar = next(
            (a for a in maha.sub_periods if a.start_jd <= jd <= a.end_jd), None
        )
        praty = None
        if antar:
            praty = next(
                (p for p in antar.sub_periods if p.start_jd <= jd <= p.end_jd), None
            )
        return maha.lord, antar.lord if antar else None, praty.lord if praty else None
    return None, None, None


# ---------------------------------------------------------------------------
# Transit calculation
# ---------------------------------------------------------------------------


def transits_at_date(chart: VedicChart, when: date) -> dict[str, TransitState]:
    """Sidereal transiting positions mapped onto natal whole-sign houses."""
    jd = julian_day_from_datetime(
        datetime.combine(when, time(12, 0)), chart.birth_timezone
    )

    raw = calc_all_planets(jd.jd_tt)
    sun_lon = tropical_to_sidereal(
        raw["sun"].longitude_tropical, jd.jd_tt, chart.ayanamsha
    )

    out: dict[str, TransitState] = {}
    for name, pos in raw.items():
        lon = tropical_to_sidereal(
            pos.longitude_tropical, jd.jd_tt, chart.ayanamsha
        )
        sign = sign_from_longitude(lon)
        out[name] = TransitState(
            planet=name,
            longitude_sidereal=lon,
            sign=sign,
            house=((sign - chart.lagna_sign) % 12) + 1,
            retrograde=pos.retrograde,
            combust=calculate_combustion(name, lon, sun_lon, pos.retrograde),
            nakshatra=nakshatra_from_longitude(lon)[0],
        )
    return out


# ---------------------------------------------------------------------------
# Factor predicates
# ---------------------------------------------------------------------------


def compute_factors(
    chart: VedicChart,
    transits: dict[str, TransitState],
    maha: str | None,
    antar: str | None,
    praty: str | None,
) -> frozenset[str]:
    """The transparent rule set from the spec, expressed as named predicates.

    Every factor is a string so a result can be audited: a researcher can
    read which rules fired without reverse-engineering code.
    """
    factors: set[str] = set()

    # Dasha lords
    if maha:
        factors.add(f"dasha={maha}")
    if antar:
        factors.add(f"antardasha={antar}")
    if praty:
        factors.add(f"pratyantardasha={praty}")

    # Transiting planet occupying a natal house
    for p, t in transits.items():
        factors.add(f"transit_{p}_in_house_{t.house}")
        if t.retrograde:
            factors.add(f"transit_{p}_retrograde")
        if t.combust:
            factors.add(f"transit_{p}_combust")

    # Slow-moving body in a kendra/trikona from the natal lagna
    for p in SLOW_TRANSITS:
        t = transits.get(p)
        if t and t.house in (1, 4, 7, 10):
            factors.add(f"{p}_kendra")
        if t and t.house in (1, 5, 9):
            factors.add(f"{p}_trikona")

    # House lords: which house lords are activated by dasha or transit
    for house in range(1, 13):
        sign = (chart.lagna_sign + house - 1) % 12
        lord = get_sign_lord(sign)
        if maha == lord:
            factors.add(f"maha_lord_of_house_{house}")
        if antar == lord:
            factors.add(f"antar_lord_of_house_{house}")
        # A transiting planet aspecting the house from its transit position
        for p, t in transits.items():
            if planet_aspects_house(p, t.house, house):
                factors.add(f"transit_{p}_aspects_house_{house}")

    # Natal placement context (static per profile, but part of the record)
    for p, vp in chart.planets.items():
        if vp.combust:
            factors.add(f"natal_{p}_combust")
        if vp.retrograde:
            factors.add(f"natal_{p}_retrograde")

    return frozenset(factors)


def extract_features_at(chart: VedicChart, when: date) -> FeatureVector:
    """FeatureVector for one date. Works for any date, event or not."""
    transits = transits_at_date(chart, when)
    maha, antar, praty = dasha_at_date(chart, when)
    return FeatureVector(
        when=when,
        dasha_lord=maha,
        antardasha_lord=antar,
        pratyantardasha_lord=praty,
        transits=transits,
        factors=compute_factors(chart, transits, maha, antar, praty),
    )


def extract_features_for_event(
    chart: VedicChart, event: LifeEvent, step_days: int = 7
) -> list[FeatureVector]:
    """FeatureVectors for every date consistent with the event's precision.

    A day-precision event yields one vector. A year-precision event yields
    vectors across the whole year, so the caller can see which
    configurations were and were not possible given what the user reported.

    ``step_days`` controls sampling density across the interval. The default
    of 7 is a compromise: full 1-day marginalisation of a year would mean
    ~365 vectors and ~3,300 ephemeris calls per event, while 30 days can
    step over a short dasha boundary. Days 7 is fine for the factors this
    engine derives, because the slowest-moving factor (Jupiter's sign change)
    takes on the order of a year, and dasha boundaries are months long.
    """
    if not event.usable_for_timing_analysis:
        return []
    dates = event.date_interval.sample_dates(step_days=step_days)
    return [extract_features_at(chart, d) for d in dates]


def consensus_factors(vectors: list[FeatureVector]) -> frozenset[str]:
    """Factors present in EVERY candidate vector for an event.

    These are the only factors we can claim as reliably associated with the
    event without overstating precision. Factors appearing in only some
    vectors are possible but not established.
    """
    if not vectors:
        return frozenset()
    common = set(vectors[0].factors)
    for v in vectors[1:]:
        common &= v.factors
    return frozenset(common)


def any_factors(vectors: list[FeatureVector]) -> frozenset[str]:
    """Factors present in AT LEAST ONE candidate vector."""
    result: set[str] = set()
    for v in vectors:
        result |= v.factors
    return frozenset(result)


# ---------------------------------------------------------------------------
# Negative sampling
# ---------------------------------------------------------------------------


def sample_negative_dates(
    profile_start: date,
    profile_end: date,
    step_days: int = 30,
    exclude: Iterable[tuple[date, date]] = (),
    category: str | None = None,
    margin_days: int = 0,
) -> list[date]:
    """Dates with no event of ``category`` in the surrounding window.

    These are the comparison group that makes expected frequency and
    false-positive rate computable. ``margin_days`` avoids sampling a date
    that sits within the plausible span of a known event, which would
    mislabel it as a negative.
    """
    excluded: list[tuple[date, date]] = []
    for start, end in exclude:
        if margin_days:
            excluded.append(
                (
                    start - timedelta(days=margin_days),
                    end + timedelta(days=margin_days),
                )
            )
        else:
            excluded.append((start, end))

    def is_excluded(d: date) -> bool:
        return any(s <= d <= e for s, e in excluded)

    dates: list[date] = []
    cur = profile_start
    while cur <= profile_end:
        if not is_excluded(cur):
            dates.append(cur)
        cur += timedelta(days=step_days)
    return dates


def extract_negative_features(
    chart: VedicChart, dates: Iterable[date]
) -> list[FeatureVector]:
    return [extract_features_at(chart, d) for d in dates]