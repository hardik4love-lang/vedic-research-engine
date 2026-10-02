"""
Join Rodden-AA birth records to real marriage/divorce events.

This is the first point at which the engine runs against real documented
life events rather than synthetic fixtures.

Two properties of the source data matter and are handled explicitly:

1. DATE PRECISION IS MIXED. Some records give "1990" and others
   "31/08/1921". Everything is mapped onto the DatePrecision enum rather
   than being coerced to a day, because a marriage in an unknown month of a
   known year is not an event on 1 January.

2. SENTINEL VALUES ARE NOT EMPTY. divorceDate arrives as "", "N/A",
   "Not Applicable" and "null". Treating any of those as a real date would
   place a divorce in year 1.

Only records with dataCredibility "high" are kept by default, so that the
provenance quality of the events is at least as good as the births.
"""

import csv
import json
import sys
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BIRTH_API = (
    "https://datasets-server.huggingface.co/rows?dataset="
    "vedastro-org/15000-Famous-People-Birth-Date-Location"
    "&config=default&split=train&offset={offset}&length={length}"
)
MARRIAGE_API = (
    "https://datasets-server.huggingface.co/rows?dataset="
    "vedastro-org/15000-Famous-People-Marriage-Divorce-Info"
    "&config=default&split=train&offset={offset}&length={length}"
)

OUT = ROOT / "data" / "aa_profiles_with_events.csv"
SENTINELS = {"", "n/a", "na", "not applicable", "null", "none", "unknown", "-"}


def fetch(api: str, offset: int, length: int = 100) -> list[dict]:
    with urllib.request.urlopen(api.format(offset=offset, length=length),
                                timeout=60) as resp:
        payload = json.load(resp)
    return [r["row"] for r in payload.get("rows", [])]


def parse_stime(raw: str) -> dict | None:
    try:
        blob = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    std = blob.get("StdTime")
    loc = blob.get("Location") or {}
    if not std or loc.get("Latitude") is None:
        return None
    head, _, tail = std.partition(" ")
    date_part, _, tz = tail.rpartition(" ")
    date_part = date_part.strip()
    if "/" not in date_part:
        return None
    day, month, year = date_part.split("/")
    if len(year) != 4:
        return None
    return {
        "time": head.strip(), "date": f"{year}-{month}-{day}", "tz": tz.strip(),
        "lat": loc["Latitude"], "lon": loc["Longitude"],
        "place": loc.get("Name", ""),
    }


def parse_event_date(raw: str) -> tuple[str, str] | None:
    """Return (iso_date, precision) or None for a sentinel/garbage value.

    "1990"           -> ("1990-01-01", "year")
    "31/08/1921"     -> ("1921-08-31", "exact")
    ""/N/A/null      -> None
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if s.lower() in SENTINELS:
        return None
    if "/" in s:
        parts = s.split("/")
        if len(parts) != 3:
            return None
        day, month, year = parts
        if not (day.isdigit() and month.isdigit() and year.isdigit()):
            return None
        if len(year) != 4:
            return None
        try:
            date(int(year), int(month), int(day))
        except ValueError:
            return None
        return f"{year}-{int(month):02d}-{int(day):02d}", "exact"
    if s.isdigit() and len(s) == 4:
        return f"{s}-01-01", "year"
    return None


def main(max_people: int = 600) -> None:
    births: dict[str, dict] = {}
    offset = 0
    while offset < max_people * 2:
        rows = fetch(BIRTH_API, offset)
        if not rows:
            break
        for row in rows:
            parsed = parse_stime(row.get("BirthTime", ""))
            if parsed:
                births[row["RowKey"]] = {**parsed, "name": row.get("Name", "")}
        offset += 100
        if len(births) >= max_people:
            break

    events: dict[str, list[dict]] = {}
    offset = 0
    while offset < max_people * 2:
        rows = fetch(MARRIAGE_API, offset)
        if not rows:
            break
        for row in rows:
            try:
                blob = json.loads(row.get("Info") or "{}")
                marriages = blob.get("marriages") or []
            except (TypeError, json.JSONDecodeError):
                continue
            # The key lives in PartitionKey; RowKey is null throughout.
            key = row.get("PartitionKey") or row.get("RowKey")
            if key and marriages:
                events[key] = marriages
        offset += 100
        if len(events) >= max_people:
            break

    stats = Counter()
    records: list[list] = []
    for key, person in births.items():
        marriages = events.get(key)
        if not marriages:
            stats["no_marriage_data"] += 1
            continue
        birth_year = int(person["date"][:4])
        kept = 0
        for m in marriages:
            if str(m.get("dataCredibility", "")).lower() != "high":
                stats["credibility_not_high"] += 1
                continue
            married = parse_event_date(m.get("marriageDate", ""))
            if not married:
                stats["marriage_date_unparseable"] += 1
                continue
            if int(married[0][:4]) < birth_year + 14:
                stats["marriage_before_age_14"] += 1
                continue
            divorced_raw = m.get("divorceDate", "")
            divorced = parse_event_date(divorced_raw)
            records.append([
                person["name"], key, person["date"], person["time"],
                person["tz"], person["lat"], person["lon"], person["place"],
                "AA", married[0], married[1],
                divorced[0] if divorced else "", divorced[1] if divorced else "",
                str(m.get("outcome", "")).strip(), m.get("type", ""),
                m.get("spouse", ""),
            ])
            stats["kept"] += 1
            kept += 1
        if kept == 0:
            stats["profile_no_usable_events"] += 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([
            "name", "row_key", "birth_date", "birth_time", "birth_tz",
            "lat", "lon", "place", "rodden",
            "marriage_date", "marriage_precision",
            "divorce_date", "divorce_precision",
            "outcome", "marriage_type", "spouse",
        ])
        w.writerows(records)

    print(f"births fetched      : {len(births)}")
    print(f"marriage rows seen  : {len(events)}")
    print(f"event records kept  : {len(records)}")
    print(f"filter stats        : {dict(stats)}")
    prec = Counter(r[10] for r in records)
    print(f"marriage precision  : {dict(prec)}")
    print(f"divorces            : {sum(1 for r in records if r[11])}")
    print(f"profiles with >=1   : {len({r[1] for r in records})}")
    print(f"written to          : {OUT}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 600)
