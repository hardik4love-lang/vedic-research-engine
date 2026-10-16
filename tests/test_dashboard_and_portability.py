"""Dashboard, export/import, and auth."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import api.server as server  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(server, "EVALUATION_PATH", tmp_path / "eval.json")
    return TestClient(server.app)


BIRTH = {"name": "Einstein", "birth_date": "1879-03-14", "birth_time": "11:30",
         "city": "Ulm"}


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def test_dashboard_says_so_when_nothing_measured(client):
    body = client.get("/dashboard").json()
    assert body["categories_analysed"] == 0
    assert "No evaluation on record" in body["verdict"]
    assert body["disclaimer"], "must not imply figures were computed"


def test_dashboard_serves_persisted_evaluation(client):
    server.EVALUATION_PATH.write_text('{"verdict":"x","categories":[]}')
    assert client.get("/dashboard").json()["verdict"] == "x"


def test_persisted_dashboard_is_a_real_null_result(client):
    import json

    from scripts.persist_evaluation import PERF  # noqa: F401

    # The committed evaluation must exist and must report zero support.
    path = ROOT / "data" / "evaluation.json"
    if not path.exists():
        pytest.skip("evaluation.json not generated")
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["categories_analysed"] > 0
    assert body["categories_supported"] == 0
    assert "No association detected" in body["verdict"]


# ---------------------------------------------------------------------------
# Dashboard engine
# ---------------------------------------------------------------------------


def test_significant_requires_both_methods_and_an_excluding_ci():
    from engine.dashboard import CategoryPerformance

    weak = CategoryPerformance(
        category="x", true_positives=10, false_positives=5,
        true_negatives=10, false_negatives=10,
        lift=1.5, lift_low=0.9, lift_high=2.1,
        bootstrap_p=0.001, permutation_p=0.2, naive_p=1e-9, support=35,
    )
    assert weak.significant is False, "permutation disagrees"

    ci_overlaps = CategoryPerformance(
        category="y", true_positives=10, false_positives=5,
        true_negatives=10, false_negatives=10,
        lift=1.5, lift_low=0.9, lift_high=2.1,
        bootstrap_p=0.01, permutation_p=0.01, naive_p=1e-9, support=35,
    )
    assert ci_overlaps.significant is False, "CI includes 1.0"

    good = CategoryPerformance(
        category="z", true_positives=30, false_positives=5,
        true_negatives=30, false_negatives=10,
        lift=2.0, lift_low=1.4, lift_high=2.8,
        bootstrap_p=0.001, permutation_p=0.002, naive_p=1e-9, support=75,
    )
    assert good.significant is True


def test_confounded_is_never_significant():
    from engine.dashboard import CategoryPerformance

    c = CategoryPerformance(
        category="x", true_positives=30, false_positives=5,
        true_negatives=30, false_negatives=10,
        lift=2.0, lift_low=1.4, lift_high=2.8,
        bootstrap_p=0.001, permutation_p=0.002, naive_p=1e-9, support=75,
        confounded=True, confound_notes=["dasha duration uncontrolled"],
    )
    assert c.significant is False
    assert c.evidence == "not interpretable"


def test_dashboard_verdict_is_a_null_not_an_absence_claim():
    from engine.dashboard import CategoryPerformance, build_dashboard

    cats = [CategoryPerformance(
        category="dasha=rahu", true_positives=0, false_positives=0,
        true_negatives=0, false_negatives=0,
        lift=1.04, lift_low=0.8, lift_high=1.34,
        bootstrap_p=0.8, permutation_p=0.01, naive_p=0.7, support=332,
    )]
    body = build_dashboard(cats, "s")
    assert body["categories_supported"] == 0
    assert "not evidence that the relationship is absent" in body["verdict"]


def test_calibration_bins_are_computed():
    from engine.dashboard import calibration_bins, expected_calibration_error

    preds = [(0.1, False)] * 20 + [(0.9, True)] * 20
    bins = calibration_bins(preds, bins=5)
    assert len(bins) == 5
    populated = [b for b in bins if b["n"]]
    assert populated
    ece = expected_calibration_error(bins)
    assert 0.0 <= ece <= 1.0


# ---------------------------------------------------------------------------
# Export / import
# ---------------------------------------------------------------------------


def test_export_import_roundtrip(client, monkeypatch):
    pid = client.post("/profiles", json=BIRTH).json()["profile_id"]
    client.post(f"/profiles/{pid}/events", json={
        "category": "career", "sub_category": "promotion",
        "date": "1909-03-01", "precision": "exact", "impact": 4,
    })

    exported = client.get("/export").json()
    assert exported["format"] == "vedic-export/1"
    assert exported["summary"]["profile_count"] == 1
    assert exported["summary"]["event_count"] == 1
    prof = exported["profiles"][0]
    assert prof["chart_fingerprint"], "fingerprint must travel with the data"
    assert prof["calc_config"]["ayanamsha"] == "lahiri"
    assert prof["events"][0]["precision"] == "exact"
    assert prof["events"][0]["start_lower"] == "1909-03-01"

    # A fresh instance must reconstruct the same profile and events.

    monkeypatch.setattr(server, "DB_PATH", ROOT / "_tmp_fresh.db")
    other = TestClient(server.app)
    assert other.post("/import", json=exported).json()["created"] == 1
    got_events = other.get(f"/profiles/{pid}/events").json()["events"]
    assert len(got_events) == 1
    assert got_events[0]["category"] == "career"
    (ROOT / "_tmp_fresh.db").unlink(missing_ok=True)


def test_import_is_idempotent(client, tmp_path, monkeypatch):
    pid = client.post("/profiles", json=BIRTH).json()["profile_id"]
    client.post(f"/profiles/{pid}/events", json={
        "category": "career", "sub_category": "promotion",
        "date": "1909-03-01", "precision": "exact",
    })
    exported = client.get("/export").json()

    again = client.post("/import", json=exported).json()
    assert again["created"] == 0
    assert again["skipped_existing"] == 1
    assert len(client.get(f"/profiles/{pid}/events").json()["events"]) == 1


def test_import_preserves_precision_interval(client, tmp_path, monkeypatch):
    pid = client.post("/profiles", json=BIRTH).json()["profile_id"]
    client.post(f"/profiles/{pid}/events", json={
        "category": "career", "sub_category": "job_change",
        "date": "1909", "precision": "year",
    })
    exported = client.get("/export").json()
    ev = exported["profiles"][0]["events"][0]
    assert ev["start_lower"] == "1909-01-01"
    assert ev["start_upper"] == "1909-12-31"

    # Round-trip through a fresh database.
    fresh = tmp_path / "fresh.db"
    monkeypatch.setattr(server, "DB_PATH", fresh)
    other = TestClient(server.app)
    other.post("/import", json=exported)
    pid2 = exported["profiles"][0]["profile_id"]
    got = other.get(f"/profiles/{pid2}/events").json()["events"][0]
    assert got["start"]["start"] == "1909-01-01"
    assert got["start"]["end"] == "1909-12-31"
    assert got["start"]["precision"] == "year"


def test_import_rejects_unknown_format(client):
    r = client.post("/import", json={"format": "something-else", "profiles": []})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_open_by_default(client):
    body = client.get("/health").json()
    assert body["auth_required"] is False


def test_auth_gates_writes_when_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "API_KEY", "s3cret")
    monkeypatch.setattr(server, "AUTH_ENABLED", True)
    monkeypatch.setattr(server, "DB_PATH", tmp_path / "a.db")
    c = TestClient(server.app)

    # Reads stay open so the dashboard remains inspectable.
    assert c.get("/health").status_code == 200
    assert c.get("/dashboard").status_code == 200

    # Writes require the key.
    assert c.post("/profiles", json=BIRTH).status_code == 401

    ok = c.post("/profiles", json=BIRTH, headers={"x-api-key": "s3cret"})
    assert ok.status_code == 201


def test_auth_rejects_wrong_key(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "API_KEY", "s3cret")
    monkeypatch.setattr(server, "AUTH_ENABLED", True)
    monkeypatch.setattr(server, "DB_PATH", tmp_path / "b.db")
    c = TestClient(server.app)
    r = c.post("/profiles", json=BIRTH, headers={"x-api-key": "wrong"})
    assert r.status_code == 401


def test_health_reports_ephemeris_status(client):
    body = client.get("/health").json()
    assert "ephemeris" in body
    assert body["ephemeris"]["se_vs_moshier_max_arcsec"] <= 1.0