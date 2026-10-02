"""
Event domain model.

The central concern here is DATE PRECISION. A user who says "I changed jobs
sometime in 2018" has not given us a day. If the engine silently treats that
as 2018-01-01, every downstream statistic inherits fabricated precision: a
dasha boundary can fall inside the true window and not the assumed one, and
the resulting false-positive rate looks better than it should.

So an EventDate carries a precision level and resolves to an INTERVAL. Feature
extraction must marginalise over that interval rather than pick a point.
"""

from __future__ import annotations

import calendar
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Any


class DatePrecision(str, Enum):
    """How precisely the user actually knows the event date."""

    EXACT = "exact"      # we know the day
    MONTH = "month"      # we know the month, not the day
    QUARTER = "quarter"  # we know the calendar quarter
    YEAR = "year"        # we know only the year
    UNKNOWN = "unknown"  # we know nothing; event is excluded from dated analysis

    @property
    def max_span_days(self) -> int | None:
        """Widest plausible interval, in days. None means unbounded."""
        return {
            DatePrecision.EXACT: 0,
            DatePrecision.MONTH: 30,
            DatePrecision.QUARTER: 92,
            DatePrecision.YEAR: 366,
            DatePrecision.UNKNOWN: None,
        }[self]


class EventCategory(str, Enum):
    CAREER = "career"
    RELATIONSHIP = "relationship"
    FAMILY = "family"
    EDUCATION = "education"
    FINANCE = "finance"
    LOCATION = "location"
    HEALTH = "health"
    LEGAL = "legal"
    OTHER = "other"


# Taxonomy frozen in specs/astrology_rules.md. Kept as an explicit mapping so
# an invalid sub-category raises instead of quietly entering the database.
SUB_CATEGORIES: dict[EventCategory, set[str]] = {
    EventCategory.CAREER: {
        "first_job", "promotion", "job_loss", "job_change",
        "business_launch", "business_closure", "retirement",
    },
    EventCategory.RELATIONSHIP: {
        "relationship_started", "marriage", "separation", "divorce",
    },
    EventCategory.FAMILY: {
        "child_birth", "major_family_event", "parent_death",
    },
    EventCategory.EDUCATION: {
        "admission", "graduation", "major_qualification",
    },
    EventCategory.FINANCE: {
        "major_gain", "major_loss", "property_purchase", "debt_restructuring",
    },
    EventCategory.LOCATION: {
        "relocation", "foreign_move", "home_purchase",
    },
    EventCategory.HEALTH: {
        "major_illness", "surgery", "recovery", "accident",
    },
    EventCategory.LEGAL: {
        "legal_dispute", "legal_victory", "legal_settlement",
    },
    EventCategory.OTHER: {"other"},
}


@dataclass(frozen=True)
class DateInterval:
    """A closed interval of candidate dates for an event."""

    start: date
    end: date
    precision: DatePrecision

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(f"interval end {self.end} precedes start {self.start}")

    @property
    def span_days(self) -> int:
        return (self.end - self.start).days

    @property
    def is_point(self) -> bool:
        return self.start == self.end

    def contains(self, d: date) -> bool:
        return self.start <= d <= self.end

    def sample_dates(self, step_days: int = 1) -> list[date]:
        """Deterministic sample points across the interval.

        Always includes both endpoints. Feature extraction uses this so a
        year-precision event contributes a range of configurations rather
        than one arbitrary guess.
        """
        if self.is_point:
            return [self.start]
        step = max(step_days, 1)
        dates = []
        cur = self.start
        while cur < self.end:
            dates.append(cur)
            cur += timedelta(days=step)
        dates.append(self.end)
        return dates

    def to_json(self) -> dict[str, Any]:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "precision": self.precision.value,
        }


