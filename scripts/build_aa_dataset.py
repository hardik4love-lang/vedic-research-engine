"""
Build a Rodden-AA birth dataset from the public VedAstro collection.

Rodden AA means the birth time comes from a birth certificate or official
record, not a rectified or recalled time. That is the minimum quality needed
for a golden chart dataset, and the reason Gandhi (rectified) and
Krishnamurti (disputed date) were excluded earlier.

Source: https://huggingface.co/datasets/vedastro-org/15000-Famous-People-Birth-Date-Location
(see the project's own provenance note: the source publishes it for astrological
research).

NOTE ON SCOPE. This produces verified birth INPUTS. It does not by itself
verify computed outputs; cross-checking signs against an independent
implementation is a separate step. Keeping the two apart is deliberate.
"""

import csv
import json
import sys
import urllib.request
from pathlib import Path

API = (
    "https://datasets-server.huggingface.co/rows?dataset="
    "vedastro-org/15000-Famous-People-Birth-Date-Location"
    "&config=default&split=train&offset={offset}&length={length}"
)

OUT = Path(__file__).resolve().parent.parent / "data" / "aa_birth_dataset.csv"


def fetch_page(offset: int, length: int = 100) -> list[dict]:
    url = API.format(offset=offset, length=length)
    with urllib.request.urlopen(url, timeout=60) as resp:
        payload = json.load(resp)
    return [r["row"] for r in payload.get("rows", [])]


def parse_birth_time(raw: str) -> dict | None:
    """Parse the StdTime/Location blob into plain fields."""
    try:
        blob = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    std = blob.get("StdTime")
    loc = blob.get("Location") or {}
    if not std or loc.get("Latitude") is None:
        return None

    # Format: "HH:MM DD/MM/YYYY +ZZ:00"
    head, _, tail = std.partition(" ")
    date_part, _, tz_part = tail.rpartition(" ")
    date_part = date_part.strip()
    if "/" not in date_part:
        return None
    day, month, year = date_part.split("/")
    if len(year) != 4:
        return None
    return {
        "time": head.strip(),
        "date": f"{year}-{month}-{day}",
        "tz": tz_part.strip(),
        "lat": loc["Latitude"],
        "lon": loc["Longitude"],
        "place": loc.get("Name", ""),
    }


def main(target_rows: int = 400) -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    offset = 0

    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["name", "date", "time", "tz", "lat", "lon", "place", "gender",
             "rodden", "source"]
        )

        while written < target_rows:
            rows = fetch_page(offset)
            if not rows:
                break
            for row in rows:
                parsed = parse_birth_time(row.get("BirthTime", ""))
                if not parsed:
                    continue
                notes = row.get("Notes", "") or ""
                rodden = "AA" if "AA" in notes else "?"
                writer.writerow([
                    row.get("Name", ""),
                    parsed["date"],
                    parsed["time"],
                    parsed["tz"],
                    parsed["lat"],
                    parsed["lon"],
                    parsed["place"],
                    row.get("Gender", ""),
                    rodden,
                    "vedastro-org/15000-Famous-People-Birth-Date-Location",
                ])
                written += 1
                if written >= target_rows:
                    break
            offset += 100

    print(f"wrote {written} records to {OUT}")
    return written


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    main(count)
