"""
Event storage.

SQLite for local/research use (stdlib, zero config). The production target is
the PostgreSQL schema in specs/event_schema.sql; this module is the reference
implementation of the same semantics and the place where Gate 3
("historical events stored reproducibly") is enforced.

Reproducibility means: every stored feature records the chart fingerprint it
was derived from, so changing the ayanamsha or house system later makes stale
rows detectable instead of silently wrong.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any

from engine.events import (
    SUB_CATEGORIES,
    DateInterval,
    DatePrecision,
    EventCategory,
    LifeEvent,
    Profile,
    resolve_date_interval,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    profile_id        TEXT PRIMARY KEY,
    birth_date        TEXT NOT NULL,
    birth_time        TEXT NOT NULL,
    timezone          TEXT NOT NULL,
    latitude          REAL NOT NULL,
    longitude         REAL NOT NULL,
    city              TEXT DEFAULT '',
    country           TEXT DEFAULT '',
    calc_config       TEXT NOT NULL,
    chart_data        TEXT,
    chart_computed_at TEXT,
    chart_fingerprint TEXT,
    notes             TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS events (
    event_id     TEXT PRIMARY KEY,
    profile_id   TEXT NOT NULL REFERENCES profiles(profile_id) ON DELETE CASCADE,
    category     TEXT NOT NULL,
    sub_category TEXT NOT NULL,

    -- Date precision is first class. start_exact is NULL when unknown;
    -- start_lower/start_upper bound the true date for coarse precision.
    start_date     TEXT,
    end_date       TEXT,
    date_precision TEXT NOT NULL,
    start_lower    TEXT,
    start_upper    TEXT,
    end_lower      TEXT,
    end_upper      TEXT,

    impact    INTEGER NOT NULL CHECK (impact BETWEEN 1 AND 5),
    certainty INTEGER NOT NULL CHECK (certainty BETWEEN 1 AND 5),
    description TEXT DEFAULT '',
    notes       TEXT DEFAULT '',
    source      TEXT DEFAULT 'manual',
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS event_features (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id          TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    profile_id        TEXT NOT NULL,
    chart_fingerprint TEXT NOT NULL,
    feature_json      TEXT NOT NULL,
    created_at        TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_events_profile   ON events(profile_id);
CREATE INDEX IF NOT EXISTS idx_events_category  ON events(category);
CREATE INDEX IF NOT EXISTS idx_events_precison ON events(date_precision);
CREATE INDEX IF NOT EXISTS idx_features_event   ON event_features(event_id);
"""


