# Technical Implementation Plan
## Layered Architecture, Reproducibility Protocols, and Evaluation Framework

| | |
|---|---|
| **Document** | TIP-001 |
| **Status** | As-built for Phases 0–5, forward plan for 6–7 |
| **Verification** | 191 automated tests, static analysis clean, 400-record corpus sweep |

---

## 1. Architecture Overview

Four layers with strictly enforced separation of concerns. The central
architectural constraint is that **no layer may silently substitute its output
for another's**.

```
┌─────────────────────────────────────────────────────────────┐
│  PRESENTATION      mobile-first SPA, accuracy dashboard     │
├─────────────────────────────────────────────────────────────┤
│  EXPLANATION       cites measured evidence; renders refusal   │
│                    when none exists                          │
├─────────────────────────────────────────────────────────────┤
│  BACKTEST          temporal splits, structural blindness,    │
│                    baselines, calibration                    │
├─────────────────────────────────────────────────────────────┤
│  STATISTICAL       association rules, lift, chi-square,     │
│                    Bonferroni, Wilson intervals              │
├─────────────────────────────────────────────────────────────┤
│  VEDIC LOGIC       dasha, nakshatra, divisional charts,     │
│                    dignity, combustion, aspects, yogas       │
├─────────────────────────────────────────────────────────────┤
│  ASTRONOMICAL      Swiss Ephemeris: JD, planets, houses,    │
│                    ayanamsha. No Vedic logic in this layer.  │
└─────────────────────────────────────────────────────────────┘
```

**Enforcement.** The presentation layer issues relative requests to a
same-origin API. No host is baked into the client bundle, so a deployment
target change cannot silently break data provenance.

### 1.1 Layer Boundaries as Invariants

| Invariant | Enforced by |
|---|---|
| Astronomical layer contains no Vedic concepts | Module has no knowledge of dashas or nakshatras |
| Vedic layer never invents astronomical values | All positions originate from the ephemeris |
| Statistical layer never reads evaluation data | `TrainingSet` has no field capable of holding it |
| Explanation layer never states an unmeasured claim | Refusal is a first-class rendered state |
| Presentation never interprets | It displays; the accuracy dashboard reads measured values |

### 1.2 Component Map

```
engine/
  swisseph_wrapper.py   Astronomical layer. JD conversion, planet
                       positions, ayanamsha application, nakshatra
                       arithmetic, Vimshottari period arithmetic.
  vedic_layer.py        Vedic layer. Whole-sign houses, dignity,
                       combustion, aspects, divisional charts, yogas.
  events.py             Domain model. Precision → closed date interval.
  features.py           Feature extraction + negative sampling.
  correlation.py        Association statistics + rule screening.
  backtest.py           Temporal splits, blindness, baselines,
                       calibration, harness self-test.
storage/
  event_store.py        SQLite reference implementation; fingerprints,
                        staleness detection.
api/server.py           HTTP contract; also serves the SPA.
mobile/                 Expo React Native client.
scripts/                Corpus acquisition, bulk validation, first run.
```

### 1.3 Technology Selection

| Component | Choice | Rationale |
|---|---|---|
| Ephemeris | `pyswisseph` 2.10.3 | Sidereal support, multiple ayanamsha formulations, ASTI compliance |
| Timezones | stdlib `zoneinfo` + `tzdata` | **Not pytz** — see §5.2 |
| API | FastAPI + Pydantic v2 | Schema-enforced contract |
| Storage (dev) | SQLite via stdlib | Zero-config reference implementation |
| Storage (prod) | PostgreSQL | Schema specified in `specs/event_schema.sql` |
| Client | Expo / React Native | Single codebase, device-testable without Xcode |
| Tunnelling | Cloudflare quick tunnel | No account required for evaluation |

**Swiss Ephemeris licensing is GPL.** Research and non-commercial use is
compatible. Any commercial deployment requires a purchased licence; this must
be resolved before, not after, commercial intent exists.

---

## 2. Calculation Configuration Protocol

### 2.1 The Requirement

A chart is a function of birth data **and** configuration. If configuration is
not persisted, a later change to a default silently invalidates every stored
result, and no artefact records that the change occurred.

### 2.2 Implemented Protocol

**Per-profile configuration snapshot.**

```json
{
  "ayanamsha": "lahiri",
  "house_system": "whole_sign",
  "divisional_charts": ["D1", "D9", "D10", "D12"],
  "dasha_system": "vimshottari",
  "dasha_levels": 3
}
```

**Per-chart fingerprint.** SHA-256 over birth date, time, timezone, latitude,
longitude (6 dp), and the serialised configuration, truncated to 16 hex
characters.

**Staleness detection.** `find_stale_features()` **recomputes** the expected
fingerprint from the profile row rather than reading the cached column. This is
deliberate: editing `calc_config` does not refresh the cached column, so a
comparison against the cache would report stale features as current. The check
is useless unless it recomputes, and a regression test enforces this.

### 2.3 Ayanamsa Divergence — Documented, Not Hidden

