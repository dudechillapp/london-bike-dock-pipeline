-- Every hour from 7 days ago up to the last weather pull must have weather.
-- Catches: a missed Open-Meteo pull, or the archive/recent switch leaving a gap.
SELECT h AS missing_hour
FROM generate_series(date_trunc('hour', now()) - INTERVAL '7 days',
                     (SELECT date_trunc('hour', max(pulled_at)) - INTERVAL '1 hour'
                      FROM raw.weather_response),
                     INTERVAL '1 hour') h
WHERE NOT EXISTS (SELECT 1 FROM staging.weather_hourly w WHERE w.hour = h);
