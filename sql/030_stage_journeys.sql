-- 030_stage_journeys.sql
-- Turns raw.journeys (all text) into staging.journeys (typed, UTC).
-- Only files not staged yet are processed. Rows that can't be parsed are
-- left out here and counted by src/checks/journeys_check.py.

BEGIN;
SET LOCAL TIME ZONE 'UTC';   -- so the London -> UTC conversion below is exact

CREATE TEMP TABLE files_to_stage ON COMMIT DROP AS
SELECT file_name FROM raw.journey_file
WHERE file_name NOT IN (SELECT file_name FROM staging.journey_file_staged);

-- Terminal number without leading zeros -> dock, for matching
CREATE TEMP TABLE dock_lookup ON COMMIT DROP AS
SELECT dock_id,
       ltrim(terminal_name, '0')                    AS terminal_key,
       ltrim(replace(dock_id, 'BikePoints_', ''), '0') AS bikepoint_key
FROM staging.dock;

WITH parsed AS (
    SELECT j.source_file,
           CASE WHEN j.rental_id ~ '^\d+$' THEN j.rental_id::bigint END AS rental_id,
           -- TfL writes London local time; newer files use YYYY-MM-DD, older DD/MM/YYYY
           CASE WHEN j.start_time ~ '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}'
                     THEN to_timestamp(left(j.start_time, 16), 'YYYY-MM-DD HH24:MI')::timestamp
                WHEN j.start_time ~ '^\d{2}/\d{2}/\d{4} \d{2}:\d{2}'
                     THEN to_timestamp(left(j.start_time, 16), 'DD/MM/YYYY HH24:MI')::timestamp
           END AS start_local,
           CASE WHEN j.end_time ~ '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}'
                     THEN to_timestamp(left(j.end_time, 16), 'YYYY-MM-DD HH24:MI')::timestamp
                WHEN j.end_time ~ '^\d{2}/\d{2}/\d{4} \d{2}:\d{2}'
                     THEN to_timestamp(left(j.end_time, 16), 'DD/MM/YYYY HH24:MI')::timestamp
           END AS end_local,
           CASE WHEN j.duration_ms ~ '^\d+$' THEN j.duration_ms::numeric / 1000
                WHEN j.duration_s  ~ '^\d+$' THEN j.duration_s::numeric
           END AS duration_s,
           j.start_station_id, j.end_station_id,
           trim(j.start_station_name) AS start_station_name,
           trim(j.end_station_name)   AS end_station_name,
           j.bike_id, j.bike_model
    FROM raw.journeys j
    JOIN files_to_stage f ON f.file_name = j.source_file
),
ins AS (
INSERT INTO staging.journeys (rental_id, start_time, end_time, duration_s,
                              start_station_id, end_station_id, start_dock_id, end_dock_id,
                              start_station_name, end_station_name, bike_id, bike_model, source_file)
SELECT p.rental_id,
       p.start_local AT TIME ZONE 'Europe/London',   -- London local time -> UTC
       p.end_local   AT TIME ZONE 'Europe/London',
       p.duration_s,
       p.start_station_id, p.end_station_id,
       COALESCE(st.dock_id, sb.dock_id),
       COALESCE(et.dock_id, eb.dock_id),
       p.start_station_name, p.end_station_name, p.bike_id, p.bike_model, p.source_file
FROM parsed p
LEFT JOIN dock_lookup st ON st.terminal_key  = ltrim(p.start_station_id, '0')
LEFT JOIN dock_lookup sb ON sb.bikepoint_key = ltrim(p.start_station_id, '0') AND st.dock_id IS NULL
LEFT JOIN dock_lookup et ON et.terminal_key  = ltrim(p.end_station_id, '0')
LEFT JOIN dock_lookup eb ON eb.bikepoint_key = ltrim(p.end_station_id, '0') AND et.dock_id IS NULL
WHERE p.rental_id IS NOT NULL
  AND p.start_local IS NOT NULL
ON CONFLICT (rental_id, start_time) DO NOTHING
RETURNING source_file
)
-- Record each file as staged, with how many rows made it through
INSERT INTO staging.journey_file_staged (file_name, rows_staged)
SELECT f.file_name, count(ins.source_file)
FROM files_to_stage f
LEFT JOIN ins ON ins.source_file = f.file_name
GROUP BY f.file_name;

COMMIT;