Swiss Ephemeris returns **23.857092°** at J2000 for Lahiri. The commonly
published Chitrapaksha value is **23.853086°** — a difference of **14
arcseconds**. The test suite asserts a 0.005° tolerance and records the
discrepancy explicitly.

This matters practically: ayanamsa formulation differences are the most common
cause of "my chart doesn't match" disputes between software packages. The
system discloses its value rather than asserting a canonical one.

### 2.4 Historical Timezone Protocol

Two independent sources of ambiguity, both documented and tested:

**Zone LMT versus longitude LMT.** Astro-Databank derives local mean time from
the *stated longitude*; the IANA database derives it from the *zone's*
historical reference meridian. For a 19th-century Ulm birth these differ by
13.5 minutes. A test asserts the discrepancy exists and quantifies its effect
on the ascendant.

**Precision consequence.** 17 of 25 sampled real records flip their ascendant
sign if their UTC offset is ignored. A one-hour error raises no exception; it
returns a plausible chart with the wrong lagna, propagating into every
downstream feature. The client surfaces this as inline guidance on the profile
form.

---

## 3. Astronomical Correctness Protocol

### 3.1 Verification Strategy

Correctness is established against **external ground truth**, never against the
engine's own output. Two classes of evidence:

**Class A — published astronomical quantities.** Sun longitude at IAU
equinox/solstice instants is a known value determined by observational
astronomy. Agreement within 0.0007° across 1990–2020 validates Julian Day
conversion and planetary computation simultaneously.

**Class B — independent implementations and non-astrological sources.** Cross-
implementation agreement on a sourced chart (Einstein: four quantities).
Agreement with a traditional biographical account on a nakshatra (Ramana:
Punarvasu), authored independently of any astrology implementation.

### 3.2 Class B Provenance Discipline

Charts are labelled `external-source`, `external-source-partial`, or
`self-snapshot`, with partial verification declaring **which quantities** it
covers. Charts whose birth data is disputed or rectified are labelled
`unusable` and excluded, with the exclusion reason retained and test-enforced.

**This discipline produced a concrete finding.** Two initially-plausible golden
charts were removed: one is rectified from an approximate time with sources
spanning 37 minutes, and its date is described by its encyclopaedic source as
disputed across a fourteen-month range. The engine had been using a birth time
no source supported. Had those been accepted, the suite would have passed while
testing the engine against a guess.

### 3.3 Known Gap

The Swiss Ephemeris data files are not installed locally; computation falls
back to the Moshier ephemeris. Outer-planet longitude accuracy under Moshier is
materially worse than under the primary files. The verified assertions are
solar and lunar, where this is immaterial; **outer-planet transit work is not
yet verified** and requires the data files before Phase 3 conclusions involving
Jupiter or Saturn transits should be treated as final.

---

## 4. Statistical Framework

### 4.1 Association Measurement

For each category and factor, a 2×2 contingency table:

| | Factor present | Absent |
|---|---|---|
| Event | a | b |
| No event | c | d |

Derived: `P(factor|event)` (precision), `P(factor|no event)` (false-positive
rate), lift, Pearson χ², and the 1-df survival function
`erfc(√(x/2))` — closed-form, so no SciPy dependency.

**Wilson score intervals** rather than the normal approximation, because
association support is frequently small and the normal approximation misbehaves
at 0 and 1.

**Bonferroni across categories × factors**, not factors alone. Testing nine
categories inflates the family-wise error rate as much as testing many factors
does; correcting over factors only is insufficient.

### 4.2 Screening into Rules

A factor becomes a rule only if: support ≥ threshold, lift ≥ 1.5,
Bonferroni-corrected p ≤ 0.05, **and** lift is finite. Infinite-lift factors
(zero negatives) are rejected — otherwise every rare configuration becomes a
"perfect" predictor. Weights are log-scaled and bounded to [0, 1) so a single
extreme factor cannot dominate a prediction.

### 4.3 Insufficient-Data Classification

Below the support threshold, an association is reported as unanalysable with a
stated reason. It never receives a p-value, and it never becomes a rule. With
three positives a factor can trivially reach p < 0.05; the guard exists to
prevent that from being reported as a finding.

---

## 5. Blind Backtesting Protocol

### 5.1 Structural Blindness

The temporal split is 60/20/20 over adult life, anchored at age 25, with
minimum windows of 15 years (train), 3 years (predict), 3 years (evaluate). The
prediction window is a distinct gap; evaluation is scored separately, so a
prediction is never scored against an outcome it could have been fitted to.

Blindness is enforced **structurally, not by convention**:

```python
@dataclass
class TrainingSet:
    profile_id: str
    split: TemporalSplit
    events: list[LifeEvent]   # validated against split.train_end on construction
```

There is no parameter through which held-out data could arrive. Constructing a
`TrainingSet` containing a post-boundary event raises. A test asserts the field
set, so adding a bypass would break the suite.

### 5.2 Harness Self-Verification

