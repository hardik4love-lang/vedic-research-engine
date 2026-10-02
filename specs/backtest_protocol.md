# Blind Backtesting Protocol (MVP)

## Core Principle
**Never train on the full life and claim prediction success.** The model must predict future events using only past data, with no knowledge of the evaluation period.

## Temporal Split Design

### Three-Period Split
For each profile with events spanning [birth, present]:

```
┌─────────────────────────────────────────────────────────────┐
│                    FULL LIFE TIMELINE                        │
├──────────────────┬───────────────────┬─────────────────────┤
│   TRAINING       │   PREDICTION      │   EVALUATION        │
│   (observed)     │   (blind)         │   (held-out)        │
│                  │                   │                     │
│  birth → T1      │   T1 → T2         │   T2 → T3 (present) │
└──────────────────┴───────────────────┴─────────────────────┘
```

### Split Ratios (configurable)
- **Training**: 60% of lifespan (minimum 15 years)
- **Prediction**: 20% of lifespan (minimum 5 years)  
- **Evaluation**: 20% of lifespan (minimum 5 years)

### Minimum Requirements
- Profile must have ≥10 years of adult life (age ≥25)
- Training period must contain ≥5 documented events
- Prediction period must be ≥3 years
- Evaluation period must be ≥3 years

## Backtest Procedure

### Step 1: Compute Charts for Training Period
For each profile in training set:
1. Compute natal chart (fixed at birth)
2. Compute all dasha periods overlapping training window
3. Compute all planetary transits during training window
4. Store: `{planet: {date: longitude, retrograde, combustion, dignity}}`

### Step 2: Extract Training Features
For each event in training window:
```python
features = {
    "dasha_lord": dasha_lord_at_event,
    "antardasha_lord": antardasha_lord_at_event,
    "pratyantardasha_lord": pratyantardasha_lord_at_event,
    "transiting_planets_in_house": {house: [planets]},
    "aspects_to_house_lords": {house_lord: [aspecting_planets]},
    "nakshatra_transits": {planet: nakshatra},
    "yogas_active": [yoga_names],
    "combustion_flags": {planet: bool},
    "retrograde_flags": {planet: bool}
}
```

### Step 3: Learn Association Rules
For each event category (career, relationship, etc.):
1. Collect all feature vectors for events of that category
2. Collect feature vectors for non-event time windows (negative samples)
3. Compute:
   - `P(feature | event_category)` — observed frequency
   - `P(feature | no_event)` — baseline frequency
   - `Lift = P(feature | event) / P(feature | no_event)`
4. Rank features by lift, statistical significance (chi-square)

### Step 4: Generate Prediction Rules
For each category, select top-K features where:
- Lift > 1.5 (configurable)
- p-value < 0.05 (Bonferroni corrected)
- Support ≥ 3 training events

Rule format:
```json
{
  "category": "career_change",
  "conditions": [
    {"type": "dasha_lord", "value": "saturn", "weight": 0.8},
    {"type": "transit_10th_house", "planets": ["saturn", "jupiter"], "weight": 0.9},
    {"type": "antardasha_lord", "value": "mars", "weight": 0.6}
  ],
  "threshold": 0.65,
  "training_support": 12,
  "training_lift": 2.3
}
```

### Step 5: Blind Prediction
For each profile in prediction window:
1. **Only use training-derived rules** — no access to prediction/eval events
2. Slide a 30-day window across prediction period
3. For each window, compute feature vector (same as Step 2)
4. Apply rules → score for each category
5. If score > threshold → emit prediction window

### Step 6: Evaluation
For each prediction window in evaluation period:
| Prediction | Actual Event | Outcome |
|------------|--------------|---------|
| Yes        | Yes          | True Positive |
| Yes        | No           | False Positive |
| No         | Yes          | False Negative |
| No         | No           | True Negative |

**Per-category metrics:**
- Precision = TP / (TP + FP)
- Recall = TP / (TP + FN)
- F1 = 2 * P * R / (P + R)
- Coverage = (TP + FP) / Total windows
- FPR = FP / (FP + TN)
- Calibration: Binned reliability diagram

**Aggregate metrics:**
- Macro-average (equal weight per category)
- Weighted by event frequency
- Baseline comparison: random predictor with same prediction rate

## Statistical Rigor

### Multiple Testing Correction
- Bonferroni: α / (categories × features tested)
- Report both raw and corrected p-values

### Confidence Intervals
- Wilson score interval for precision/recall (n < 30)
- Bootstrap CI (1000 resamples) for F1

### Baseline Comparisons
1. **Random**: Predict at base rate of each category
2. **Dasha-only**: Use only dasha lord as predictor
3. **Transit-only**: Use only major transits (Saturn, Jupiter)
4. **Persistence**: Predict same category as last event

### Out-of-Sample Validation
- Leave-one-profile-out cross-validation
- Time-series split: older profiles train, newer predict

## Reporting Template

```markdown
# Backtest Report — {date}

## Configuration
- Profiles: N={n}
- Training period: {start} → {end}
- Prediction period: {start} → {end}
- Evaluation period: {start} → {end}
- Rule set version: {version}

## Per-Category Results

| Category | Precision | Recall | F1 | Coverage | FPR | Support | Baseline P |
|----------|-----------|--------|-----|----------|-----|---------|------------|
| career   | 0.72      | 0.68   | 0.70| 0.15     | 0.08| 23      | 0.12       |
| relationship | 0.65  | 0.71   | 0.68| 0.12     | 0.06| 18      | 0.10       |
| ...      | ...       | ...    | ... | ...      | ... | ...     | ...        |

## Aggregate
- Macro F1: {value}
- Weighted F1: {value}
- vs Random: +{delta}%
- vs Dasha-only: +{delta}%

## Calibration
[Reliability diagram data]

## Failure Analysis
- Top 5 false positive patterns
- Top 5 false negative patterns
- Categories needing more training data
```

## Gate 5 Criteria (MVP)
- [ ] All 9 event categories tested
- [ ] ≥50 profiles with complete splits
- [ ] Macro F1 > baseline + 10% (minimum)
- [ ] Calibration error < 0.15
- [ ] No category with precision < 0.50
- [ ] Report generated automatically (no manual cherry-picking)