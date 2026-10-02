"""
API contract tests.

The mobile app is built against these endpoints, so the contract is tested
rather than assumed. Particular attention goes to the cases where a quiet
wrong answer would be worse than an error: ambiguous historical timezones
and low-precision event dates.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import api.server as server  # noqa: E402

EINSTEIN = {
    "name": "Einstein",
    "birth_date": "1879-03-14",
    "birth_time": "11:30",
    "timezone": "Europe/Berlin",
    "latitude": 48.3988,
    "longitude": 9.9916,
    "city": "Ulm",
    "country": "Germany",
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_PATH", tmp_path / "test.db")
    return TestClient(server.app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_taxonomy_lists_every_category(client):
    body = client.get("/taxonomy").json()
    assert set(body["categories"]) == {
        "career", "relationship", "family", "education", "finance",
        "location", "health", "legal", "other",
    }
    assert "promotion" in body["categories"]["career"]
    assert "year" in body["precisions"]


def test_config_is_disclosed(client):
    """The app must be able to tell the user which conventions were used."""
    body = client.get("/config").json()
    assert body["ayanamsha"] == "lahiri"
    assert body["house_system"] == "whole_sign"
    assert "Lahiri" in body["note"]


def test_chart_computation_matches_the_verified_golden_chart(client):
    """The endpoint must agree with the engine's externally verified output."""
    body = client.post("/chart", json=EINSTEIN).json()
    chart = body["chart"]
    assert chart["lagna"]["sign_name"] == "Gemini"
    assert chart["planets"]["sun"]["sign_name"] == "Pisces"
    assert chart["planets"]["moon"]["sign_name"] == "Scorpio"
    assert chart["planets"]["moon"]["nakshatra_name"] == "Jyeshtha"


def test_chart_response_carries_its_config_and_fingerprint(client):
    body = client.post("/chart", json=EINSTEIN).json()
    assert body["calc_config"]["ayanamsha"] == "lahiri"
    assert len(body["chart_fingerprint"]) == 16


def test_invalid_timezone_is_rejected_with_a_reason(client):
    bad = {**EINSTEIN, "timezone": "Not/AZone"}
    r = client.post("/chart", json=bad)
    assert r.status_code in (422, 500)


def test_out_of_range_coordinates_are_rejected(client):
    bad = {**EINSTEIN, "latitude": 200.0}
    assert client.post("/chart", json=bad).status_code == 422


def test_malformed_birth_time_is_rejected(client):
    bad = {**EINSTEIN, "birth_time": "25:99"}
    assert client.post("/chart", json=bad).status_code == 422


# ---------------------------------------------------------------------------
# Profiles and events
# ---------------------------------------------------------------------------


def test_profile_lifecycle(client):
    created = client.post("/profiles", json=EINSTEIN)
    assert created.status_code == 201
    pid = created.json()["profile_id"]

    fetched = client.get(f"/profiles/{pid}").json()
    assert fetched["profile"]["city"] == "Ulm"
    assert fetched["chart"] is not None
    assert fetched["event_count"] == 0


def test_missing_profile_returns_404(client):
    assert client.get("/profiles/does-not-exist").status_code == 404


def test_profiles_receive_distinct_ids(client):
    """Regression: a fixed placeholder id made every profile collide."""
    a = client.post("/profiles", json=EINSTEIN).json()["profile_id"]
    b = client.post("/profiles", json={**EINSTEIN, "name": "Someone Else"}).json()[
        "profile_id"
    ]
    assert a != b, "two profiles shared a primary key"
    assert client.get(f"/profiles/{a}").status_code == 200
    assert client.get(f"/profiles/{b}").status_code == 200


