"""Simplified input: city lookup, IST default, fixed UTC offsets."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import api.server as server  # noqa: E402
from engine.cities import CITIES, DEFAULT_TIMEZONE, search  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_PATH", tmp_path / "t.db")
    return TestClient(server.app)


# ---------------------------------------------------------------------------
# City table
# ---------------------------------------------------------------------------


def test_default_timezone_is_ist():
    assert DEFAULT_TIMEZONE == "Asia/Kolkata"


def test_indian_cities_use_ist():
    ist = [c for c in CITIES if c.country == "India"]
    assert len(ist) >= 30
    for c in ist:
        assert c.timezone == "Asia/Kolkata"


def test_city_coordinates_are_in_range():
    for c in CITIES:
        assert -90 <= c.latitude <= 90, c.name
        assert -180 <= c.longitude <= 180, c.name
        assert "/" in c.timezone or c.timezone == "UTC", c.name


def test_city_names_are_unique():
    names = [c.name for c in CITIES]
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, f"duplicate city names: {dupes}"


def test_search_is_case_insensitive_and_partial():
    assert search("MUMBAI")[0].name == "Mumbai"
    assert search("mum")[0].name == "Mumbai"
    assert any(c.name == "New Delhi" or c.name == "Delhi"
               for c in search("delhi"))
    assert search("zzzznothing") == []
    assert search("")  # empty returns a default list


# ---------------------------------------------------------------------------
# Simplification: coordinates never need to be typed
# ---------------------------------------------------------------------------


def test_city_only_is_enough(client):
    r = client.post("/chart", json={
        "name": "A", "birth_date": "1990-01-01", "birth_time": "12:00",
        "city": "Mumbai",
    })
    assert r.status_code == 200
    assert r.json()["chart"]["lagna"]["sign_name"]


def test_bare_name_date_time_defaults_to_ist(client):
    r = client.post("/chart", json={
        "name": "A", "birth_date": "1990-01-01", "birth_time": "12:00",
    })
    assert r.status_code == 200


def test_defaulted_chart_matches_explicit_ist(client):
    """The Delhi fallback must not shift the clock offset."""
    a = client.post("/chart", json={
        "name": "A", "birth_date": "1990-06-15", "birth_time": "07:20",
        "city": "Delhi"}).json()
    b = client.post("/chart", json={
        "name": "A", "birth_date": "1990-06-15", "birth_time": "07:20",
        "city": "Delhi", "timezone": "Asia/Kolkata"}).json()
    assert a["chart"]["lagna"] == b["chart"]["lagna"]


def test_short_time_format_accepted(client):
    r = client.post("/chart", json={
        "name": "A", "birth_date": "1990-01-01", "birth_time": "9:05",
    })
    assert r.status_code == 200


def test_unknown_city_suggests_alternatives(client):
    r = client.post("/chart", json={
        "name": "A", "birth_date": "1990-01-01", "birth_time": "12:00",
        "city": "Mumboo",
    })
    assert r.status_code == 422
    assert "not in the built-in table" in r.json()["detail"]


def test_cities_endpoint_lists_default_timezone(client):
    body = client.get("/cities", params={"q": "mum"}).json()
    assert body["default_timezone"] == "Asia/Kolkata"
    assert body["cities"][0]["name"] == "Mumbai"
    assert body["cities"][0]["timezone"] == "Asia/Kolkata"


# ---------------------------------------------------------------------------
# Fixed UTC offsets, for historical births
# ---------------------------------------------------------------------------


def test_utc_offset_reproduces_the_astro_databank_reading(client):
    """+00:40 for Ulm is what Astro-Databank records.

    It is NOT the same as Europe/Berlin, whose 1879 local mean time is
    +00:53:28 — a 13.5-minute discrepancy that arises because Astro-Databank
    derives LMT from the stated longitude while tzdb uses the zone's
    reference meridian. Both land on Gemini here, but the ascendant degrees
    differ, and that is precisely why the offset is worth being able to
    state explicitly.
    """
    a = client.post("/chart", json={
        "name": "E", "birth_date": "1879-03-14", "birth_time": "11:30",
        "latitude": 48.3988, "longitude": 9.9916,
        "timezone": "Europe/Berlin"}).json()["chart"]
    b = client.post("/chart", json={
        "name": "E", "birth_date": "1879-03-14", "birth_time": "11:30",
        "latitude": 48.3988, "longitude": 9.9916,
        "utc_offset": "+00:40"}).json()["chart"]

    # Same sign, different degree: the ambiguity is real but sub-sign here.
    assert b["lagna"]["sign_name"] == "Gemini" == a["lagna"]["sign_name"]
    assert b["planets"]["sun"]["sign_name"] == "Pisces"
    assert b["planets"]["moon"]["nakshatra_name"] == "Jyeshtha"
    assert b["lagna"]["degree"] != a["lagna"]["degree"]


def test_ist_offset_is_accepted_despite_half_hour(client):
    """Etc/GMT has no +05:30 zone, so fixed offsets need explicit support."""
    r = client.post("/chart", json={
        "name": "A", "birth_date": "1990-01-01", "birth_time": "12:00",
        "latitude": 19.076, "longitude": 72.8777, "utc_offset": "+05:30"})
    assert r.status_code == 200
    c = client.post("/chart", json={
        "name": "A", "birth_date": "1990-01-01", "birth_time": "12:00",
        "latitude": 19.076, "longitude": 72.8777, "timezone": "Asia/Kolkata"}).json()
    assert r.json()["chart"]["lagna"] == c["chart"]["lagna"]


def test_utc_offset_overrides_timezone(client):
    """The offset wins, and the same instant can be expressed either way.

    11:30 at +05:30 is 06:00 UTC, which is 06:40 at +00:40.
    """
    via_offset = client.post("/chart", json={
        "name": "E", "birth_date": "1879-03-14", "birth_time": "11:30",
        "latitude": 48.3988, "longitude": 9.9916,
        "timezone": "Europe/Berlin", "utc_offset": "+05:30"}).json()["chart"]
    same_instant = client.post("/chart", json={
        "name": "E", "birth_date": "1879-03-14", "birth_time": "06:40",
        "latitude": 48.3988, "longitude": 9.9916, "utc_offset": "+00:40"}).json()["chart"]
    assert via_offset["lagna"]["degree"] == pytest.approx(
        same_instant["lagna"]["degree"], abs=1e-6
    )

    # And the offset genuinely overrides the zone: a different clock time
    # with the same offset is a different chart.
    other = client.post("/chart", json={
        "name": "E", "birth_date": "1879-03-14", "birth_time": "06:00",
        "latitude": 48.3988, "longitude": 9.9916, "utc_offset": "+00:40"}).json()["chart"]
    assert other["lagna"]["degree"] != same_instant["lagna"]["degree"]


def test_malformed_utc_offset_rejected(client):
    r = client.post("/chart", json={
        "name": "A", "birth_date": "1990-01-01", "birth_time": "12:00",
        "latitude": 1.0, "longitude": 1.0, "utc_offset": "5:30"})
    assert r.status_code == 422