-- 050_marts_dock_hourly_hires.sql
-- marts.dock_hourly_hires: one row per dock per hour, with hires (valid trips that
-- started there), the weather, calendar fields and lagged hires for forecasting.
--
-- Every hour between a dock's first and last hire is included, even with 0 hires,
-- because a forecast has to learn the quiet hours too.
-- Lags use LAG() over a complete hourly grid, so "168 rows back" is exactly one week back.
-- Rebuild with: REFRESH MATERIALIZED VIEW marts.dock_hourly_hires;

DROP MATERIALIZED VIEW IF EXISTS marts.dock_hourly_hires;

CREATE MATERIALIZED VIEW marts.dock_hourly_hires AS
WITH counts AS (
    SELECT start_dock_id AS dock_id,
           time_bucket('1 hour', start_time) AS hour,
           count(*) AS hires
    FROM staging.journeys
    WHERE is_valid_trip AND start_match = 'matched'
    GROUP BY 1, 2
), docks AS (                       -- each dock's active period
    SELECT dock_id, min(hour) AS first_hour, max(hour) AS last_hour
    FROM counts GROUP BY dock_id
), grid AS (
    SELECT d.dock_id, w.hour, w.hour_london, w.hour_of_day, w.day_of_week,
           w.month, w.is_working_day, w.temperature_c, w.precipitation_mm,
           w.wind_speed_kmh, w.is_rain,
           COALESCE(c.hires, 0) AS hires
    FROM docks d
    JOIN marts.hires_weather w ON w.hour BETWEEN d.first_hour AND d.last_hour
    LEFT JOIN counts c ON c.dock_id = d.dock_id AND c.hour = w.hour
)
SELECT g.*,
       LAG(hires, 1)   OVER w AS hires_lag_1h,    -- the hour before
       LAG(hires, 24)  OVER w AS hires_lag_24h,   -- same hour yesterday
       LAG(hires, 168) OVER w AS hires_lag_168h   -- same hour last week
FROM grid g
WINDOW w AS (PARTITION BY dock_id ORDER BY hour);

CREATE UNIQUE INDEX dock_hourly_hires_pk ON marts.dock_hourly_hires (dock_id, hour);
CREATE INDEX dock_hourly_hires_hour_idx ON marts.dock_hourly_hires (hour);

COMMENT ON MATERIALIZED VIEW marts.dock_hourly_hires IS
  'Hires starting at each dock per hour (UTC), zero-filled between the dock''s first and last hire, with weather and lagged hires.';
COMMENT ON COLUMN marts.dock_hourly_hires.hires IS
  'Valid hires (1 minute to 1 day) that started at this dock in this hour, matched by terminal number and name.';