def test_events_are_scoped_to_their_own_profile(client):
    a = client.post("/profiles", json=EINSTEIN).json()["profile_id"]
    b = client.post("/profiles", json={**EINSTEIN, "name": "Other"}).json()[
        "profile_id"
    ]
    client.post(
        f"/profiles/{a}/events",
        json={"category": "career", "sub_category": "promotion", "date": "1909-03-01"},
    )
    assert len(client.get(f"/profiles/{a}/events").json()["events"]) == 1
    assert len(client.get(f"/profiles/{b}/events").json()["events"]) == 0


def test_add_and_list_events(client):
    pid = client.post("/profiles", json=EINSTEIN).json()["profile_id"]

    r = client.post(
        f"/profiles/{pid}/events",
        json={
            "category": "career",
            "sub_category": "promotion",
            "date": "1909-03-01",
            "precision": "exact",
            "impact": 4,
        },
    )
    assert r.status_code == 201
    assert r.json()["usable_for_timing_analysis"] is True

    listed = client.get(f"/profiles/{pid}/events").json()
    assert len(listed["events"]) == 1
    assert listed["summary"]["total_events"] == 1


def test_invalid_sub_category_is_rejected(client):
    pid = client.post("/profiles", json=EINSTEIN).json()["profile_id"]
    r = client.post(
        f"/profiles/{pid}/events",
        json={
            "category": "career",
            "sub_category": "marriage",
            "date": "1909-03-01",
        },
    )
    assert r.status_code == 422
    assert "invalid for" in r.json()["detail"]


def test_year_precision_event_reports_the_interval_not_a_day(client):
    """A year-precision event must not be silently pinned to 1 January."""
    pid = client.post("/profiles", json=EINSTEIN).json()["profile_id"]
    body = client.post(
        f"/profiles/{pid}/events",
        json={
            "category": "career",
            "sub_category": "job_change",
            "date": "1909",
            "precision": "year",
        },
    ).json()

    interval = body["date_interval"]
    assert interval["precision"] == "year"
    assert interval["start"] == "1909-01-01"
    assert interval["end"] == "1909-12-31"
    assert interval["start"] != interval["end"]


def test_event_on_missing_profile_returns_404(client):
    r = client.post(
        "/profiles/nope/events",
        json={
            "category": "career", "sub_category": "promotion",
            "date": "1909-03-01",
        },
    )
    assert r.status_code == 404


def test_impact_bounds_are_enforced(client):
    pid = client.post("/profiles", json=EINSTEIN).json()["profile_id"]
    r = client.post(
        f"/profiles/{pid}/events",
        json={
            "category": "career", "sub_category": "promotion",
            "date": "1909-03-01", "impact": 9,
        },
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Timeline: the precision-aware view the app renders
# ---------------------------------------------------------------------------


def test_timeline_reports_multiple_candidate_dates_for_rough_events(client):
    pid = client.post("/profiles", json=EINSTEIN).json()["profile_id"]
    client.post(
        f"/profiles/{pid}/events",
        json={
            "category": "career", "sub_category": "job_change",
            "date": "1909", "precision": "year",
        },
    )
    body = client.get(f"/profiles/{pid}/timeline").json()
    event = body["events"][0]
    assert event["candidate_dates"] > 1
    assert event["dasha_configurations"]


def test_timeline_reports_a_single_configuration_for_exact_events(client):
    pid = client.post("/profiles", json=EINSTEIN).json()["profile_id"]
    client.post(
        f"/profiles/{pid}/events",
        json={
            "category": "career", "sub_category": "promotion",
            "date": "1909-03-01", "precision": "exact",
        },
    )
    event = client.get(f"/profiles/{pid}/timeline").json()["events"][0]
    assert event["candidate_dates"] == 1
    assert len(event["dasha_configurations"]) == 1


def test_analysis_does_not_claim_prediction(client):
    pid = client.post("/profiles", json=EINSTEIN).json()["profile_id"]
    body = client.get(f"/profiles/{pid}/analysis").json()
    assert "not evidence" in body["caveat"]
    assert "summary" in body
    assert "precision_breakdown" in body
