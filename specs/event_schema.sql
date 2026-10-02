-- Vedic Astrology Event Database Schema (MVP)

-- Core profiles table
CREATE TABLE profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Birth data
    birth_date DATE NOT NULL,              -- YYYY-MM-DD
    birth_time TIME NOT NULL,              -- HH:MM:SS (24hr)
    birth_timezone TEXT NOT NULL,          -- IANA tz, e.g., "America/New_York"
    latitude DECIMAL(9,6) NOT NULL,        -- WGS84, -90 to 90
    longitude DECIMAL(9,6) NOT NULL,       -- WGS84, -180 to 180
    birth_city TEXT,                       -- Human-readable
    birth_country TEXT,
    
    -- Calculation config snapshot (JSONB)
    calc_config JSONB NOT NULL DEFAULT '{
        "ayanamsha": "lahiri",
        "house_system": "whole_sign",
        "divisional_charts": ["D1", "D9", "D10", "D12"],
        "dasha_system": "vimshottari",
        "dasha_levels": 3
    }'::jsonb,
    
    -- Computed chart data (cached)
    chart_data JSONB,                      -- Full computed chart
    chart_computed_at TIMESTAMPTZ,
    
    -- Metadata
    source TEXT DEFAULT 'manual',          -- manual, import, api
    notes TEXT
);

-- Events table with precision metadata
CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Event classification
    category TEXT NOT NULL,                -- career, relationship, family, education, finance, location, health, legal, other
    sub_category TEXT,                     -- promotion, marriage, child_birth, graduation, etc.
    
    -- Date with precision
    start_date DATE NOT NULL,
    end_date DATE,                         -- NULL for point events
    date_precision TEXT NOT NULL CHECK (date_precision IN ('exact', 'month', 'quarter', 'year', 'unknown')),
    
    -- Impact & certainty
    impact SMALLINT CHECK (impact BETWEEN 1 AND 5),  -- 1=minor, 5=life-changing
    certainty SMALLINT CHECK (certainty BETWEEN 1 AND 5),  -- 1=uncertain, 5=verified
    
    -- Description
    description TEXT,
    notes TEXT,
    
    -- Astrological context (cached at event creation)
    dasha_at_event JSONB,                  -- Dasha/Antardasha/Pratyantardasha lords
    transits_at_event JSONB,               -- Key planetary transits
    chart_factors JSONB                    -- House activations, aspects, yogas
);

-- Indexes
CREATE INDEX idx_events_profile ON events(profile_id);
CREATE INDEX idx_events_category ON events(category);
CREATE INDEX idx_events_start_date ON events(start_date);
CREATE INDEX idx_events_precision ON events(date_precision);

-- Event categories enum (for validation)
CREATE TYPE event_category AS ENUM (
    'career', 'relationship', 'family', 'education', 
    'finance', 'location', 'health', 'legal', 'other'
);

CREATE TYPE event_sub_category AS ENUM (
    -- Career
    'first_job', 'promotion', 'job_loss', 'job_change', 
    'business_launch', 'business_closure', 'retirement',
    -- Relationships
    'relationship_started', 'marriage', 'separation', 'divorce',
    -- Family
    'child_birth', 'major_family_event', 'parent_death',
    -- Education
    'admission', 'graduation', 'major_qualification',
    -- Finance
    'major_gain', 'major_loss', 'property_purchase', 'debt_restructuring',
    -- Location
    'relocation', 'foreign_move', 'home_purchase',
    -- Health
    'major_illness', 'surgery', 'recovery', 'accident',
    -- Legal
    'legal_dispute', 'legal_victory', 'legal_settlement',
    -- Other
    'other'
);

-- Historical matching results (for backtesting)
CREATE TABLE historical_matches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Match configuration
    rule_set TEXT NOT NULL,                -- e.g., "career_change_v1"
    factors JSONB NOT NULL,                -- Astrological factors that matched
    
    -- Statistics
    observed_frequency DECIMAL(6,4),
    expected_frequency DECIMAL(6,4),
    association_strength DECIMAL(6,4),
    false_positive_rate DECIMAL(6,4)
);

-- Backtest results
CREATE TABLE backtest_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Split configuration
    train_start DATE NOT NULL,
    train_end DATE NOT NULL,
    predict_start DATE NOT NULL,
    predict_end DATE NOT NULL,
    eval_start DATE NOT NULL,
    eval_end DATE NOT NULL,
    
    -- Model config
    rule_set TEXT NOT NULL,
    model_config JSONB NOT NULL,
    
    -- Metrics per category
    metrics JSONB NOT NULL,                -- {category: {precision, recall, f1, coverage, fpr, calibration}}
    
    -- Summary
    overall_precision DECIMAL(6,4),
    overall_recall DECIMAL(6,4),
    baseline_precision DECIMAL(6,4)
);

-- Prediction windows (future-looking)
CREATE TABLE prediction_windows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Window definition
    category TEXT NOT NULL,
    sub_category TEXT,
    window_start DATE NOT NULL,
    window_end DATE NOT NULL,
    
    -- Prediction details
    contributing_factors JSONB NOT NULL,   -- Dasha, transits, house activations
    historical_analogs INTEGER,            -- Number of similar historical configurations
    backtest_metrics JSONB,                -- Relevant backtest performance
    
    -- Confidence
    confidence_score DECIMAL(4,3),         -- 0.000-1.000
    confidence_label TEXT,                 -- low, medium, high
    
    -- Outcome tracking (filled later)
    actual_event_id UUID REFERENCES events(id),
    outcome TEXT CHECK (outcome IN ('confirmed', 'false_positive', 'pending', 'missed')),
    outcome_recorded_at TIMESTAMPTZ
);

-- Indexes for predictions
CREATE INDEX idx_predictions_profile ON prediction_windows(profile_id);
CREATE INDEX idx_predictions_window ON prediction_windows(window_start, window_end);
CREATE INDEX idx_predictions_outcome ON prediction_windows(outcome);

-- Accuracy dashboard view
CREATE VIEW accuracy_dashboard AS
SELECT 
    p.id AS profile_id,
    COUNT(DISTINCT e.id) AS total_events,
    COUNT(DISTINCT pw.id) AS total_predictions,
    COUNT(DISTINCT CASE WHEN pw.outcome = 'confirmed' THEN pw.id END) AS confirmed,
    COUNT(DISTINCT CASE WHEN pw.outcome = 'false_positive' THEN pw.id END) AS false_positives,
    COUNT(DISTINCT CASE WHEN pw.outcome = 'missed' THEN e.id END) AS false_negatives,
    ROUND(
        COUNT(DISTINCT CASE WHEN pw.outcome = 'confirmed' THEN pw.id END)::numeric / 
        NULLIF(COUNT(DISTINCT pw.id), 0) * 100, 2
    ) AS precision_pct,
    ROUND(
        COUNT(DISTINCT CASE WHEN pw.outcome = 'confirmed' THEN pw.id END)::numeric / 
        NULLIF(COUNT(DISTINCT e.id), 0) * 100, 2
    ) AS recall_pct
FROM profiles p
LEFT JOIN events e ON e.profile_id = p.id
LEFT JOIN prediction_windows pw ON pw.profile_id = p.id
GROUP BY p.id;