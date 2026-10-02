"""
HTTP API over the calculation engine.

The mobile app depends on this contract, so it is deliberately small and
explicit: no field is optional unless it truly is, and calculation config is
echoed back with every chart so the client can display which conventions
produced the result.

The API never invents data. If a chart cannot be computed it returns a 422
with a reason, rather than returning a partial chart that would look valid.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from engine.events import (
    SUB_CATEGORIES,
    DatePrecision,
    EventCategory,
    LifeEvent,
    Profile,
    resolve_date_interval,
)
from engine.features import extract_features_for_event
from engine.vedic_layer import build_vedic_chart, chart_to_dict
from storage.event_store import EventStore

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"

app = FastAPI(
    title="Vedic Chart API",
    version="0.1.0",
    description="Sidereal chart calculation with explicit, stored conventions.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# The Expo web build is mounted at the bottom of this file, AFTER all the API
# routes. FastAPI matches routes in registration order, so a catch-all placed
# here would shadow /health, /taxonomy and the rest.


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BirthInput(BaseModel):
    """Birth data.

    Only name, date and time are genuinely required. Give a city and the
    coordinates and timezone are looked up; give coordinates and the
    timezone falls back to IST. Everything else is derived.
    """

    name: str = Field(min_length=1, max_length=200)
    birth_date: str
    birth_time: str = Field(
        pattern=r"^\d{1,2}:\d{2}(:\d{2})?$",
        description="Local civil time, H:MM or HH:MM:SS",
    )
    city: str = Field(default="", description="City name; looked up in the built-in table")
    timezone: str = Field(
        default="",
        description="IANA identifier. Defaults to Asia/Kolkata when omitted.",
    )
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    country: str = ""
    # How the birth time is pinned. For pre-1900 births a named zone is
    # often subtly wrong; see the LMT note below.
    utc_offset: str | None = Field(
        default=None,
        pattern=r"^[+-]\d{2}:\d{2}$",
        description="Fixed UTC offset such as +05:30. Overrides `timezone` "
        "when given; use for births before about 1900.",
    )

    model_config = {"json_schema_extra": {
        "examples": [{
            "name": "Einstein", "birth_date": "1879-03-14", "birth_time": "11:30",
            "city": "Ulm", "utc_offset": "+00:40",
        }]
    }}

    def resolved(self) -> tuple[float, float, str, str, str]:
        """Return (lat, lon, tz_for_calc, tz_label, city_label).

        Raises HTTPException with an actionable message rather than a
        validation error, because the fix is to pick a city, not to
        restate the schema.
        """
        from engine.cities import DEFAULT_TIMEZONE
        from engine.cities import get as city_get

        lat, lon = self.latitude, self.longitude
        tz = self.timezone.strip()
        city_label = self.city.strip()

        if (lat is None or lon is None) and city_label:
            found = city_get(city_label)
            if found is None:
                near = ", ".join(c.name for c in search_city(city_label, 5))
                raise HTTPException(
                    422,
                    f"city {city_label!r} is not in the built-in table. "
                    f"Closest matches: {near or 'none'}. "
                    "Supply latitude and longitude explicitly, or use one of "
                    "the listed cities.",
                )
            lat = found.latitude if lat is None else lat
            lon = found.longitude if lon is None else lon
            if not tz:
                tz = found.timezone
            if not self.country:
                self.country = found.country

        if lat is None or lon is None:
            # Default to Delhi so a bare name/date/time still works. The
            # ascendant depends on the clock offset more than the exact
            # coordinates, and IST is the default zone, so Delhi keeps the
            # two consistent.
            fallback = city_get("Delhi")
            lat, lon = fallback.latitude, fallback.longitude
            if not tz and not self.utc_offset:
                tz = fallback.timezone
            if not city_label:
                city_label = f"{fallback.name} (default)"

        if self.utc_offset:
            tz_label = f"UTC{self.utc_offset}"
            tz_for_calc = tz_label
        else:
            tz_label = tz or DEFAULT_TIMEZONE
            tz_for_calc = tz_label

        return lat, lon, tz_for_calc, tz_label, city_label


def search_city(query: str, limit: int):
    from engine.cities import search

    return search(query, limit)


class EventInput(BaseModel):
    category: EventCategory
    sub_category: str
    date: str = Field(description="Date at the granularity of `precision`")
    precision: DatePrecision = DatePrecision.EXACT
    impact: int = Field(default=3, ge=1, le=5)
    certainty: int = Field(default=3, ge=1, le=5)
    description: str = ""


class PredictionRequest(BaseModel):
    profile_id: str
    months_ahead: int = Field(default=12, ge=1, le=60)
    score_threshold: float = Field(default=0.35, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_local_datetime(birth: BirthInput):
    from datetime import datetime

    parts = birth.birth_time.split(":")
    hour, minute = int(parts[0]), int(parts[1])
    second = int(parts[2]) if len(parts) > 2 else 0
    y, m, d = (int(x) for x in birth.birth_date.split("-"))
    try:
        return datetime(y, m, d, hour, minute, second)
    except ValueError as exc:
        raise HTTPException(422, f"invalid birth date: {exc}") from exc


def _build_chart(birth: BirthInput, config: dict[str, Any] | None = None):
    naive = _parse_local_datetime(birth)
    lat, lon, tz_calc, tz_label, city_label = birth.resolved()
    profile = Profile(
        # Generated per request. A fixed placeholder would make every
        # profile share one primary key, so a second profile would silently
        # overwrite the first.
        profile_id=str(uuid.uuid4()),
        birth_date=naive.date(),
        birth_time=naive.strftime("%H:%M:%S"),
        timezone=tz_label,
        latitude=lat,
        longitude=lon,
        city=city_label,
        country=birth.country,
        calc_config=config
        or Profile.__dataclass_fields__["calc_config"].default_factory(),
    )
    try:
        chart = build_vedic_chart(naive, tz_calc, lat, lon)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            422,
            f"chart could not be computed: {type(exc).__name__}: {exc}. "
            "Check the date range and timezone identifier.",
        ) from exc
    return chart, profile


def _store() -> EventStore:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return EventStore(DB_PATH)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "version": app.version}


@app.get("/taxonomy")
def taxonomy() -> dict[str, Any]:
    """Event categories and sub-categories, so the client never hardcodes them."""
    return {
        "categories": {
            c.value: sorted(s) for c, s in SUB_CATEGORIES.items()
        },
        "precisions": [p.value for p in DatePrecision],
    }


@app.get("/cities")
def cities(q: str = "", limit: int = 20) -> dict[str, Any]:
    """City lookup, so the client never needs latitude/longitude typed in."""
    from engine.cities import DEFAULT_TIMEZONE, search

    return {
        "cities": [
            {
                "name": c.name,
                "country": c.country,
                "latitude": c.latitude,
                "longitude": c.longitude,
                "timezone": c.timezone,
            }
            for c in search(q, min(limit, 50))
        ],
        "default_timezone": DEFAULT_TIMEZONE,
    }


@app.get("/config")
def config() -> dict[str, Any]:
    """The conventions this build uses. Shown in the app so a user knows
    what produced their chart."""
    return {
        "ayanamsha": "lahiri",
        "house_system": "whole_sign",
        "divisional_charts": ["D1", "D9", "D10", "D12"],
        "dasha_system": "vimshottari",
        "dasha_levels": 3,
        "note": (
            "Lahiri is implemented via Swiss Ephemeris, which differs from the "
            "commonly published J2000 value (23.857092 vs 23.853086 deg) by "
            "about 14 arcsec. Changing any of these invalidates stored charts."
        ),
    }


@app.post("/chart", tags=["chart"])
def compute_chart(birth: BirthInput) -> dict[str, Any]:
    """Compute a natal chart. Returns the chart plus the config used."""
    chart, profile = _build_chart(birth)
    return {
        "chart": chart_to_dict(chart),
        "calc_config": profile.calc_config,
        "chart_fingerprint": profile.chart_fingerprint(),
    }


@app.post("/profiles", status_code=201, tags=["profiles"])
def create_profile(birth: BirthInput) -> dict[str, Any]:
    """Create a profile and precompute its chart."""
    chart, profile = _build_chart(birth)
    with _store() as store:
        pid = store.add_profile(profile)
        store.store_chart(pid, chart_to_dict(chart), chart.__class__.__name__)
    return {"profile_id": pid, "calc_config": profile.calc_config,
            "chart_fingerprint": profile.chart_fingerprint()}


@app.get("/profiles/{profile_id}", tags=["profiles"])
def get_profile(profile_id: str) -> dict[str, Any]:
    with _store() as store:
        profile = store.get_profile(profile_id)
        if profile is None:
            raise HTTPException(404, "profile not found")
        row = store.conn.execute(
            "SELECT chart_data FROM profiles WHERE profile_id = ?", (profile_id,)
        ).fetchone()
        events = store.get_events(profile_id)
    return {
        "profile": {
            "profile_id": profile.profile_id,
            "birth_date": profile.birth_date.isoformat(),
            "birth_time": profile.birth_time,
            "timezone": profile.timezone,
            "latitude": profile.latitude,
            "longitude": profile.longitude,
            "city": profile.city,
            "country": profile.country,
            "calc_config": profile.calc_config,
        },
        "chart": json.loads(row["chart_data"]) if row and row["chart_data"] else None,
        "event_count": len(events),
    }


@app.post("/profiles/{profile_id}/events", status_code=201, tags=["events"])
def add_event(profile_id: str, payload: EventInput) -> dict[str, Any]:
    valid = SUB_CATEGORIES[payload.category]
    if payload.sub_category not in valid:
        raise HTTPException(
            422,
            f"sub_category {payload.sub_category!r} invalid for "
            f"{payload.category.value}; expected {sorted(valid)}",
        )
    try:
        interval = resolve_date_interval(payload.date, payload.precision)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    event = LifeEvent(
        profile_id=profile_id,
        category=payload.category,
        sub_category=payload.sub_category,
        date_interval=interval,
        impact=payload.impact,
        certainty=payload.certainty,
        description=payload.description,
    )
    with _store() as store:
        if store.get_profile(profile_id) is None:
            raise HTTPException(404, "profile not found")
        eid = store.add_event(event)
    return {
        "event_id": eid,
        "date_interval": interval.to_json(),
        "usable_for_timing_analysis": event.usable_for_timing_analysis,
    }


@app.get("/profiles/{profile_id}/events", tags=["events"])
def list_events(profile_id: str) -> dict[str, Any]:
    with _store() as store:
        events = store.get_events(profile_id)
        summary = store.dataset_summary(profile_id)
    return {
        "events": [e.to_json() for e in events],
        "summary": summary,
    }


@app.get("/profiles/{profile_id}/timeline", tags=["events"])
def timeline(profile_id: str) -> dict[str, Any]:
    """Timeline, with the dasha context for each event.

    Year-precision events report the SET of configurations consistent with
    the stated date, not a single arbitrary one.
    """
    with _store() as store:
        profile = store.get_profile(profile_id)
        if profile is None:
            raise HTTPException(404, "profile not found")
        events = store.get_events(profile_id)

    from datetime import datetime

    naive = datetime.strptime(profile.birth_time, "%H:%M:%S")
    chart = build_vedic_chart(
        datetime.combine(profile.birth_date, naive.time()),
        profile.timezone,
        profile.latitude,
        profile.longitude,
    )

    out = []
    for ev in events:
        vectors = extract_features_for_event(chart, ev, step_days=14)
        lords = sorted(
            {
                (v.dasha_lord, v.antardasha_lord, v.pratyantardasha_lord)
                for v in vectors
            }
        )
        out.append(
            {
                **ev.to_json(),
                "candidate_dates": len(ev.effective_dates()),
                "dasha_configurations": [
                    {"maha": m, "antar": a, "praty": p} for m, a, p in lords
                ],
            }
        )
    return {"events": out}


@app.get("/profiles/{profile_id}/analysis", tags=["analysis"])
def historical_analysis(profile_id: str) -> dict[str, Any]:
    """Summary statistics over stored events. Descriptive only."""
    with _store() as store:
        profile = store.get_profile(profile_id)
        if profile is None:
            raise HTTPException(404, "profile not found")
        events = store.get_events(profile_id)
        summary = store.dataset_summary(profile_id)

    by_category: dict[str, int] = {}
    for ev in events:
        by_category[ev.category.value] = by_category.get(ev.category.value, 0) + 1

    return {
        "summary": summary,
        "events_by_category": by_category,
        "precision_breakdown": {
            p.value: sum(
                1 for e in events
                if e.date_interval.precision is p
            )
            for p in DatePrecision
        },
        "caveat": (
            "These are counts of documented events, not evidence of "
            "astrological association. No prediction has been generated for "
            "this profile."
        ),
    }


def run() -> None:  # pragma: no cover
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


# ---------------------------------------------------------------------------
# Static single-page app
#
# Mounted LAST so it cannot shadow the API routes above: FastAPI resolves
# routes in registration order, and a catch-all registered early would
# swallow /health and /taxonomy.
#
# Same-origin is what makes the app shareable: the client issues relative
# requests, so one process behind one public URL serves both the UI and the
# API, with no CORS and no host baked into the bundle.
# ---------------------------------------------------------------------------

_DIST = Path(__file__).resolve().parent.parent / "mobile" / "dist"
if (_DIST / "index.html").exists():
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    app.mount("/_expo", StaticFiles(directory=_DIST / "_expo"), name="expo-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        """Serve static assets, falling back to index.html for client routes."""
        if full_path:
            candidate = (_DIST / full_path).resolve()
            # Guard against traversal out of the dist folder.
            try:
                candidate.relative_to(_DIST.resolve())
            except ValueError as exc:
                raise HTTPException(404, "not found") from exc
            if candidate.is_file():
                return FileResponse(candidate)
        return FileResponse(_DIST / "index.html")


if __name__ == "__main__":  # pragma: no cover
    run()
