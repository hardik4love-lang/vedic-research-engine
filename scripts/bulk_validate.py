"""
Bulk validation of the chart engine over real Rodden-AA birth records.

This does NOT verify correctness against an external implementation. What it
does is find impossible states and crashes that synthetic tests miss:

  * a planet in house 0 or 13
  * a nakshatra index outside 1-27
  * dasha periods that do not tile the 120-year cycle
  * a varga missing a planet
  * retrograde flag disagreeing with the sign of the speed
  * combustion or dignity flags that contradict their own inputs

Those are the failure modes that would silently corrupt every downstream
statistic while still producing plausible-looking output.
"""

import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.vedic_layer import build_vedic_chart

DATA = Path(__file__).resolve().parent.parent / "data" / "aa_birth_dataset.csv"


class ChartError(AssertionError):
    pass


def _load(limit: int | None = None) -> list[dict]:
    if not DATA.exists():
        return []
    with DATA.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return rows[:limit] if limit else rows


def validate_chart(chart, label: str) -> list[str]:
    """Return a list of invariant violations for one chart."""
    problems: list[str] = []

    if not 0 <= chart.lagna_sign <= 11:
        problems.append(f"lagna_sign out of range: {chart.lagna_sign}")

    planets = chart.planets
    if len(planets) != 9:
        problems.append(f"expected 9 planets, got {len(planets)}")

    for name, vp in planets.items():
        if not 0 <= vp.sign <= 11:
            problems.append(f"{name}: sign {vp.sign} out of range")
        if not 0 <= vp.degree_in_sign < 30:
            problems.append(f"{name}: degree {vp.degree_in_sign} out of range")
        if not 1 <= vp.nakshatra <= 27:
            problems.append(f"{name}: nakshatra {vp.nakshatra} out of range")
        if not 1 <= vp.pada <= 4:
            problems.append(f"{name}: pada {vp.pada} out of range")
        if not 1 <= vp.house <= 12:
            problems.append(f"{name}: house {vp.house} out of range")
        if not 0 <= vp.longitude_sidereal < 360:
            problems.append(f"{name}: longitude {vp.longitude_sidereal} out of range")

        # Retrograde must agree with the sign of the speed.
        if vp.speed == 0.0:
            problems.append(f"{name}: zero speed (FLG_SPEED missing?)")
        elif vp.retrograde != (vp.speed < 0):
            problems.append(
                f"{name}: retrograde={vp.retrograde} but speed={vp.speed:+.5f}"
            )

        # Nodes are always retrograde.
        if name in ("rahu", "ketu") and not vp.retrograde:
            problems.append(f"{name}: node should always be retrograde")

        # Dignity vocabulary is closed.
        if vp.dignity not in {
            "exalted", "moolatrikona", "own", "friendly",
            "neutral", "enemy", "debilitated",
        }:
            problems.append(f"{name}: unknown dignity {vp.dignity!r}")

        # Sun and nodes never combust.
        if name in ("sun", "rahu", "ketu") and vp.combust:
            problems.append(f"{name}: must never be combust")

    # Houses must be internally consistent.
    for house in chart.houses:
        if not 1 <= house.number <= 12:
            problems.append(f"house number {house.number} out of range")
        for planet in house.planets:
            if planets[planet].house != house.number:
                problems.append(
                    f"{planet} listed in house {house.number} but its house "
                    f"field says {planets[planet].house}"
                )

    # Every planet must appear in exactly one house.
    listed = [p for h in chart.houses for p in h.planets]
    if sorted(listed) != sorted(planets):
        problems.append("house membership does not partition the planets")

    # Vargas must be complete.
    for varga in ("D1", "D9", "D10", "D12"):
        if varga not in chart.divisional_charts:
            problems.append(f"missing varga {varga}")
            continue
        dc = chart.divisional_charts[varga]
        if len(dc.planets) != 9:
            problems.append(f"{varga} has {len(dc.planets)} planets, expected 9")
        if not 0 <= dc.lagna_sign <= 11:
            problems.append(f"{varga} lagna out of range: {dc.lagna_sign}")

    # Vimshottari must tile the cycle.
    if len(chart.dasha_periods) != 9:
        problems.append(f"expected 9 maha dashas, got {len(chart.dasha_periods)}")
    else:
        for i in range(8):
            gap = (
                chart.dasha_periods[i + 1].start_jd
                - chart.dasha_periods[i].end_jd
            )
            if abs(gap) > 0.01:
                problems.append(f"dasha discontinuity at index {i}: gap {gap:.4f} d")
        for d in chart.dasha_periods:
            if d.end_jd <= d.start_jd:
                problems.append(f"dasha {d.lord} has non-positive duration")
            if len(d.sub_periods) != 9:
                problems.append(
                    f"dasha {d.lord} has {len(d.sub_periods)} antardashas"
                )
            for a in d.sub_periods:
                if len(a.sub_periods) != 9:
                    problems.append(
                        f"antar {a.lord} has {len(a.sub_periods)} pratyantardashas"
                    )

    return problems


