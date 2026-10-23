-- 003_journeys_schema.sql
-- Raw tables for TfL Santander Cycles journey history.
-- Values are kept as text, exactly as in the CSV files, under one set of column
-- names. Old and new files use different headers, so the loader maps both to these.
-- Types (timestamps, numbers) are applied later in staging.

CREATE TABLE IF NOT EXISTS raw.journey_file (
    file_name     text PRIMARY KEY,
    period_start  date,
    period_end    date,
    size_bytes    bigint,
    row_count     bigint,
    header        text,          -- the header exactly as it appeared, to track format changes
    header_format text,          -- 'new' or 'old'
    loaded_at     timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE raw.journey_file IS
  'One row per TfL usage-stats file loaded. The loader skips files already listed here.';

CREATE TABLE IF NOT EXISTS raw.journeys (
    source_file         text NOT NULL REFERENCES raw.journey_file (file_name),
    rental_id           text,
    start_time          text,    -- London local time as written in the file
    start_station_id    text,
    start_station_name  text,
    end_time            text,
    end_station_id      text,
    end_station_name    text,
    bike_id             text,
    bike_model          text,    -- only in newer files
    duration_text       text,    -- e.g. '19m 33s' in newer files
    duration_ms         text,    -- newer files
    duration_s          text     -- older files
);

CREATE INDEX IF NOT EXISTS journeys_source_file_idx ON raw.journeys (source_file);

COMMENT ON TABLE raw.journeys IS
  'Every hire from the TfL journey files, values as text exactly as published.';
COMMENT ON COLUMN raw.journeys.start_station_id IS
  'Station id as published. Newer files may use the terminal number rather than the BikePoints id: check before joining.';
