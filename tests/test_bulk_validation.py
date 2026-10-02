"""
Bulk validation over real Rodden-AA birth records.

These tests use real, certificate-sourced birth data rather than synthetic
input, so they catch impossible states that hand-written fixtures miss.

They verify ROBUSTNESS, not correctness: passing means the engine produced
structurally valid output for every record, not that the output matches an
independent implementation. See tests/test_external_verification.py for the
correctness evidence.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.vedic_layer import build_vedic_chart  # noqa: E402
from scripts.bulk_validate import (  # noqa: E402
    sweep,
    validate_chart,
)

DATA = ROOT / "data" / "aa_birth_dataset.csv"

pytestmark = pytest.mark.skipif(
    not DATA.exists(),
    reason="run scripts/build_aa_dataset.py first to fetch the AA birth records",
)


def _utc_instant(row: dict) -> datetime:
    """Local wall time + explicit UTC offset -> UTC datetime."""
    naive = datetime.strptime(f"{row['date']} {row['time']}", "%Y-%m-%d %H:%M")
    sign = 1 if row["tz"].startswith("+") else -1
    hours, minutes = row["tz"][1:].split(":")
    return naive - timedelta(hours=sign * int(hours), minutes=sign * int(minutes))


def test_dataset_is_present_and_rodden_aa():
    import csv

    with DATA.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) >= 100
    assert all(r["rodden"] == "AA" for r in rows), "all records must be Rodden AA"
    assert all(r["date"][:4].isdigit() for r in rows)


def test_bulk_sweep_finds_no_invariant_violations():
    """Every sampled chart must be structurally valid."""
    result = sweep(limit=60)
    assert result["records"] == 60
    assert result["skipped"] == [], f"charts failed to build: {result['skipped'][:3]}"
    assert result["violations"] == {}, (
        "invariant violations found:\n"
        + "\n".join(
            f"  {k}: {v[:3]}" for k, v in result["violations"].items()
        )
    )


def test_validate_chart_detects_a_corrupted_chart():
    """The validator must actually catch problems, or it is worthless."""
    chart = build_vedic_chart(
        datetime(1980, 5, 5, 10, 0), "UTC", 51.5, -0.12
    )
    assert validate_chart(chart, "clean") == []

    chart.lagna_sign = 99
    problems = validate_chart(chart, "corrupt")
    assert any("lagna_sign out of range" in p for p in problems)

    chart.lagna_sign = 0
    chart.planets["sun"].nakshatra = 44
    assert any("nakshatra 44 out of range" in p for p in validate_chart(chart, "c2"))

    chart.planets["sun"].nakshatra = 1
    chart.planets["sun"].retrograde = not chart.planets["sun"].retrograde
    assert any("retrograde=" in p for p in validate_chart(chart, "c3"))

    chart.planets["sun"].retrograde = chart.planets["sun"].speed < 0
    chart.planets["sun"].combust = True
    assert any("must never be combust" in p for p in validate_chart(chart, "c4"))


def test_ignoring_utc_offsets_flips_many_lagna_signs():
    """Documents how damaging a timezone error is for whole-sign houses.

    A one-hour mistake never raises. It just yields a plausible chart with
    the wrong ascendant, which would then propagate silently into every
    feature and statistic derived from it.
    """
    import csv

    with DATA.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    flipped = 0
    considered = 0
    for row in rows[:25]:
        if row["tz"] in ("+00:00", "-00:00"):
            continue
        considered += 1
        lat, lon = float(row["lat"]), float(row["lon"])
        correct = build_vedic_chart(_utc_instant(row), "UTC", lat, lon)
        naive = datetime.strptime(
            f"{row['date']} {row['time']}", "%Y-%m-%d %H:%M"
        )
        wrong = build_vedic_chart(naive, "UTC", lat, lon)
        if correct.lagna_sign != wrong.lagna_sign:
            flipped += 1

    assert considered > 0
    # Not asserting a specific count, but this must be a substantial
    # fraction: if it were rare, the risk would be overstated.
    assert flipped / considered > 0.3, (
        f"only {flipped}/{considered} flipped; the offset risk may be "
        "overstated in the documentation"
    )