def resolve_date_interval(
    value: str | date,
    precision: DatePrecision,
) -> DateInterval:
    """Build the interval of dates consistent with a stated precision.

    ``value`` is interpreted at the granularity implied by ``precision``:
      YEAR + "2018"        -> 2018-01-01 .. 2018-12-31
      QUARTER + "2018-Q1"  -> 2018-01-01 .. 2018-03-31
      MONTH + "2018-06"    -> 2018-06-01 .. 2018-06-30
      EXACT + "2018-06-12" -> 2018-06-12 .. 2018-06-12
    """
    if precision is DatePrecision.UNKNOWN:
        raise ValueError("UNKNOWN precision has no resolvable interval")

    s = value.isoformat() if isinstance(value, date) else value

    if precision is DatePrecision.YEAR:
        y = int(s[:4])
        start, end = date(y, 1, 1), date(y, 12, 31)

    elif precision is DatePrecision.QUARTER:
        year_part, quarter_part = s.split("-Q")
        y, q = int(year_part), int(quarter_part)
        if not 1 <= q <= 4:
            raise ValueError(f"quarter must be 1-4, got {q}")
        start_month = 3 * (q - 1) + 1
        end_month = start_month + 2
        start = date(y, start_month, 1)
        end = date(y, end_month, calendar.monthrange(y, end_month)[1])

    elif precision is DatePrecision.MONTH:
        y, m = int(s[:4]), int(s[5:7])
        start = date(y, m, 1)
        end = date(y, m, calendar.monthrange(y, m)[1])

    else:  # EXACT
        d = date.fromisoformat(s)
        start = end = d

    return DateInterval(start=start, end=end, precision=precision)


@dataclass
class LifeEvent:
    """A single documented historical event."""

    profile_id: str
    category: EventCategory
    sub_category: str
    date_interval: DateInterval
    end_interval: DateInterval | None = None
    impact: int = 3          # 1 (minor) .. 5 (life-changing)
    certainty: int = 3       # 1 (uncertain) .. 5 (verified)
    description: str = ""
    notes: str = ""
    source: str = "manual"
    event_id: str | None = None

    def __post_init__(self) -> None:
        if self.sub_category not in SUB_CATEGORIES[self.category]:
            raise ValueError(
                f"sub_category {self.sub_category!r} is not valid for "
                f"category {self.category.value!r}; expected one of "
                f"{sorted(SUB_CATEGORIES[self.category])}"
            )
        for name, value in (("impact", self.impact), ("certainty", self.certainty)):
            if not 1 <= value <= 5:
                raise ValueError(f"{name} must be 1-5, got {value}")
        if (
            self.end_interval
            and self.date_interval.precision is not DatePrecision.UNKNOWN
            and self.end_interval.start < self.date_interval.end
        ):
            # An end before the (widest) start is always inconsistent.
            raise ValueError(
                f"end {self.end_interval.start} precedes start "
                f"{self.date_interval.start}"
            )

    @property
    def is_point_event(self) -> bool:
        return self.date_interval.is_point and self.end_interval is None

    @property
    def usable_for_timing_analysis(self) -> bool:
        """Events with unknown dates cannot be tied to astrological timing."""
        return self.date_interval.precision is not DatePrecision.UNKNOWN

    def effective_dates(self) -> list[date]:
        """Candidate dates, expanded across the precision interval."""
        return self.date_interval.sample_dates()

    def to_json(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "profile_id": self.profile_id,
            "category": self.category.value,
            "sub_category": self.sub_category,
            "start": self.date_interval.to_json(),
            "end": self.end_interval.to_json() if self.end_interval else None,
            "impact": self.impact,
            "certainty": self.certainty,
            "description": self.description,
            "notes": self.notes,
            "source": self.source,
        }


@dataclass
class Profile:
    """A person: birth data plus the calculation config used for their charts."""

    profile_id: str
    birth_date: date
    birth_time: str          # HH:MM:SS local civil time
    timezone: str            # IANA identifier
    latitude: float
    longitude: float
    city: str = ""
    country: str = ""
    calc_config: dict[str, Any] = field(
        default_factory=lambda: {
            "ayanamsha": "lahiri",
            "house_system": "whole_sign",
            "divisional_charts": ["D1", "D9", "D10", "D12"],
            "dasha_system": "vimshottari",
            "dasha_levels": 3,
        }
    )
    chart_data: dict[str, Any] | None = None
    chart_computed_at: str | None = None
    notes: str = ""

    def chart_fingerprint(self) -> str:
        """Stable hash of everything that affects computed positions.

        Stored alongside every derived feature so a later change to
        ayanamsha or house system is detectable rather than silent.
        """
        import hashlib

        material = json.dumps(
            {
                "birth_date": self.birth_date.isoformat(),
                "birth_time": self.birth_time,
                "timezone": self.timezone,
                "latitude": round(self.latitude, 6),
                "longitude": round(self.longitude, 6),
                "calc_config": self.calc_config,
            },
            sort_keys=True,
        )
        return hashlib.sha256(material.encode()).hexdigest()[:16]


def precision_distribution(events: list[LifeEvent]) -> dict[str, int]:
    """Counts by precision — a dataset-quality indicator worth reporting."""
    counts: dict[str, int] = {p.value: 0 for p in DatePrecision}
    for e in events:
        counts[e.date_interval.precision.value] += 1
    return counts