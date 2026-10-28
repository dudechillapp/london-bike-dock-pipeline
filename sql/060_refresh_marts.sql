-- 060_refresh_marts.sql
-- Refreshes the marts after new journeys or weather have been staged.
-- CONCURRENTLY keeps them readable while they rebuild (needs their unique indexes).
-- Order matters: dock_hourly_hires is built on hires_weather.

REFRESH MATERIALIZED VIEW CONCURRENTLY marts.hires_weather;
REFRESH MATERIALIZED VIEW CONCURRENTLY marts.dock_hourly_hires;
