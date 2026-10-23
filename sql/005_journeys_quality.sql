-- 005_journeys_quality.sql
-- Fixes found by src/checks/journeys_check.py (see docs/data_issues.md, issues 2, 4 and 5).
-- Run on an empty staging.journeys (TRUNCATE first), then rerun 030 to restage from raw.

-- One shared rule for cleaning station names: trim, no space before a comma, single spaces.
CREATE OR REPLACE FUNCTION staging.clean_name(name text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
    SELECT regexp_replace(regexp_replace(trim(name), '\s+,', ',', 'g'), '\s{2,}', ' ', 'g')
$$;

COMMENT ON FUNCTION staging.clean_name(text) IS
  'Cleans station names: trims, removes spaces before commas, collapses double spaces. Issue 2.';

-- Issue 2: clean the names already in the dock dimension
UPDATE staging.dock SET name = staging.clean_name(name) WHERE name <> staging.clean_name(name);

-- Issue 4: record how each journey end was matched to a dock
ALTER TABLE staging.journeys ADD COLUMN IF NOT EXISTS start_match text;
ALTER TABLE staging.journeys ADD COLUMN IF NOT EXISTS end_match   text;

COMMENT ON COLUMN staging.journeys.start_match IS
  'matched = terminal number and name agree; name_mismatch = terminal number now belongs to a different dock; no_dock = no live dock has this terminal number.';

-- Issue 5: flag hires that are too short, too long or impossible
ALTER TABLE staging.journeys ADD COLUMN IF NOT EXISTS is_valid_trip boolean
    GENERATED ALWAYS AS (duration_s BETWEEN 60 AND 86400 AND end_time >= start_time) STORED;

COMMENT ON COLUMN staging.journeys.is_valid_trip IS
  'True when the hire lasted 1 minute to 1 day and ended after it started. Use for demand analysis.';

-- UK bank holidays (England) in the journey period, from gov.uk/bank-holidays
CREATE TABLE IF NOT EXISTS staging.uk_bank_holiday (
    day  date PRIMARY KEY,
    name text NOT NULL
);
INSERT INTO staging.uk_bank_holiday VALUES
    ('2025-08-25', 'Summer bank holiday'),
    ('2025-12-25', 'Christmas Day'),
    ('2025-12-26', 'Boxing Day'),
    ('2026-01-01', 'New Year''s Day'),
    ('2026-04-03', 'Good Friday'),
    ('2026-04-06', 'Easter Monday'),
    ('2026-05-04', 'Early May bank holiday'),
    ('2026-05-25', 'Spring bank holiday'),
    ('2026-08-31', 'Summer bank holiday')
ON CONFLICT (day) DO NOTHING;
