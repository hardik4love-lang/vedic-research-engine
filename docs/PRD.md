# Product Requirements Document
## Longitudinal Research Engine for Vedic Astrological Correlation

| | |
|---|---|
| **Document** | PRD-001 |
| **Status** | Baseline, incorporating Phase 0–5 empirical results |
| **Classification** | Research software, not consumer entertainment |
| **Supersedes** | The original 12-week roadmap (see §3.7 for material deviations) |

---

## 1. Executive Summary

### 1.1 Strategic Repositioning

The product is **not** a horoscope application. A horoscope application
optimises for engagement and generates confident narrative from a chart. This
product optimises for **falsifiability** and generates *nothing* when the
evidence does not support a claim.

The strategic pivot is from **prediction** to **measurement**. The system is
architected as a longitudinal research engine whose primary output is not a
prediction but an **audit trail**: for any asserted relationship between an
astrological configuration and a life event, the system must be able to
demonstrate, out of sample, at a stated precision, with a stated confidence
interval, and against a stated baseline.

Where such demonstration fails, the system is required to report failure. This
requirement is non-negotiable and is enforced structurally in code, not by
policy.

### 1.2 Value Proposition

| Traditional astrology product | This system |
|---|---|
| Asserts correctness | Reports measured performance, including null results |
| Hides its conventions | Stores and displays the full calculation configuration |
| Treats date precision as an implementation detail | Treats stated date precision as a first-class epistemic claim |
| Optimises for user satisfaction | Optimises for honest characterisation of its own reliability |
| Retro-fits explanation after the fact | Requires explanation to cite measured evidence |
| Single subject, one lifetime | Cohort-based, temporally held-out evaluation |

### 1.3 Principal Finding to Date

The engine is complete through the blind-backtesting harness and has been
exercised against the largest public corpus of verified birth times (400
Rodden-AA records, 1752–2009) and the largest public corpus of documented life
events attached to those births (616 events across 516 profiles).

**The predictive claim remains untested.** All 516 profiles were excluded from
backtesting because the protocol requires a minimum of five dated events per
subject and the observed distribution averages 1.1. The system reported this as
a data limitation rather than as a negative result, which is the correct
classification and is enforced by the reporting layer.

This finding is material to the product plan and is treated as such in §3.7.

---

## 2. Product Principles

1. **No claim without a denominator.** Every assertion carries its sample size,
   its confidence interval, and the baseline it was measured against.
2. **Refusal is a first-class outcome.** The system must be able to decline to
   answer. A prediction that cannot be supported is not rendered.
3. **Data provenance is visible.** Birth times carry source attribution and
   reliability ratings; events carry credibility levels and stated precision.
4. **Configuration is data.** The calculation configuration is persisted with
   every derived result so that a later change to conventions makes stale
   results *detectable* rather than silently wrong.
5. **Instrumentation before inference.** Failure modes are enumerated and
   tested before any statistical claim is attempted.

---

## 3. Phase-by-Phase Roadmap

Phases 0–5 are **complete and verified**. Phases 6–7 are revised in light of
measured results.

### 3.1 Phase 0 — Specification (Week 1) ✅

**Objectives.** Eliminate ambiguity before writing inference code.

**Technical Requirements.** Sidereal zodiac; Lahiri ayanamsha; whole-sign
houses; D1, D9, D10, D12 divisional charts; Vimshottari dasha to three
levels; combustion, dignity, retrograde, and Parashara aspects as codified in
`specs/astrology_rules.md`.

**Data Schema Requirements.** Every stored profile carries a `calc_config`
JSONB snapshot; every derived feature carries a `chart_fingerprint` (SHA-256
over birth data plus configuration).

**Validation Gate.** Specification frozen; taxonomy defined; protocol written.

**Result.** Delivered. Six specification artefacts produced.

### 3.2 Phase 1 — Calculation Engine (Weeks 2–3) ✅

**Objectives.** Astronomical correctness before any Vedic logic.

**Technical Requirements.** Julian Day conversion; planetary positions;
ayanamsha application; house cusps; nakshatra and pada boundaries; dasha
period arithmetic; divisional chart mapping under the Parashara rule (odd
divisions count forward, even divisions backward).

**Success Metrics.** 100% agreement on sign assignment against an independent
implementation; longitude agreement within 0.01°; dasha boundaries within
7 days; timezone correctness across historical transitions.

**Validation Gates 1 and 2.**

