-- 002_weather_schema.sql
-- Tables for hourly London weather from Open-Meteo.
-- Safe to run more than once.

-- raw: every API response exactly as received
CREATE TABLE IF NOT EXISTS raw.weather_response (
    pulled_at   timestamptz NOT NULL,
    source      text        NOT NULL,   -- 'archive' (final, about 5 days behind) or 'recent' (last 7 days)
    start_date  date        NOT NULL,
    end_date    date        NOT NULL,
    payload     jsonb       NOT NULL
);

COMMENT ON TABLE raw.weather_response IS
  'Open-Meteo responses for central London (51.5072, -0.1276), hourly, times in UTC. Never edited.';

-- staging: one row per hour
CREATE TABLE IF NOT EXISTS staging.weather_hourly (
    hour              timestamptz PRIMARY KEY,
    temperature_c     numeric(4,1),
    precipitation_mm  numeric(5,1),
    wind_speed_kmh    numeric(5,1),
    source            text,
    is_rain           boolean GENERATED ALWAYS AS (precipitation_mm > 0.5) STORED
);

COMMENT ON TABLE staging.weather_hourly IS
  'Hourly London weather, one row per hour (UTC). Archive values replace recent values once available.';
COMMENT ON COLUMN staging.weather_hourly.hour IS
  'Start of the hour, UTC. Stored in UTC so the clock change never creates duplicate or missing hours.';
COMMENT ON COLUMN staging.weather_hourly.precipitation_mm IS
  'Rain, showers and snow in the hour, in mm.';
COMMENT ON COLUMN staging.weather_hourly.is_rain IS
  'True when precipitation is above 0.5 mm. The rain threshold from the project brief.';
