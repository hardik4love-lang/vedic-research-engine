"""
First real run: the engine against actual documented life events.

Two analyses are performed and reported separately, because they answer
different questions and only one of them is a real test:

  A. BACKTEST (predictive, out-of-sample)
     The full protocol: train on early life, predict blind, score on the
     held-out period. This is the only result that could support a
     predictive claim.

  B. ASSOCIATION (descriptive, not predictive)
     Compares the dasha/transit configuration at marriage against the same
     profiles' non-event periods. This measures whether a configuration
     co-occurs with marriage more often than chance. It CANNOT support a
     predictive claim: no blind prediction, no held-out period, and the
     same people appear on both sides.

Reporting B without A would be the classic way to manufacture a result, so
the two are never merged.
"""

import csv
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.backtest import BacktestProfile, run_backtest  # noqa: E402
from engine.correlation import (  # noqa: E402
    Aggregation,
    compute_associations,
)
from engine.events import (  # noqa: E402
    DatePrecision,
    EventCategory,
    LifeEvent,
    resolve_date_interval,
)
from engine.features import (  # noqa: E402
    FeatureVector,
    extract_features_at,
    sample_negative_dates,
)
from engine.vedic_layer import build_vedic_chart  # noqa: E402

DATA = ROOT / "data" / "aa_profiles_with_events.csv"


def load_profiles() -> list[BacktestProfile]:
    profiles: list[BacktestProfile] = []
    with DATA.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            naive = datetime.strptime(
                f"{row['birth_date']} {row['birth_time']}", "%Y-%m-%d %H:%M"
            )
            sign = 1 if row["birth_tz"].startswith("+") else -1
            oh, om = row["birth_tz"][1:].split(":")
            utc_birth = naive - timedelta(
                hours=sign * int(oh), minutes=sign * int(om)
            )

            try:
                chart = build_vedic_chart(
                    utc_birth, "UTC", float(row["lat"]), float(row["lon"])
                )
            except Exception:  # noqa: BLE001
                continue

            events: list[LifeEvent] = []
            key = row["row_key"]
            events.append(
                LifeEvent(
                    profile_id=key,
                    category=EventCategory.RELATIONSHIP,
                    sub_category="marriage",
                    date_interval=resolve_date_interval(
                        row["marriage_date"],
                        DatePrecision(row["marriage_precision"]),
                    ),
                    impact=4,
                    certainty=4,
                    description=f"married {row['spouse']}",
                )
            )
            if row["divorce_date"]:
                events.append(
                    LifeEvent(
                        profile_id=key,
                        category=EventCategory.RELATIONSHIP,
                        sub_category="divorce",
                        date_interval=resolve_date_interval(
                            row["divorce_date"],
                            DatePrecision(row["divorce_precision"]),
                        ),
                        impact=4,
                        certainty=4,
                        description=f"divorced {row['spouse']}",
                    )
                )

            profiles.append(
                BacktestProfile(
                    profile_id=key,
                    chart=chart,
                    events=events,
                    birth_date=date.fromisoformat(row["birth_date"]),
                )
            )
    return profiles


def run_association(profiles: list[BacktestProfile], category: EventCategory):
    """Descriptive comparison of event vs non-event configurations."""
    positives, negatives = [], []
    precision_counts: Counter = Counter()

    for p in profiles:
        for ev in p.events:
            if ev.category is not category:
                continue
            precision_counts[ev.date_interval.precision.value] += 1
            positives.append(
                [
                    FeatureVector(
                        when=d, factors=extract_features_at(p.chart, d).factors
                    )
                    for d in ev.date_interval.sample_dates(step_days=7)
                ]
            )

        spans = [
            (e.date_interval.start, e.date_interval.end)
            for e in p.events
            if e.date_interval.precision is not DatePrecision.UNKNOWN
        ]
        for d in sample_negative_dates(
            p.birth_date + timedelta(days=365 * 25),
            date.today(),
            step_days=45,
            exclude=spans,
            margin_days=365,
        ):
            negatives.append(
                [FeatureVector(
                    when=d, factors=extract_features_at(p.chart, d).factors
                )]
            )

    assocs = compute_associations(
        category, positives, negatives,
        aggregation=Aggregation.CONSENSUS, min_support=10,
    )
    return assocs, positives, negatives, precision_counts