**Result.** Astronomical layer **verified against published data** — solar
longitude within 0.0007° (2.5 arcseconds) of IAU equinox and solstice
instants spanning 1990–2020; Julian Day agreement with an independent Meeus
implementation to 1e-6 day; timezone offsets matching the IANA database
exactly.

Two charts are externally cross-verified: Albert Einstein (Rodden AA, birth
certificate) matches an independent implementation on ascendant, solar sign,
lunar sign, and lunar nakshatra; Sri Ramana Maharshi matches an independent
traditional biographical source on the lunar nakshatra (Punarvasu).

**Gate 1 remains formally open.** The protocol targets a golden dataset of
20–30 charts; 2 are fully verified and 1 partially. The shortfall is
reported by the test suite on every run and cannot be silently closed.

### 3.3 Phase 2 — Event Database (Weeks 3–4) ✅

**Objectives.** Capture what subjects actually know, at the precision they
actually know it.

**Data Schema Requirements.** Nine event categories with a closed
sub-category taxonomy; five date-precision levels (exact, month, quarter, year,
unknown); impact and certainty on 1–5 scales.

**Validation Gate 3** — events stored reproducibly.

**Result.** Delivered and tested. A precision level resolves to a **closed
date interval**, never a point estimate. Year-precision events expand to 365
candidate dates and 53 sampled feature vectors; the system reports only factors
present in *every* candidate vector as reliably associated.

### 3.4 Phase 3 — Historical Matching (Weeks 5–6) ✅

**Objectives.** Transparent association rules; no learned model at this stage.

**Technical Requirements.** Named-string factor predicates; negative sampling;
association statistics with Bonferroni correction across the full
categories × factors family; Wilson score intervals; explicit
insufficient-data classification.

**Validation Gate 4** — matching without manual intervention.

**Result.** Delivered. Two methodological guards are enforced by test:

- **Precision-symmetry guard.** Aggregating imprecise positives across an
  interval while sampling negatives at single points inflates lift. A test
  demonstrates the inflation and a runtime check reports it.
- **Insufficient-data guard.** Associations below the support threshold are
  reported as unanalysable rather than as significant, and never become rules.

### 3.5 Phase 4 — Blind Backtesting (Weeks 7–8) ✅ *(harness)* / ⚠️ *(no evaluable cohort)*

**Objectives.** Out-of-sample evaluation with structural blindness.

**Result.** The harness is complete and **self-verified**: it recovers a
planted signal (lift 10.0, p = 3.4e-08) and reports nothing on independent
noise (lift 1.17, p = 0.36).

It has **not** been run on an evaluable cohort. See §3.7.

### 3.6 Phase 5 — Prediction (Weeks 9–10) ⛔ *Blocked*

**Status.** Blocked on Phase 4 cohort availability. The prediction surface
currently renders an explicit refusal with its rationale, which is the
specified behaviour for an unsupported claim.

### 3.7 Material Deviations from the Original Roadmap

Three findings invalidate assumptions in the original plan. They are recorded
here rather than omitted.

**Deviation 1 — The M3 cohort does not exist in public data.**
The plan gates on 100 profiles with ≥10 documented events each. The largest
public corpus of documented life events with verified birth times contains
**516 events across 516 profiles (1.1 per subject)**, with a maximum of 2. The
dataset is not sparse by accident; marriage and divorce are simply the only
event categories published at this linkage quality. Acquiring the remaining
categories at the required density is manual work with no automation path.

*Implication:* Phase 4 cannot be executed as specified without a
data-acquisition investment of approximately one quarter, independent of
engineering effort.

**Deviation 2 — Golden dataset density is insufficient for Gate 1.**
Rodden AA birth records are abundant; *cross-verified computed placements* are
not. Public sources disagree on several well-known charts: one prominent
figure's chart is rectified from an approximate time with sources spanning 37
minutes (~9° of ascendant, sufficient to change a whole-sign house), and
another has a birth date that its own encyclopaedic source describes as
disputed across a fourteen-month range.

*Implication:* Gate 1 requires manual cross-verification against a second
implementation, at roughly half a day per chart. Twenty charts is ten days of
deliberate work, not a coding task.

**Deviation 3 — Publication-quality astronomical data is unavailable locally.**
The Swiss Ephemeris data files are absent, so calculations fall back to the
Moshier ephemeris, whose outer-planet longitude accuracy is materially worse
than the primary. For the solar and lunar positions used by the verified
assertions this is immaterial; for outer-planet transit work it is not.

*Implication:* Phase 1 is verified for the quantities tested, and its
outer-planet accuracy is **not** yet verified.

