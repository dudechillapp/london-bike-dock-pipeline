-- 070_agent_layer.sql
-- Makes the warehouse safe and easy for an AI agent to use (Step 8).
--   1. A read-only database role that can only see the marts schema
--   2. Small, well-described views for the questions the agent answers
--   3. A metric catalog, so the agent quotes the same definitions as the docs
--
-- Run with the agent's password as a psql variable (see README):
--   ... | docker exec -i bikes-warehouse psql -U bikes -d bikes -v ON_ERROR_STOP=1 -v agent_password=...

-- ---------------------------------------------------------------
-- 1. Read-only role
-- ---------------------------------------------------------------
SELECT format('CREATE ROLE agent_reader LOGIN PASSWORD %L', :'agent_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agent_reader') \gexec

ALTER ROLE agent_reader SET default_transaction_read_only = on;   -- can never write
ALTER ROLE agent_reader SET statement_timeout = '15s';            -- can never run away

REVOKE ALL ON SCHEMA raw, staging FROM agent_reader;              -- no raw or staging data
GRANT USAGE ON SCHEMA marts TO agent_reader;

-- ---------------------------------------------------------------
-- 2. Views for the agent (views run with the owner's rights, so the
--    agent sees staging data only in the shape these views give it)
-- ---------------------------------------------------------------
CREATE OR REPLACE VIEW marts.dock AS
SELECT dock_id,
       name,
       trim(split_part(name, ',', -1)) AS area,
       lat, lon,
       last_seen
FROM staging.dock;

COMMENT ON VIEW marts.dock IS
  'One row per Santander Cycles dock. area = the part of the name after the last comma, e.g. Waterloo.';

CREATE OR REPLACE VIEW marts.dock_status_latest AS
SELECT d.name, d.area,
       s.bikes, s.ebikes, s.empty_docks, s.total_docks,
       s.total_docks - s.bikes - s.empty_docks AS out_of_service_spaces,
       s.pulled_at AS as_of
FROM staging.dock_status s
JOIN marts.dock d USING (dock_id)
WHERE s.pulled_at = (SELECT max(pulled_at) FROM staging.dock_status);

COMMENT ON VIEW marts.dock_status_latest IS
  'Live bikes and spaces at every dock from the newest 15-minute pull. Check as_of before trusting it.';

DROP MATERIALIZED VIEW IF EXISTS marts.area_morning_rush;
CREATE MATERIALIZED VIEW marts.area_morning_rush AS
SELECT d.area,
       (h.hour AT TIME ZONE 'Europe/London')::date AS day,
       sum(h.hires) AS hires
FROM marts.dock_hourly_hires h
JOIN marts.dock d USING (dock_id)
WHERE h.is_working_day AND h.hour_of_day BETWEEN 7 AND 9
GROUP BY 1, 2;

CREATE UNIQUE INDEX area_morning_rush_pk ON marts.area_morning_rush (area, day);

COMMENT ON MATERIALIZED VIEW marts.area_morning_rush IS
  'Valid hires starting in each area in the working-day morning rush, 07:00-09:59 London time, per day.';

-- ---------------------------------------------------------------
-- 3. Metric catalog: one agreed definition per KPI
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS marts.metric_catalog (
    name        text PRIMARY KEY,
    definition  text NOT NULL,
    source      text NOT NULL
);

INSERT INTO marts.metric_catalog (name, definition, source) VALUES
  ('hires',
   'Valid hires: lasted 1 minute to 1 day and ended after they started. Counted at the dock where they started.',
   'marts.dock_hourly_hires, marts.hires_weather'),
  ('working day',
   'Monday to Friday, excluding England bank holidays. Times are London local time.',
   'marts.hires_weather.is_working_day'),
  ('morning rush',
   'Working days, 07:00 to 09:59 London time.',
   'marts.area_morning_rush'),
  ('rain hour',
   'An hour with more than 0.5 mm of precipitation in central London (Open-Meteo).',
   'marts.hires_weather.is_rain'),
  ('rain effect',
   'Percentage fewer hires in rain hours than in dry hours at the same hour of the day, in the same month, on the same kind of day. About 28 percent on working days (Jun 2025 to May 2026).',
   'docs/findings.md, Finding 1'),
  ('forecast error',
   'MAE (Mean Absolute Error): the average number of hires a forecast is off by, tested on May 2026, a month the model never saw.',
   'marts.hire_forecast, docs/findings.md, Finding 2'),
  ('out of service spaces',
   'Docking points counted in the dock total but neither holding a bike nor free: total docks minus bikes minus empty docks. Most likely broken points.',
   'marts.dock_status_latest, docs/data_issues.md, issue 1'),
  ('area',
   'The part of a dock name after the last comma, for example Haggerston in "Belford House, Haggerston".',
   'marts.dock')
ON CONFLICT (name) DO UPDATE SET definition = EXCLUDED.definition, source = EXCLUDED.source;

-- Read access to everything in marts, now and in future
GRANT SELECT ON ALL TABLES IN SCHEMA marts TO agent_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA marts GRANT SELECT ON TABLES TO agent_reader;
