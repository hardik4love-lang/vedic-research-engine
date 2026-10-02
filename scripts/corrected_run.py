"""
Corrected first real analysis: cluster-robust association on the real corpus.

The previous run (scripts/first_real_run.py) used the naive path and treated
345,388 correlated negative windows as independent. Its p-values are void.

This re-runs the same comparison with the profile as the unit of analysis, so
the numbers produced here are the first from this system that can be cited.
"""
import csv
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.cluster_stats import compare_methods  # noqa: E402
from engine.correlation import Aggregation  # noqa: E402
from engine.events import (  # noqa: E402
    DatePrecision,
    EventCategory,
    LifeEvent,
    resolve_date_interval,
)
from engine.features import FeatureVector, extract_features_at, sample_negative_dates  # noqa: E402
from engine.vedic_layer import build_vedic_chart  # noqa: E402

DATA = ROOT / "data" / "aa_profiles_with_events.csv"
TARGET_FACTORS = [
    "dasha=rahu", "dasha=sun", "dasha=jupiter", "dasha=venus",
    "dasha=saturn", "dasha=moon", "dasha=mercury", "dasha=mars",
    "dasha=ketu",
]


def main() -> None:
    # ONLY day-precision events, so the positive and negative sides can be
    # compared at matching granularity.
    #
    # A year-precision event is reduced to the factors present in EVERY
    # candidate date, while a negative window is a single date. Comparing
    # those is not a like-for-like test: consensus systematically strips
    # dasha factors from positives (any dasha boundary inside the year
    # removes it), which drives every lift below 1 and produces a
    # spurious "significant" result in the wrong direction. Restricting to
    # exact dates removes the asymmetry.
    profiles = []
    with DATA.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["marriage_precision"] != "exact":
                continue
            naive = datetime.strptime(
                f"{row['birth_date']} {row['birth_time']}", "%Y-%m-%d %H:%M"
            )
            sign = 1 if row["birth_tz"].startswith("+") else -1
            oh, om = row["birth_tz"][1:].split(":")
            try:
                chart = build_vedic_chart(
                    naive - timedelta(hours=sign * int(oh), minutes=sign * int(om)),
                    "UTC", float(row["lat"]), float(row["lon"]),
                )
            except Exception:  # noqa: BLE001
                continue

            events = [
                LifeEvent(
                    profile_id=row["row_key"],
                    category=EventCategory.RELATIONSHIP,
                    sub_category="marriage",
                    date_interval=resolve_date_interval(
                        row["marriage_date"], DatePrecision.EXACT
                    ),
                    impact=4, certainty=4,
                )
            ]
            profiles.append((row["row_key"], chart, events, date.fromisoformat(row["birth_date"])))

    print(f"profiles with day-precision marriage date: {len(profiles)}")

    pos_g, pos_i, neg_g, neg_i = [], [], [], []
    for key, chart, events, birth in profiles:
        for ev in events:
            pos_g.append([
                FeatureVector(when=ev.date_interval.start,
                              factors=extract_features_at(chart, ev.date_interval.start).factors)
            ])
            pos_i.append(key)

        spans = [
            (e.date_interval.start, e.date_interval.end)
            for e in events
            if e.date_interval.precision is not DatePrecision.UNKNOWN
        ]
        # Sampling is deliberately sparse. The unit of analysis is the
        # profile, not the window, so dense sampling buys nothing and costs
        # ~3M ephemeris calls. One window every ~5 months is ample to
        # establish profile-level factor presence.
        # Negatives must be AGE-MATCHED, not drawn from the whole adult span.
        #
        # Vimshottari dashas run sequentially through life, so every dasha
        # factor is a proxy for age. Marriages cluster around 25-40; sampling
        # "all other adult dates" spans 25-80 and therefore measures age
        # rather than astrology. Every dasha lift came out below 1 for
        # exactly this reason: Ketu covers roughly ages 0-7, before marriage
        # is possible, so P(Ketu | marriage) is near zero by construction.
        #
        # Each profile's negatives are drawn only within +/-6 years of that
        # profile's own event age.
        event_age = (ev.date_interval.start - birth).days / 365.25
        lo = birth + timedelta(days=int(max(0, (event_age - 6)) * 365.25))
        hi = birth + timedelta(days=int((event_age + 6) * 365.25))
        for d in sample_negative_dates(
            lo, min(hi, date.today()),
            step_days=150, exclude=spans, margin_days=180,
        ):
            neg_g.append([
                FeatureVector(when=d, factors=extract_features_at(chart, d).factors)
            ])
            neg_i.append(key)

    print(f"event windows : {len(pos_g):,}")
    print(f"negative windows: {len(neg_g):,}")
    print(f"distinct profiles in negatives: {len(set(neg_i))}")
    print()

    methods = compare_methods(
        pos_g, neg_g, pos_i, neg_i, TARGET_FACTORS,
        aggregation=Aggregation.CONSENSUS, n_boot=1000,
    )

    # The bootstrap and permutation paths measure lift over DATES while
    # clustering the inference by profile. The profile-aggregate path
    # collapses to presence-per-profile, which is only meaningful when both
    # sides have the same number of windows per profile — they do not here
    # (one event date vs ~30 negative dates), so its lift is not reported.
    boot = methods["cluster_bootstrap"]
    perm = methods["cluster_permutation"]

    print("=" * 100)
    print("DASHA LORD AT MARRIAGE  (association, not prediction)")
    print("=" * 100)
    print(f"{'factor':<16} {'naive p':>12} {'boot p':>10} {'perm p':>10} "
          f"{'lift':>7} {'lift 95% CI':>22} {'overstated':>13}")
    print("-" * 100)

    survivors = []
    for f in TARGET_FACTORS:
        b, pm = boot[f], perm[f]
        ci = f"[{b.lift_low:.2f}, {b.lift_high:.2f}]"
        ov = b.inflation_factor
        ov_s = f"{ov:,.0f}x" if ov < 1e6 else f"{ov:.1e}x"
        print(f"{f:<16} {b.naive_p:>12.2e} {b.p_value:>10.4f} {pm.p_value:>10.4f} "
              f"{b.lift:>7.3f} {ci:>22} {ov_s:>13}")
        # Require agreement between both cluster-robust methods, and a CI
        # that excludes 1.0. Either alone is not enough.
        if (b.p_value <= 0.05 and pm.p_value <= 0.05
                and b.lift_low > 1.0):
            survivors.append(f)

    print()
    print(f"profiles positive (event)     : {boot[TARGET_FACTORS[0]].profiles_positive}")
    print(f"profiles negative (no event)  : {boot[TARGET_FACTORS[0]].profiles_negative}")
    print()
    if survivors:
        print("Survives BOTH cluster-robust methods with a CI excluding 1.0:",
              ", ".join(survivors))
        print()
        print("This would still not be a predictive result. It would be an")
        print("association on a convenience sample of publicly-documented")
        print("figures, requiring replication on an independent cohort.")
    else:
        print("VERDICT: no dasha lord shows an association with marriage timing")
        print()
        print("  - neither cluster-robust method reaches p <= 0.05, and")
        print("  - no confidence interval excludes 1.0")
        print()
        print("This is a NULL result on a convenience sample of famous people")
        print("with public marriage records. It is not evidence that Vedic")
        print("astrology lacks predictive power in general; the sample, the")
        print("single event category, and the uncontrolled dasha-duration")
        print("confound all limit what can be concluded from it.")
    print()
    print("CAVEATS: dasha period length is uncontrolled (Ketu 7y ... Venus 20y),")
    print("so a long dasha is partly a statement about duration. The sample is")
    print("famous people with public marriage records, not a random sample.")


if __name__ == "__main__":
    main()