class EventStore:
    """SQLite-backed repository for profiles and events."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> EventStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- profiles ---------------------------------------------------------

    def add_profile(self, profile: Profile) -> str:
        pid = profile.profile_id or str(uuid.uuid4())
        self.conn.execute(
            """
            INSERT INTO profiles (
                profile_id, birth_date, birth_time, timezone, latitude, longitude,
                city, country, calc_config, chart_data, chart_computed_at,
                chart_fingerprint, notes
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                pid,
                profile.birth_date.isoformat(),
                profile.birth_time,
                profile.timezone,
                profile.latitude,
                profile.longitude,
                profile.city,
                profile.country,
                json.dumps(profile.calc_config, sort_keys=True),
                json.dumps(profile.chart_data) if profile.chart_data else None,
                profile.chart_computed_at,
                profile.chart_fingerprint(),
                profile.notes,
            ),
        )
        self.conn.commit()
        return pid

    def get_profile(self, profile_id: str) -> Profile | None:
        row = self.conn.execute(
            "SELECT * FROM profiles WHERE profile_id = ?", (profile_id,)
        ).fetchone()
        if row is None:
            return None
        return Profile(
            profile_id=row["profile_id"],
            birth_date=date.fromisoformat(row["birth_date"]),
            birth_time=row["birth_time"],
            timezone=row["timezone"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            city=row["city"],
            country=row["country"],
            calc_config=json.loads(row["calc_config"]),
            chart_data=json.loads(row["chart_data"]) if row["chart_data"] else None,
            chart_computed_at=row["chart_computed_at"],
            notes=row["notes"],
        )

    def chart_fingerprint(self, profile_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT chart_fingerprint FROM profiles WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()
        return row["chart_fingerprint"] if row else None

    def store_chart(
        self, profile_id: str, chart_json: dict[str, Any], computed_at: str
    ) -> None:
        self.conn.execute(
            "UPDATE profiles SET chart_data = ?, chart_computed_at = ? "
            "WHERE profile_id = ?",
            (json.dumps(chart_json, sort_keys=True), computed_at, profile_id),
        )
        self.conn.commit()

    # -- events -----------------------------------------------------------

    def add_event(self, event: LifeEvent) -> str:
        eid = event.event_id or str(uuid.uuid4())
        iv = event.date_interval
        eiv = event.end_interval

        self.conn.execute(
            """
            INSERT INTO events (
                event_id, profile_id, category, sub_category,
                start_date, end_date, date_precision,
                start_lower, start_upper, end_lower, end_upper,
                impact, certainty, description, notes, source
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                eid,
                event.profile_id,
                event.category.value,
                event.sub_category,
                iv.start.isoformat() if iv.precision is not DatePrecision.UNKNOWN else None,
                eiv.start.isoformat()
                if eiv and eiv.precision is not DatePrecision.UNKNOWN
                else None,
                iv.precision.value,
                iv.start.isoformat(),
                iv.end.isoformat(),
                eiv.start.isoformat() if eiv else None,
                eiv.end.isoformat() if eiv else None,
                event.impact,
                event.certainty,
                event.description,
                event.notes,
                event.source,
            ),
        )
        self.conn.commit()
        return eid

    def get_event(self, event_id: str) -> LifeEvent | None:
        row = self.conn.execute(
            "SELECT * FROM events WHERE event_id = ?", (event_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_event(row)

    def get_events(
        self,
        profile_id: str | None = None,
        category: EventCategory | None = None,
        usable_only: bool = False,
    ) -> list[LifeEvent]:
        clauses: list[str] = []
        params: list[Any] = []
        if profile_id:
            clauses.append("profile_id = ?")
            params.append(profile_id)
        if category:
            clauses.append("category = ?")
            params.append(category.value)
        if usable_only:
            clauses.append("date_precision != ?")
            params.append(DatePrecision.UNKNOWN.value)

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"SELECT * FROM events{where} ORDER BY start_lower", params
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> LifeEvent:
        precision = DatePrecision(row["date_precision"])
        interval = (
            DateInterval(
                start=date.fromisoformat(row["start_lower"]),
                end=date.fromisoformat(row["start_upper"]),
                precision=precision,
            )
            if row["start_lower"]
            else DateInterval(
                start=date(1900, 1, 1), end=date(2100, 1, 1),
                precision=DatePrecision.UNKNOWN,
            )
        )
        end_interval = None
        if row["end_lower"]:
            end_interval = DateInterval(
                start=date.fromisoformat(row["end_lower"]),
                end=date.fromisoformat(row["end_upper"]),
                precision=precision,
            )
        return LifeEvent(
            event_id=row["event_id"],
            profile_id=row["profile_id"],
            category=EventCategory(row["category"]),
            sub_category=row["sub_category"],
            date_interval=interval,
            end_interval=end_interval,
            impact=row["impact"],
            certainty=row["certainty"],
            description=row["description"],
            notes=row["notes"],
            source=row["source"],
        )

    # -- features ---------------------------------------------------------

    def add_features(
        self,
        event_id: str,
        profile_id: str,
        feature_json: dict[str, Any],
        chart_fingerprint: str | None = None,
    ) -> None:
        """Persist extracted features, stamped with the chart fingerprint.

        Storing the fingerprint is what makes Gate 3 checkable: if the
        ayanamsha or house system is ever changed, every previously derived
        feature set can be identified as stale.
        """
        fp = chart_fingerprint or self.chart_fingerprint(profile_id) or ""
        self.conn.execute(
            "INSERT INTO event_features "
            "(event_id, profile_id, chart_fingerprint, feature_json) "
            "VALUES (?,?,?,?)",
            (event_id, profile_id, fp, json.dumps(feature_json, sort_keys=True)),
        )
        self.conn.commit()

    def get_features(self, event_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT feature_json, chart_fingerprint FROM event_features "
            "WHERE event_id = ? ORDER BY id",
            (event_id,),
        ).fetchall()
        return [json.loads(r["feature_json"]) for r in rows]

    def find_stale_features(self) -> list[tuple[str, str, str]]:
        """Return (event_id, profile_id, stored_fingerprint) where the stored
        fingerprint no longer matches the profile's current chart config.

        The expected fingerprint is RECOMPUTED from the profile row rather
        than read from its cached column, because editing calc_config does
        not by itself refresh that column. Comparing against the cache would
        silently report stale features as current.
        """
        rows = self.conn.execute(
            """
            SELECT f.event_id, f.profile_id, f.chart_fingerprint,
                   p.birth_date, p.birth_time, p.timezone,
                   p.latitude, p.longitude, p.calc_config
            FROM event_features f
            JOIN profiles p ON p.profile_id = f.profile_id
            """
        ).fetchall()

        stale: list[tuple[str, str, str]] = []
        for r in rows:
            expected = Profile(
                profile_id=r["profile_id"],
                birth_date=date.fromisoformat(r["birth_date"]),
                birth_time=r["birth_time"],
                timezone=r["timezone"],
                latitude=r["latitude"],
                longitude=r["longitude"],
                calc_config=json.loads(r["calc_config"]),
            ).chart_fingerprint()
            if r["chart_fingerprint"] != expected:
                stale.append((r["event_id"], r["profile_id"], r["chart_fingerprint"]))
        return stale

    # -- reporting --------------------------------------------------------

    def dataset_summary(self, profile_id: str) -> dict[str, Any]:
        events = self.get_events(profile_id)
        usable = [e for e in events if e.usable_for_timing_analysis]
        from engine.events import precision_distribution

        return {
            "profile_id": profile_id,
            "total_events": len(events),
            "usable_events": len(usable),
            "excluded_unknown_date": len(events) - len(usable),
            "precision_distribution": precision_distribution(events),
            "categories": {
                c.value: sum(1 for e in events if e.category is c)
                for c in EventCategory
                if any(e.category is c for e in events)
            },
            "meets_m3_benchmark": len(events) >= 10,
        }


def validate_taxonomy() -> list[str]:
    """Return any sub-categories present in the SQL schema but missing here."""
    problems = []
    for cat, subs in SUB_CATEGORIES.items():
        if not subs:
            problems.append(f"{cat.value} has no sub-categories")
    return problems


def build_event(
    profile_id: str,
    category: EventCategory,
    sub_category: str,
    when: str,
    precision: DatePrecision,
    **kwargs: Any,
) -> LifeEvent:
    """Convenience constructor that resolves the date interval."""
    return LifeEvent(
        profile_id=profile_id,
        category=category,
        sub_category=sub_category,
        date_interval=resolve_date_interval(when, precision),
        **kwargs,
    )


def iter_timing_events(events: Iterable[LifeEvent]) -> list[LifeEvent]:
    return sorted(
        (e for e in events if e.usable_for_timing_analysis),
        key=lambda e: e.date_interval.start,
    )