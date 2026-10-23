-- 020_stage_weather.sql
-- Flattens raw.weather_response into staging.weather_hourly, one row per hour.
-- Open-Meteo returns parallel arrays (time[], temperature_2m[], ...), so
-- WITH ORDINALITY gives each value its position to line them up again.
-- Idempotent: reruns update rows instead of duplicating them.

INSERT INTO staging.weather_hourly (hour, temperature_c, precipitation_mm, wind_speed_kmh, source)
SELECT DISTINCT ON (hour)
       hour, temperature_c, precipitation_mm, wind_speed_kmh, source
FROM (
    SELECT (t.value || 'Z')::timestamptz                                   AS hour,
           (r.payload->'hourly'->'temperature_2m'->>(t.n - 1)::int)::numeric  AS temperature_c,
           (r.payload->'hourly'->'precipitation' ->>(t.n - 1)::int)::numeric  AS precipitation_mm,
           (r.payload->'hourly'->'wind_speed_10m'->>(t.n - 1)::int)::numeric  AS wind_speed_kmh,
           r.source,
           r.pulled_at
    FROM raw.weather_response r,
         jsonb_array_elements_text(r.payload->'hourly'->'time') WITH ORDINALITY AS t(value, n)
) flat
WHERE hour < now()                       -- 'recent' responses include forecast hours: drop the future
  AND temperature_c IS NOT NULL
ORDER BY hour,
         (source = 'archive') DESC,      -- prefer final archive values
         pulled_at DESC                  -- then the newest pull
ON CONFLICT (hour) DO UPDATE
SET temperature_c    = EXCLUDED.temperature_c,
    precipitation_mm = EXCLUDED.precipitation_mm,
    wind_speed_kmh   = EXCLUDED.wind_speed_kmh,
    source           = EXCLUDED.source
WHERE staging.weather_hourly.source <> 'archive' OR EXCLUDED.source = 'archive';
