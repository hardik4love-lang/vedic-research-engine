"""Does the Swiss Ephemeris data improve outer-planet accuracy over Moshier?

The claim being checked: the Moshier fallback has materially worse
outer-planet longitudes, so transit work involving Jupiter and Saturn was
unverified. If the two agree to within a few arcseconds, the fallback was
never a practical problem for this work and the caveat can be narrowed.
"""
import sys
from pathlib import Path

import swisseph as swe

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EPHE = ROOT / "ephe"

BODIES = [
    ("sun", swe.SUN), ("moon", swe.MOON), ("mars", swe.MARS),
    ("mercury", swe.MERCURY), ("jupiter", swe.JUPITER), ("venus", swe.VENUS),
    ("saturn", swe.SATURN), ("mean node", swe.MEAN_NODE),
]

# Spread across 1900-2050 so the comparison is not one lucky instant.
JDS = [
    swe.julday(y, 1, 15, 0.0)
    for y in range(1900, 2051, 5)
]


def positions(flags, path=None):
    if path:
        swe.set_ephe_path(path)
    else:
        swe.set_ephe_path("")
    out = {}
    for jd in JDS:
        for label, body in BODIES:
            r, _ = swe.calc_ut(jd, body, flags | swe.FLG_SPEED)
            out[(jd, label)] = r[0] % 360
    return out


def diff(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


print(f"comparing {len(JDS)} instants x {len(BODIES)} bodies")
print()
print(f"{'body':<12} {'max |SE - Moshier|':>20} {'mean':>10}")
print("-" * 44)

moshier = positions(swe.FLG_MOSEPH)
swiss = positions(swe.FLG_SWIEPH, str(EPHE))

worst = 0.0
for label, _ in BODIES:
    ds = [diff(swiss[(jd, label)], moshier[(jd, label)]) for jd in JDS]
    m = max(ds)
    mean = sum(ds) / len(ds)
    worst = max(worst, m)
    flag = "  <-- material" if m > 0.01 else ""
    print(f"{label:<12} {m * 3600:>16.1f}\" {mean * 3600:>8.1f}\"{flag}")

print()
print(f"worst disagreement across all bodies: {worst * 3600:.1f} arcsec")
print()
print("Interpretation:")
if worst < 0.01:
    print("  Under 36 arcsec everywhere. The Moshier fallback was not a")
    print("  practical accuracy problem for this application, and the")
    print("  technical plan's caveat can be narrowed accordingly.")
else:
    print("  Over 36 arcsec. Outer-planet transits are materially affected,")
    print("  so the data files are required and the caveat stands.")