### 3.8 Phase 6 — Mobile Interface (Week 11) ✅ *(partial)*

Delivered: single-origin mobile-first web application with chart rendering,
event capture, timeline with precision-aware dasha context, and configuration
disclosure. The accuracy dashboard is specified in §5 but **not implemented**,
because there is no measured model performance to display.

### 3.9 Phase 7 — Pilot (Week 12) ⛔ *Blocked*

Blocked on Gate 5. A pilot without a measured baseline would generate
predictions that could not later be honestly evaluated.

---

## 4. Product Interface & User Experience

### 4.1 Design Position

The interface has an obligation the consumer product does not: it must make
the system's epistemic state visible at the point of use. A user who cannot
tell whether a given number is measured or assumed is being misled, regardless
of how the number was derived.

### 4.2 Screen Requirements

| Screen | Requirement |
|---|---|
| Home | Discloses active calculation conventions at all times |
| Profile creation | Warns on pre-1900 births about timezone ambiguity |
| Chart | Renders D1 with legend, houses, vargas, dasha, yogas |
| Event entry | Precision selection is mandatory and explicit; no silent default |
| Timeline | Shows candidate-date count and configuration count per event |
| Predictions | **Renders refusal with rationale when unsupported** |
| Accuracy dashboard | Per-category precision, recall, calibration, sample size, baseline delta |
| Settings | Cache control, configuration disclosure, data export |

### 4.3 Accuracy Dashboard Specification

The dashboard is a **first-class product surface**, not a developer tool. It
must answer, for any category: *"How well has this historically performed, on
how many out-of-sample cases, against what baseline?"*

Required elements per category:

- Precision, recall, F1 with Wilson confidence intervals
- False-positive rate and coverage, presented together (high coverage is not
  favourable in isolation)
- Calibration error and reliability diagram
- Baseline comparison: random, dasha-only, persistence
- **Sample size displayed adjacent to every rate.** A precision computed on
  twelve cases must not render in the same visual weight as one computed on
  twelve hundred.
- Explicit "insufficient data" state where support is below threshold

Prohibited: presenting a rate without its denominator; rendering a rule-derived
score as a probability; displaying a category's performance as representative
of the system's overall accuracy.

### 4.4 Offline and Data-Loss Requirements

- Computed charts cached by (date, time, timezone, latitude, longitude)
- **Event entry writes to local storage before network transmission.** A failed
  send leaves the event queued with a visible pending indicator; it is never
  dropped.
- Cache invalidation must be possible, since a configuration change invalidates
  every cached chart

### 4.5 Exposure Warning

The sharing surface (public tunnel) carries **no authentication**. This is
acceptable for testing and must be disclosed in the interface for any
distribution scenario.

---

## 5. Scope Management

### 5.1 In Scope — Core Research Engine

Calculation engine with explicit configuration; structured event capture with
precision semantics; reproducible feature derivation with staleness detection;
transparent association statistics; blind backtest harness with baselines;
accuracy reporting including null results.

### 5.2 Out of Scope — Post-MVP

Remedies and gemstone recommendations; AI-generated narrative; voice
interfaces; divisional charts beyond the four in scope; yoga enumeration
beyond the core set; celebrity matching; social features; marketplace;
subscriptions; event scraping.

### 5.3 Explicitly Deferred — and Why

**Narration.** The architecture reserves an explanation layer, but
explanation must cite measured evidence. With no measured model, any narrative
would be ungrounded. Rendering nothing is correct.

**Prediction.** Blocked on cohort availability, not on engineering capacity.

**Additional divisional charts.** Each addition multiplies the factor space and
therefore tightens the multiple-testing correction without adding signal.

### 5.4 Resource Reallocation

If the product objective is a shippable application, the correct allocation is
to stop after Phase 5, treat the engine as a complete library, and invest
remaining effort in interface depth. A single user with a single chart requires
no cohort, no backtest, and no validation — none of which the interface
currently depends on except the prediction surface, which already renders
refusal.

If the objective is the research question, the correct allocation is to halt
interface work entirely and fund data acquisition. On current evidence that is
the binding constraint on the entire programme.

---

## 6. Success Criteria

The product succeeds if it can state, with evidence, one of:

- a set of configurations with measured out-of-sample predictive power
  exceeding baseline at stated confidence; or
- a demonstrated absence of such power, at sufficient statistical power to be
  informative.

The product **fails** if it ships predictions without either. The distinction
between these outcomes is the entire reason the system was built.