def main() -> None:
    profiles = load_profiles()
    ev_counts = Counter(len(p.events) for p in profiles)
    print(f"profiles loaded          : {len(profiles)}")
    print(f"total events             : {sum(len(p.events) for p in profiles)}")
    print(f"events per profile       : {dict(sorted(ev_counts.items()))}")
    print(f"profiles with >=5 events : "
          f"{sum(1 for p in profiles if len(p.events) >= 5)}")

    # ---- A. Predictive backtest ----
    print("\n" + "=" * 70)
    print("A. BLIND BACKTEST (predictive, out-of-sample)")
    print("=" * 70)
    report = run_backtest(profiles, version="aa-marriage-v1", min_support=5)
    print(f"profiles tested    : {report.n_profiles}")
    print(f"profiles excluded  : {report.n_excluded}")
    for reason, n in report.exclusion_reasons.items():
        print(f"   {n:4d}  {reason}")
    print(f"\nFINDING: {report.finding}")

    # ---- B. Descriptive association ----
    print("\n" + "=" * 70)
    print("B. ASSOCIATION (descriptive, NOT predictive)")
    print("=" * 70)
    assocs, positives, negatives, prec = run_association(
        profiles, EventCategory.RELATIONSHIP
    )
    print(f"event windows      : {len(positives)}")
    print(f"negative windows   : {len(negatives)}")
    print(f"event precision    : {dict(prec)}")
    print(f"factors tested     : {len(assocs)}")

    analysable = [a for a in assocs if a.sufficient_data]
    print(f"factors with enough support: {len(analysable)}")

    significant = [
        a for a in analysable
        if a.lift > 1.2 and a.p_value_corrected < 0.05 and a.lift != float("inf")
    ]
    print(f"\nafter Bonferroni + lift>1.2: {len(significant)} factors")

    for a in sorted(analysable, key=lambda x: -x.lift)[:12]:
        print(f"  {a.factor:<44} lift={a.lift:5.2f} "
              f"p_corr={a.p_value_corrected:.3f} n={a.a}")

    print("\n" + "!" * 70)
    print("CONFOUNDS THAT MAKE THE ABOVE UNINTERPRETABLE AS PREDICTION")
    print("!" * 70)
    print(f"""
1. PSEUDO-REPLICATION (a flaw in this analysis, not the data).
   {len(negatives):,} negative windows were drawn from only {len(profiles)}
   profiles at 45-day intervals. These are massively autocorrelated: the
   same natal chart recurs at every sample. Treating them as independent
   inflates significance by orders of magnitude, so the corrected
   p-values below are far too small. The effective sample size is closer
   to the number of profiles, not the number of windows.

2. DASHA LENGTH IS NOT CONTROLLED.
   Vimshottari dasha lengths differ (Ketu 7y ... Venus 20y). A 18-year
   Rahu dasha covers a large share of an adult life, so "was in Rahu
   dasha" is partly a statement about dasha duration rather than about
   timing. No normalisation for this was applied.

3. YEAR-PRECISION EVENTS ASYMMETRY.
   {prec.get('year', 0)} of {sum(prec.values())} events are year-precision and
   are reduced to CONSENSUS factors across the year, while each negative
   is a single date. The modes differ in granularity even though the
   aggregation rule is nominally the same.

4. SAMPLE SELECTION.
   The subjects are famous people whose marriages are publicly documented.
   That is not a random sample of lives, and fame correlates with both
   marriage publicity and age at marriage.

None of these can be resolved with this dataset.
""")

    if not significant:
        print("No factor survives correction. On this sample, marriage timing")
        print("shows no association with the tested astrological configurations")
        print("beyond what chance would produce.")
    else:
        print(f"{len(significant)} factor(s) survive correction. DESCRIPTIVE ONLY.")
        print("Given confound 1, the significance is almost certainly")
        print("inflated. This is NOT evidence that Vedic astrology predicts")
        print("marriage timing, and analysis A above could not run at all.")


if __name__ == "__main__":
    main()
