-- London weather must be physically plausible.
SELECT hour, temperature_c, precipitation_mm, wind_speed_kmh
FROM staging.weather_hourly
WHERE temperature_c NOT BETWEEN -25 AND 45
   OR precipitation_mm NOT BETWEEN 0 AND 100
   OR wind_speed_kmh NOT BETWEEN 0 AND 200;
