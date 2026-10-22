-- 001_schemas.sql
-- Creates the three warehouse layers and the first tables.
-- Safe to run more than once: everything uses IF NOT EXISTS.
--
-- raw      responses exactly as received, insert only, never updated
-- staging  cleaned and typed, one row per dock per pull, rebuilt from raw
-- marts    answers: hourly facts, KPIs and forecasts for dashboards and agents

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS marts;

-- ---------------------------------------------------------------
-- raw.bikepoint_snapshot: one row per API call, the full JSON
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.bikepoint_snapshot (
    pulled_at  timestamptz NOT NULL,
    payload    jsonb       NOT NULL
);

-- A hypertable, so a retention policy can drop old raw data later.
SELECT create_hypertable('raw.bikepoint_snapshot', 'pulled_at',
                         chunk_time_interval => INTERVAL '7 days',
                         if_not_exists       => TRUE);

COMMENT ON TABLE raw.bikepoint_snapshot IS
  'Full response from api.tfl.gov.uk/BikePoint, one row per pull (every 15 minutes). Never edited.';
COMMENT ON COLUMN raw.bikepoint_snapshot.pulled_at IS
  'When the pipeline called the API, in UTC.';

-- ---------------------------------------------------------------
-- staging.dock: one row per dock (the dimension table)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS staging.dock (
    dock_id     text PRIMARY KEY,
    name        text,
    lat         numeric(9,6),
    lon         numeric(9,6),
    first_seen  timestamptz,
    last_seen   timestamptz
);

COMMENT ON TABLE staging.dock IS
  'One row per Santander Cycles dock. Names and locations from the BikePoint API.';
COMMENT ON COLUMN staging.dock.dock_id IS
  'TfL dock id, for example BikePoints_1.';

-- ---------------------------------------------------------------
-- staging.dock_status: one row per dock per pull (the fact table)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS staging.dock_status (
    pulled_at    timestamptz NOT NULL,
    dock_id      text        NOT NULL,
    bikes        int,
    ebikes       int,
    empty_docks  int,
    total_docks  int,
    PRIMARY KEY (dock_id, pulled_at)
);

SELECT create_hypertable('staging.dock_status', 'pulled_at',
                         chunk_time_interval => INTERVAL '7 days',
                         if_not_exists       => TRUE);

COMMENT ON TABLE staging.dock_status IS
  'Bikes and spaces at each dock, every 15 minutes. Flattened from raw.bikepoint_snapshot.';
COMMENT ON COLUMN staging.dock_status.bikes IS
  'Bikes available to hire (NbBikes), including e-bikes. Excludes docks out of service.';
COMMENT ON COLUMN staging.dock_status.ebikes IS
  'E-bikes available to hire (NbEBikes).';
COMMENT ON COLUMN staging.dock_status.empty_docks IS
  'Docks free to return a bike into (NbEmptyDocks). Excludes docks out of service.';
COMMENT ON COLUMN staging.dock_status.total_docks IS
  'Total docking points at the station (NbDocks), including any out of service.';