A backtester that reports signal on noise is worse than useless, because it
manufactures confidence. `selftest_signal_recovery()` constructs data with a
planted signal and data with none:

| Input | lift | p | Required outcome |
|---|---|---|---|
| Planted signal | 10.0 | 3.4e-08 | detected |
| Independent noise | 1.17 | 0.36 | **not** detected |

This must pass before any real result is considered credible. Both directions
are asserted.

### 5.3 Required Metrics

Precision, recall, F1, false-positive rate, coverage, and expected calibration
error over score bins — all with Wilson intervals. Coverage is reported
**alongside** precision, because a high firing rate inflates recall while
destroying precision; neither is interpretable alone.

### 5.4 Mandatory Baselines

Random at matched firing rate; dasha-only; transit-only; persistence. A rule
set that does not beat a random predictor at the same rate is reported as a
null result, with the explicit verdict string.

### 5.5 Result Classification

- Beats baseline → signal detected, **must be reproduced on an independent
  cohort before being believed**
- Does not beat baseline → **valid negative result**, reported as such
- No eligible cohort → **data limitation, explicitly not a negative result**

The third distinction is why the current state can be reported honestly.

### 5.6 Precision-Symmetry Requirement

Aggregating an imprecise event across its candidate-date interval while sampling
negatives at single points inflates lift. The effect is measured, not assumed:
`check_aggregation_symmetry()` reports inflation and a test demonstrates it
with a factor present in one month of twelve — biased aggregation calls it
strongly predictive, symmetric aggregation correctly reports it as
non-consensus.

### 5.7 Pseudo-Replication Hazard — Identified, Not Yet Resolved

The first real run drew **345,388 negative windows from 516 profiles** at
45-day intervals. These are massively autocorrelated; the same natal chart
recurs at every sample. Treating them as independent inflates significance by
orders of magnitude. Effective sample size is closer to the number of
profiles.

This is a **defect in the analysis harness**, not in the data, and it
invalidates the p-values from that run. One factor (`dasha=rahu`, lift 1.81)
cleared the corrected threshold in that run; it should be treated as
uninterpretable until block-bootstrap or cluster-robust methods are applied.

Additional uncontrolled confounds from that run: Vimshottari period lengths
differ (Ketu 7 y … Venus 20 y), so a long dasha is partly a statement about
duration rather than timing; and the sample comprises publicly documented
figures, which is not a random sample of lives.

**Action:** the first real run's results are not to be cited. §6.4 specifies
the fix.

---

## 6. Forward Work

### 6.1 Install Swiss Ephemeris Data Files (Prerequisite)

Resolves §3.3. Requires a licence decision for any non-research use.

### 6.2 Complete the Golden Dataset

Target 20 charts at Rodden AA with cross-verified placements. Approximately
half a day per chart of manual cross-checking. Not parallelisable without
introducing the provenance errors documented in §3.2.

### 6.3 Resolve Cluster Dependence in Evaluation

Replace naive negative sampling with one of:

- **Block bootstrap** over profiles, resampling subjects rather than windows
- **Cluster-robust standard errors**, clustered by profile
- **Subject-level leave-one-out**, with negatives aggregated per subject

Whichever is chosen, the reported confidence intervals must be derived from
resampling subjects. This is the single highest-priority correction.

### 6.4 Control for Dasha Duration

Normalise association measures against each lord's period length, or include
period length as a covariate. Without this, the analysis measures the Vimshottari
cycle rather than any timing hypothesis.

### 6.5 Aggregate Correlated Factors

Factors are not independent (a Rahu dasha implies particular house-lord
factors). Bonferroni over 301 correlated tests is roughly but not exactly
appropriate; consider a permutation test or effective-number-of-tests
correction.

### 6.6 Data Acquisition

The binding constraint on the research question. Options, in descending
cost-effectiveness:

1. Manual collection of events for a targeted cohort (highest quality, highest cost)
2. Licensed biographical datasets
3. **Reduce scope:** accept one or two categories with adequate density rather
   than nine with inadequate density. Fewer categories with sufficient support
   beats broad coverage that no factor can clear.

Option 3 is recommended. The protocol's minimum support threshold combined with
the observed 1.1 events per subject means a nine-category evaluation is
arithmetically infeasible with current data; a two-category evaluation is not.

---

## 7. Verification Summary

| Area | Method | Result |
|---|---|---|
| Astronomical layer | Published ephemeris instants, 1990–2020 | within 0.0007° |
| Julian Day | Independent Meeus implementation | within 1e-6 day |
| Timezones | IANA database comparison | exact |
| Vedic layer | Independent implementation, sourced chart | 4/4 quantities |
| Nakshatra | Independent traditional source | 1/1 quantity |
| Dasha arithmetic | Contiguity and cycle-sum assertions | pass |
| Robustness | 400 Rodden-AA records, real data | 0 invariant violations |
| Statistics | Planted-signal / noise self-test | both directions pass |
| Backtest harness | Leakage and blindness assertions | pass |
| API contract | 20 endpoint tests | pass |
| Total | — | **191 passing** |