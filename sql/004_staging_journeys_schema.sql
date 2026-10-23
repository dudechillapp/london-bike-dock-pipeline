-- 004_staging_journeys_schema.sql
-- 1. Adds TfL's terminal number to the dock dimension, so journeys can be joined to docks.
-- 2. Creates staging.journeys: one typed row per hire, times in UTC.
-- Safe to run more than once.

-- ---------------------------------------------------------------
-- 1. Terminal number on staging.dock
-- ---------------------------------------------------------------
ALTER TABLE staging.dock ADD COLUMN IF NOT EXISTS terminal_name text;

COMMENT ON COLUMN staging.dock.terminal_name IS
  'TfL terminal number (TerminalName in the API), for example 001023. Journey files may use this instead of the BikePoints id.';

-- Fill it from the newest snapshot
UPDATE staging.dock d
SET terminal_name = t.terminal_name
FROM (
    SELECT dock->>'id' AS dock_id,
           (SELECT p->>'value' FROM jsonb_array_elements(dock->'additionalProperties') p
            WHERE p->>'key' = 'TerminalName') AS terminal_name
    FROM (SELECT payload FROM raw.bikepoint_snapshot ORDER BY pulled_at DESC LIMIT 1) s,
         jsonb_array_elements(s.payload) dock
) t
WHERE d.dock_id = t.dock_id;

-- ---------------------------------------------------------------
-- 2. staging.journeys
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS staging.journeys (
    rental_id           bigint      NOT NULL,
    start_time          timestamptz NOT NULL,
    end_time            timestamptz,
    duration_s          numeric(10,1),
    start_station_id    text,        -- as published in the file
    end_station_id      text,
    start_dock_id       text,        -- matched to staging.dock, NULL when no match
    end_dock_id         text,
    start_station_name  text,
    end_station_name    text,
    bike_id             text,
    bike_model          text,
    source_file         text NOT NULL,
    PRIMARY KEY (rental_id, start_time)
);

SELECT create_hypertable('staging.journeys', 'start_time',
                         chunk_time_interval => INTERVAL '1 month',
                         if_not_exists       => TRUE);

CREATE INDEX IF NOT EXISTS journeys_start_dock_idx ON staging.journeys (start_dock_id, start_time);

COMMENT ON TABLE staging.journeys IS
  'One row per Santander Cycles hire. Times converted from London local time to UTC.';
COMMENT ON COLUMN staging.journeys.start_time IS
  'When the hire started, UTC. Converted from London local time in the TfL file.';
COMMENT ON COLUMN staging.journeys.duration_s IS
  'Hire length in seconds, from Total duration (ms) in newer files or Duration in older files.';
COMMENT ON COLUMN staging.journeys.start_dock_id IS
  'BikePoints id of the start dock, matched by terminal number (or by BikePoints number in older files). NULL if the station no longer exists.';

-- Which raw files have been staged, so reruns only process new files
CREATE TABLE IF NOT EXISTS staging.journey_file_staged (
    file_name   text PRIMARY KEY,
    rows_staged bigint,
    staged_at   timestamptz NOT NULL DEFAULT now()
);
