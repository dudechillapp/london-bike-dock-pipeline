-- 040_marts_hires_weather.sql
-- marts.hires_weather: one row per hour with valid hires and the weather in that hour.
-- Hours with no hires are kept as 0, not left out, so averages are honest.
-- Rebuild with: REFRESH MATERIALIZED VIEW marts.hires_weather;

DROP MATERIALIZED VIEW IF EXISTS marts.hires_weather;

CREATE MATERIALIZED VIEW marts.hires_weather AS
WITH hires AS (
    SELECT time_bucket('1 hour', start_time) AS hour, count(*) AS hires
    FROM staging.journeys
    WHERE is_valid_trip
    GROUP BY 1
), period AS (
    SELECT min(start_time) AS first_hire, max(start_time) AS last_hire
    FROM staging.journeys
)
SELECT w.hour,                                                         -- UTC
       (w.hour AT TIME ZONE 'Europe/London')                       AS hour_london,
       extract(hour FROM w.hour AT TIME ZONE 'Europe/London')::int AS hour_of_day,
       extract(isodow FROM w.hour AT TIME ZONE 'Europe/London')::int AS day_of_week,  -- 1 = Monday
       date_trunc('month', w.hour AT TIME ZONE 'Europe/London')::date AS month,
       (extract(isodow FROM w.hour AT TIME ZONE 'Europe/London') <= 5
        AND (w.hour AT TIME ZONE 'Europe/London')::date
            NOT IN (SELECT day FROM staging.uk_bank_holiday))         AS is_working_day,
       COALESCE(h.hires, 0)                                         AS hires,
       w.temperature_c,
       w.precipitation_mm,
       w.wind_speed_kmh,
       w.is_rain
FROM staging.weather_hourly w
CROSS JOIN period p
LEFT JOIN hires h ON h.hour = w.hour
WHERE w.hour >= time_bucket('1 hour', p.first_hire)
  AND w.hour <= time_bucket('1 hour', p.last_hire);

CREATE UNIQUE INDEX hires_weather_hour_idx ON marts.hires_weather (hour);

COMMENT ON MATERIALIZED VIEW marts.hires_weather IS
  'Valid hires per hour joined to London weather. Hours are UTC; hour_of_day and month are London time.';
COMMENT ON COLUMN marts.hires_weather.is_working_day IS
  'Monday to Friday, excluding England bank holidays.';
COMMENT ON COLUMN marts.hires_weather.is_rain IS
  'More than 0.5 mm of rain in the hour (project brief definition).';