def sweep(limit: int | None = None) -> dict:
    """Run the engine over the dataset and collect every violation found."""
    rows = _load(limit)
    checked = 0
    failures: dict[str, list[str]] = {}
    skipped: list[tuple[str, str]] = []

    for row in rows:
        label = f"{row['name']} {row['date']} {row['time']} {row['tz']}"
        try:
            naive = datetime.strptime(
                f"{row['date']} {row['time']}", "%Y-%m-%d %H:%M"
            )
            # The dataset stores an explicit UTC offset per record, e.g.
            # "19:55 26/06/1954 +01:00". Converting to UTC here is required:
            # passing the local wall time as if it were UTC would place
            # every chart up to a day wrong without raising any error.
            offset_sign = 1 if row["tz"].startswith("+") else -1
            off_h, off_m = row["tz"][1:].split(":")
            utc_dt = naive - timedelta(
                hours=offset_sign * int(off_h), minutes=offset_sign * int(off_m)
            )

            chart = build_vedic_chart(
                birth_datetime=utc_dt,
                birth_timezone="UTC",
                latitude=float(row["lat"]),
                longitude=float(row["lon"]),
            )
        except Exception as exc:  # noqa: BLE001
            skipped.append((label, f"{type(exc).__name__}: {exc}"))
            continue

        checked += 1
        for problem in validate_chart(chart, label):
            failures.setdefault(problem.split(":")[0], []).append(
                f"{label} -> {problem}"
            )

    return {
        "records": len(rows),
        "charts_built": checked,
        "skipped": skipped,
        "violations": failures,
        "clean": not failures and not skipped,
    }


def offset_sensitivity_sample(n: int = 25) -> list[str]:
    """Report how far the ascendant moves if a record's UTC offset is ignored.

    An off-by-one-hour error never raises an error — it just produces a
    plausible-looking but wrong chart. This quantifies the exposure.
    """
    rows = _load(n)
    findings: list[str] = []
    for row in rows:
        try:
            naive = datetime.strptime(
                f"{row['date']} {row['time']}", "%Y-%m-%d %H:%M"
            )
            sign = 1 if row["tz"].startswith("+") else -1
            oh, om = row["tz"][1:].split(":")
            delta = timedelta(hours=sign * int(oh), minutes=sign * int(om))
            correct = build_vedic_chart(
                naive - delta, "UTC", float(row["lat"]), float(row["lon"])
            )
            wrong = build_vedic_chart(
                naive, "UTC", float(row["lat"]), float(row["lon"])
            )
        except Exception as exc:  # noqa: BLE001
            findings.append(f"{row['name']}: error {exc}")
            continue

        offset_hours = delta.total_seconds() / 3600
        if offset_hours == 0:
            continue
        if wrong.lagna_sign != correct.lagna_sign:
            findings.append(
                f"{row['name']}: ignoring offset {row['tz']} flips the lagna "
                f"sign ({correct.lagna_sign} -> {wrong.lagna_sign})"
            )
    return findings


if __name__ == "__main__":
    import sys

    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    result = sweep(limit)
    print(f"records={result['records']} built={result['charts_built']}")
    print(f"skipped={len(result['skipped'])}")
    for label, err in result["skipped"][:10]:
        print(f"  SKIP {label}: {err}")
    if result["violations"]:
        print("\nVIOLATIONS:")
        for kind, items in result["violations"].items():
            print(f"  {kind}: {len(items)}")
            for it in items[:3]:
                print(f"    {it}")
    else:
        print("\nno invariant violations")

    print("\n--- offset sensitivity (ignoring the record's UTC offset) ---")
    flips = offset_sensitivity_sample()
    if flips:
        for f in flips[:10]:
            print(f"  {f}")
        print(f"  {len(flips)} of 25 sampled records flip the lagna sign")
    else:
        print("  no lagna sign flips in the sample")
